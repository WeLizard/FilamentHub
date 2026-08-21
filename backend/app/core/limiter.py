"""Rate limiting setup with Redis backend."""

import hashlib

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings


def client_key(request: Request) -> str:
    """Count requests per person, not per proxy.

    The backend is reachable only through nginx, so the socket peer is the same
    address for every visitor and each limit would otherwise be shared by the
    whole site. The real address arrives in a header nginx sets, trusted only
    when the peer is the proxy itself, so it cannot be spoofed from outside.

    Imported inside the function because the region service pulls in settings
    and the GeoIP reader, which must not load while the limiter is constructed.
    """
    from app.services.request_region_service import get_request_client_ip

    client_ip = get_request_client_ip(request)
    return str(client_ip) if client_ip is not None else get_remote_address(request)


def adapter_token_key(request: Request) -> str:
    """Rate-limit one bridge credential without storing or logging its secret."""
    token = request.headers.get("X-FilamentHub-Bridge-Token")
    if token:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return f"bridge:{digest}"
    return client_key(request)


limiter = Limiter(
    key_func=client_key,
    storage_uri=settings.REDIS_URL,
)
