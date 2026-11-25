"""Record a failure of the web application in a reader's browser.

A page that fails to render shows the reader a recovery screen and, before
this endpoint, told nobody else: the cause stayed in that browser's console.
The report goes to the application log, where it can be read next to the
release that produced it. It carries no account and no address query.
"""

import logging
import re

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

from app.core.limiter import limiter

router = APIRouter(prefix="/client-errors", tags=["client-errors"])
logger = logging.getLogger(__name__)

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class ClientErrorReport(BaseModel):
    message: str = Field(max_length=500)
    stack: str = Field(default="", max_length=4000)
    component_stack: str = Field(default="", max_length=2000)
    path: str = Field(default="", max_length=300)
    build: str = Field(default="", max_length=80)


def _one_line(value: str) -> str:
    return _CONTROL.sub(" ", value.replace("\n", " ")).strip()


def _lines(value: str) -> str:
    return _CONTROL.sub(" ", value).strip()


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/hour")
async def report_client_error(request: Request, data: ClientErrorReport) -> Response:
    """Write one render failure to the log. A broken page must not flood it."""
    logger.warning(
        "Client render error: build=%s path=%s message=%s\n%s\n%s",
        _one_line(data.build) or "-",
        _one_line(data.path).split("?")[0] or "-",
        _one_line(data.message),
        _lines(data.stack),
        _lines(data.component_stack),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
