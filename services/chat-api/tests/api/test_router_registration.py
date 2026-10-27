"""Import-level proof that the session-share router is mounted under /api.

The session-share router must be registered under the same ``/api`` prefix
as other routers. FastAPI 0.141 stores included routers lazily, while older
versions flatten their routes into ``app.routes``. Cover both layouts.
"""

from __future__ import annotations

import fastapi.routing
from fastapi.routing import APIRoute

from app.api.endpoints import session_shares
from app.main import app


def test_session_share_router_mounted_under_api_prefix() -> None:
    included_router = getattr(fastapi.routing, "_IncludedRouter", None)
    if included_router is None:
        mounted = {
            (method, route.path)
            for route in app.routes
            if isinstance(route, APIRoute)
            for method in route.methods
        }
    else:
        included = [
            route
            for route in app.routes
            if isinstance(route, included_router)
            and route.original_router is session_shares.router
        ]
        assert included, "session_shares.router is not registered in app.main"
        mounted = {
            (method, ctx.path)
            for ctx in included[0].effective_candidates()
            if isinstance(ctx.original_route, APIRoute)
            for method in ctx.original_route.methods
        }
    expected = {
        ("POST", "/api/sessions/{session_id}/share"),
        ("POST", "/api/session-shares/{token}/join"),
        ("DELETE", "/api/sessions/{session_id}/share"),
        ("GET", "/api/sessions/{session_id}/participants"),
        ("DELETE", "/api/sessions/{session_id}/participants/me"),
        ("DELETE", "/api/sessions/{session_id}/participants/{user_id}"),
    }
    missing = expected - mounted
    assert not missing, f"session-share routes missing under /api: {sorted(missing)}"
