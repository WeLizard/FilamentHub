"""Let browsers and the production reverse proxy keep public catalogue reads.

The catalogue is the same for everyone and changes rarely: a material's page is
identical whoever opens it, and nothing about it depends on who is signed in.
Yet every visit re-fetched every page in full, and the plugin asks for the same
lists on every sync.

So catalogue answers now carry a version tag and a short life. Browsers retain
them for conditional reuse, while production nginx keeps a bounded cache shared
by all Uvicorn workers. A hot response therefore reaches neither the
application nor PostgreSQL; after expiry, one request refreshes it and the
others wait for that result instead of rebuilding it in parallel.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Named one by one rather than by a common beginning: a whole branch of the API
# is not a safe unit to declare public. Under /brands alone sit a team roster and
# a usage report, both of which answer differently depending on who asks — the
# kind of thing a shared cache must never be told it may hand to the next person.
# Anything not listed here is left alone, so a new endpoint is private by
# default and becomes cacheable only when someone decides it is.
CACHEABLE_ROUTES = frozenset(
    {
        "/api/v1/filaments/",
        "/api/v1/filaments/material-types",
        "/api/v1/filaments/{filament_id}",
        "/api/v1/filaments/{filament_id}/presets",
        "/api/v1/filaments/{filament_id}/compatible-printers",
        "/api/v1/filament-lines",
        "/api/v1/brands/",
        "/api/v1/brands/{identifier}",
        "/api/v1/printers/",
        "/api/v1/printers/{printer_id}",
        "/api/v1/printers/{printer_id}/compatible-filaments",
    }
)

# The browser always revalidates: nginx answers that conditional request from
# its shared cache, without Python or SQL, and the client cannot accidentally
# add another full max-age after receiving an already-aged nginx object.
BROWSER_MAX_AGE_SECONDS = 0

# Long enough to absorb a page's worth of navigation, short enough that an edit
# in the admin panel shows up while the person who made it is still looking.
NGINX_MAX_AGE_SECONDS = 60

# nginx consumes this header as a shared-cache lifetime and does not forward it
# to the client. The browser revalidates immediately; the reverse proxy is the
# only layer allowed to hold a fresh representation for sixty seconds.
NGINX_CACHE_HEADER = "x-accel-expires"

# JSON catalogue pages are bounded, but the middleware must not turn a future
# stream or accidentally oversized response into one large per-request buffer.
MAX_CACHEABLE_BODY_BYTES = 1024 * 1024


async def _body_chunks(body: bytes) -> AsyncIterator[bytes]:
    """Restore a response body after BaseHTTPMiddleware has inspected it."""
    if body:
        yield body


def _if_none_match_matches(value: str | None, etag: str) -> bool:
    """Apply the weak comparison required by If-None-Match for GET requests."""
    if value is None:
        return False

    for candidate in value.split(","):
        candidate = candidate.strip()
        if candidate == "*":
            return True
        if candidate.startswith("W/"):
            candidate = candidate[2:].lstrip()
        if candidate == etag:
            return True

    return False


class CatalogueCacheMiddleware(BaseHTTPMiddleware):
    """Add a version tag to catalogue answers and honour the one a browser holds."""

    async def dispatch(self, request: Request, call_next):
        # FastAPI catalogue routes currently expose GET, not HEAD. Hashing a
        # future HEAD response here would hash its empty wire body instead of
        # the GET representation and produce the wrong validator.
        if request.method != "GET":
            return await call_next(request)

        response = await call_next(request)
        if response.status_code != 200:
            return response

        # Which endpoint answered is known only once routing has happened, and
        # the endpoint — not the address — is what decides whether the answer
        # belongs to everyone.
        route = request.scope.get("route")
        if getattr(route, "path", None) not in CACHEABLE_ROUTES:
            return response

        # An endpoint may own its validator or need a stricter policy for a
        # particular successful response. Its explicit contract always wins,
        # and a response that sets cookies must never become shared content.
        if any(
            header in response.headers
            for header in ("cache-control", "etag", "set-cookie")
        ):
            return response

        content_lengths = response.headers.getlist("content-length")
        if len(content_lengths) != 1:
            return response
        try:
            content_length = int(content_lengths[0])
        except ValueError:
            return response
        if content_length < 0 or content_length > MAX_CACHEABLE_BODY_BYTES:
            return response

        body = b"".join([section async for section in response.body_iterator])
        etag = '"%s"' % hashlib.sha256(body).hexdigest()[:32]

        # Mutate the original response instead of rebuilding it from a dict.
        # Header names are case-insensitive on the wire but Python dict keys
        # are not: rebuilding and adding `Content-Length` beside Starlette's
        # existing `content-length` produced two physical headers, which strict
        # HTTP clients reject. Keeping the response also preserves repeated
        # headers and any response-specific state.
        response.headers["etag"] = etag
        response.headers["cache-control"] = (
            f"public, max-age={BROWSER_MAX_AGE_SECONDS}, must-revalidate"
        )
        response.headers[NGINX_CACHE_HEADER] = str(NGINX_MAX_AGE_SECONDS)

        if _if_none_match_matches(request.headers.get("if-none-match"), etag):
            # Nothing changed since they last asked: say so and send no body.
            response.status_code = 304
            for header in (
                "content-length",
                "content-type",
                "content-encoding",
                "content-range",
                "transfer-encoding",
            ):
                if header in response.headers:
                    del response.headers[header]
            response.body_iterator = _body_chunks(b"")
            return response

        response.headers["content-length"] = str(len(body))
        response.body_iterator = _body_chunks(body)
        return response
