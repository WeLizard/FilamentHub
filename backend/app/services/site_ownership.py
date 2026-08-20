"""Prove that an applicant controls the brand's own site.

A scan can be produced by anyone; placing a code on the brand's domain requires
access to it. The check is deliberately narrow: one fixed path, one exact token,
no redirects to other hosts and a small response budget, so a request cannot be
turned into a probe of arbitrary addresses.
"""

import asyncio
import logging
import secrets
import socket
from datetime import datetime, timezone
from ipaddress import ip_address

import httpx

from app.services.email_validator import normalize_website_url

logger = logging.getLogger(__name__)

VERIFICATION_PATH = "/.well-known/filamenthub.txt"
_TOKEN_PREFIX = "filamenthub-verify-"
_MAX_BODY_BYTES = 4096
_TIMEOUT_SECONDS = 8.0


def new_verification_token() -> str:
    return f"{_TOKEN_PREFIX}{secrets.token_hex(16)}"


def _is_public_address(value: str) -> bool:
    """Only public unicast targets may be contacted by the verifier."""
    try:
        return ip_address(value).is_global
    except ValueError:
        return False


async def _resolve_public_addresses(domain: str) -> set[str]:
    """Resolve every address and reject the host if any target is non-public."""
    try:
        records = await asyncio.get_running_loop().getaddrinfo(
            domain,
            443,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except OSError:
        return set()

    addresses = {record[4][0] for record in records}
    if not addresses or not all(_is_public_address(address) for address in addresses):
        return set()
    return addresses


async def confirm_site_ownership(website: str | None, token: str) -> tuple[bool, str | None]:
    """Read the token from the brand's domain. Returns (confirmed, domain)."""
    domain = normalize_website_url(website or "")
    if not domain or not token:
        return False, None

    allowed_addresses = await _resolve_public_addresses(domain)
    if not allowed_addresses:
        logger.warning("Site verification rejected a non-public target for %s", domain)
        return False, domain

    url = f"https://{domain}{VERIFICATION_PATH}"
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT_SECONDS,
            follow_redirects=False,
            trust_env=False,
            headers={
                "User-Agent": "FilamentHub-SiteVerification",
                "Accept-Encoding": "identity",
            },
        ) as client:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    return False, domain

                connected_stream = response.extensions.get("network_stream")
                server_addr = (
                    connected_stream.get_extra_info("server_addr")
                    if connected_stream is not None
                    else None
                )
                connected_address = server_addr[0] if server_addr else None
                if (
                    connected_address is None
                    or not _is_public_address(connected_address)
                    or connected_address not in allowed_addresses
                ):
                    logger.warning(
                        "Site verification connection for %s reached an unexpected target",
                        domain,
                    )
                    return False, domain

                body = bytearray()
                chunks = response.aiter_raw(chunk_size=1024)
                try:
                    async for chunk in chunks:
                        body.extend(chunk)
                        if len(body) > _MAX_BODY_BYTES:
                            return False, domain
                finally:
                    close_chunks = getattr(chunks, "aclose", None)
                    if close_chunks is not None:
                        await close_chunks()
    except httpx.HTTPError:
        logger.info("Site verification unreachable for %s", domain, exc_info=True)
        return False, domain

    text = bytes(body).decode("utf-8", errors="ignore")
    return token in text.split(), domain


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
