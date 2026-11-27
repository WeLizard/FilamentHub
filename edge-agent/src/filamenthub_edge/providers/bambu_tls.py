"""Reaching a Bambu Lab printer: which address, and whose certificate.

The printer serves MQTT and its files behind TLS with a certificate Bambu Lab
issued to it at the factory. Both of Edge's readers come through here, so the
access code is sent only to a local address and only to the printer that was
linked.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import ssl
import time
from pathlib import Path
from typing import Any

from ..errors import ProviderUnavailable, StateError
from ..storage import JsonStateFile
from ._bambu_trust import (
    BAMBU_CA_CERTIFICATES,
    bambu_certificate_fingerprint,
    bambu_certificate_serial,
)

logger = logging.getLogger("filamenthub_edge.bambu")

MAX_TRUST_BYTES = 4096


class CertificateRejected(ProviderUnavailable):
    """The device at the printer's address is not the printer that was linked."""


def resolve_printer(
    host: str, port: int, *, label: str = "Bambu printer"
) -> tuple[socket.AddressFamily, tuple[Any, ...]]:
    """Resolve once and accept only an address inside the local network.

    A printer's access code or LAN login is sent to whatever answers there, so
    it never goes to an address on the public internet.
    """
    try:
        candidates = socket.getaddrinfo(
            host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
        )
    except (OSError, UnicodeError) as exc:
        raise ProviderUnavailable(f"{label} address could not be resolved") from exc
    for family, _, _, _, sockaddr in candidates:
        try:
            address = ipaddress.ip_address(str(sockaddr[0]).split("%")[0])
        except ValueError:
            continue
        local = address.is_private or address.is_link_local or address.is_loopback
        if local and not (address.is_multicast or address.is_unspecified):
            return family, sockaddr
    raise ProviderUnavailable(f"{label} address must be inside the local network")


def _tls_context(
    *, verify: bool, maximum_version: ssl.TLSVersion | None = None
) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    # A printer certificate names a serial number, not a host; the caller
    # compares it.
    context.check_hostname = False
    if verify:
        context.verify_mode = ssl.CERT_REQUIRED
        # Bambu Lab's root certificates do not satisfy the strict X.509 checks
        # that newer Python turns on by default.
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT
        context.load_verify_locations(cadata=BAMBU_CA_CERTIFICATES)
    else:
        context.verify_mode = ssl.CERT_NONE
    if maximum_version is not None:
        context.maximum_version = maximum_version
    return context


def _handshake(
    family: socket.AddressFamily,
    sockaddr: tuple[Any, ...],
    timeout: float,
    *,
    verify: bool,
    maximum_version: ssl.TLSVersion | None,
) -> ssl.SSLSocket:
    raw = socket.socket(family, socket.SOCK_STREAM)
    raw.settimeout(timeout)
    try:
        raw.connect(sockaddr)
        context = _tls_context(verify=verify, maximum_version=maximum_version)
        return context.wrap_socket(raw, server_hostname=None)
    except BaseException:
        raw.close()
        raise


def open_printer(
    family: socket.AddressFamily,
    sockaddr: tuple[Any, ...],
    *,
    serial: str,
    pinned: str,
    timeout: float,
    maximum_version: ssl.TLSVersion | None = None,
) -> ssl.SSLSocket:
    """Connect to the printer that was linked and to nobody else.

    A linked printer is recognised by the certificate it showed when it last
    accepted the access code. A different certificate is accepted only when
    Bambu Lab issued it to the same serial number; otherwise nothing, the
    access code included, is sent. A printer seen for the first time is
    trusted as it is: newer models are issued by certificates this build may
    not carry yet, so the chain alone cannot be required of everyone.
    """
    deadline = time.monotonic() + timeout

    def handshake(*, verify: bool) -> ssl.SSLSocket:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Bambu TLS connection timed out")
        return _handshake(
            family, sockaddr, remaining, verify=verify, maximum_version=maximum_version
        )

    sock = handshake(verify=False)
    if pinned and bambu_certificate_fingerprint(sock.getpeercert(True)) != pinned:
        sock.close()
        try:
            sock = handshake(verify=True)
        except ssl.SSLCertVerificationError:
            raise CertificateRejected("Bambu printer certificate changed") from None
        if bambu_certificate_serial(sock.getpeercert()) != serial:
            sock.close()
            raise CertificateRejected("Bambu certificate names another printer")
    sock.settimeout(timeout)
    return sock


class CertificateMemory:
    """The certificate a printer showed when it last accepted the access code."""

    def __init__(self, path: Path | None) -> None:
        self._file = JsonStateFile(path) if path is not None else None
        self._held: dict[str, str] = {}

    def pinned(self, serial: str) -> str:
        if serial in self._held:
            return self._held[serial]
        if self._file is None:
            return ""
        try:
            document = self._file.read_document(max_bytes=MAX_TRUST_BYTES) or {}
        except StateError:
            # An unreadable file is no evidence; the next accepted login rewrites it.
            return ""
        certificate = document.get("certificate")
        if (
            document.get("serial") != serial
            or not isinstance(certificate, str)
            or not re.fullmatch(r"[0-9a-f]{64}", certificate)
        ):
            return ""
        self._held[serial] = certificate
        return certificate

    def remember(self, serial: str, fingerprint: str) -> None:
        if not fingerprint or self.pinned(serial) == fingerprint:
            return
        self._held = {serial: fingerprint}
        if self._file is None:
            return
        try:
            self._file.write_document(
                {"serial": serial, "certificate": fingerprint}, max_bytes=MAX_TRUST_BYTES
            )
        except StateError:
            # Held for this run; the next start learns it again.
            logger.warning("Bambu printer certificate could not be saved")

    def forget(self) -> None:
        self._held = {}
        if self._file is None:
            return
        try:
            self._file.write_document({}, max_bytes=MAX_TRUST_BYTES)
        except StateError:
            logger.warning("Bambu printer certificate could not be forgotten")
