"""Every admin route must ask who is calling before it does anything.

The dangerous ones are not the endpoints written today but the ones added
later: a broadcast to the whole user base and the correspondence with brands
sit behind a single `Depends`, and forgetting it on a new route is silent. A
per-endpoint 403 test would only cover the endpoints that already exist, so the
boundary is checked over the whole route table instead.
"""

from fastapi.routing import APIRoute

from app.core.dependencies import get_current_admin_user
from app.main import app

ADMIN_PREFIX = "/api/v1/admin"

# Routes under /admin that are deliberately reachable without an admin session.
# Each entry needs a reason, not just a path.
PUBLIC_ADMIN_ROUTES: dict[str, str] = {}


def _dependency_calls(dependant) -> set:
    calls = {dependency.call for dependency in dependant.dependencies}
    for dependency in dependant.dependencies:
        calls |= _dependency_calls(dependency)
    return calls


def test_no_admin_route_is_left_without_an_admin_check():
    checked = 0
    unguarded = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith(ADMIN_PREFIX):
            continue
        if route.path in PUBLIC_ADMIN_ROUTES:
            continue
        checked += 1
        if get_current_admin_user not in _dependency_calls(route.dependant):
            unguarded.append(f"{sorted(route.methods)} {route.path}")

    # A renamed prefix would otherwise leave this test green over nothing.
    assert checked > 50, f"expected the admin surface, found {checked} routes"
    assert not unguarded, "admin routes without an admin check: " + ", ".join(sorted(unguarded))
