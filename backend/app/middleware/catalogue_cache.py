"""Let a browser keep the catalogue instead of asking for it again.

The catalogue is the same for everyone and changes rarely: a material's page is
identical whoever opens it, and nothing about it depends on who is signed in.
Yet every visit re-fetched every page in full, and the plugin asks for the same
lists on every sync.

So catalogue answers now carry a version tag and a short life. Within that life
the browser does not ask at all; after it, it asks with the tag it holds and is
told "unchanged" in a couple of hundred bytes instead of being sent the whole
list again.

The tag is computed from the answer, so the database is still consulted to
produce it — what this saves is the transfer and the client's work, which on a
phone or a slow connection is the part a person feels. Skipping the database
too would need a version counter the catalogue does not have yet.
"""

from __future__ import annotations

import hashlib

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

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
        "/api/v1/brands/slug-suggestion",
        "/api/v1/brands/{identifier}",
        "/api/v1/printers/",
        "/api/v1/printers/{printer_id}",
        "/api/v1/printers/{printer_id}/compatible-filaments",
    }
)

# Long enough to absorb a page's worth of navigation, short enough that an edit
# in the admin panel shows up while the person who made it is still looking.
MAX_AGE_SECONDS = 60


class CatalogueCacheMiddleware(BaseHTTPMiddleware):
    """Add a version tag to catalogue answers and honour the one a browser holds."""

    async def dispatch(self, request: Request, call_next):
        if request.method not in ("GET", "HEAD"):
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

        body = b"".join([section async for section in response.body_iterator])
        etag = '"%s"' % hashlib.sha256(body).hexdigest()[:32]

        headers = dict(response.headers)
        headers["ETag"] = etag
        headers["Cache-Control"] = f"public, max-age={MAX_AGE_SECONDS}"

        if request.headers.get("if-none-match") == etag:
            # Nothing changed since they last asked: say so and send no body.
            headers.pop("content-length", None)
            return Response(status_code=304, headers=headers)

        headers["Content-Length"] = str(len(body))
        return Response(
            content=body,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
        )
