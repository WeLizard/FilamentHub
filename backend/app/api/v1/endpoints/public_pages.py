"""Server-rendered public pages, requested by nginx for crawlers and first loads."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.public_page_render import render_public_page

router = APIRouter(prefix="/public-pages", tags=["seo"])


@router.get("/render", include_in_schema=False)
async def render_page(
    db: Annotated[AsyncSession, Depends(get_db)],
    x_original_uri: Annotated[str, Header(alias="X-Original-URI")],
) -> Response:
    """Return the page as HTML with SSI includes for nginx to complete.

    404 and 301 carry no page: nginx answers a missing page with the
    application's own not-found screen, and follows a redirect as is.
    """
    page = await render_public_page(db, x_original_uri)
    if page.location is not None:
        return Response(
            status_code=status.HTTP_301_MOVED_PERMANENTLY,
            headers={"Location": page.location, "Cache-Control": "no-store"},
        )
    return HTMLResponse(page.html, status_code=page.status, headers={"Cache-Control": "no-cache"})
