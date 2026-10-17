"""The browser client, served by the app itself (TDD §8; plan G4-1).

`index.html` is served at `/` and the hashed bundle under `/assets/`, ahead of the MCP mount, so
`/mcp` and the protected-resource metadata are unaffected. The page gets a strict Content
Security Policy: scripts and styles only from this origin, and network calls only to this origin
and Cognito. `GET /api/config` gives the client its sign-in settings; none of them is secret.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings

WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"
SCOPES = "openid homekeep/api homekeep/mcp"


def client_config(settings: Settings, *, local_sign_in: bool) -> dict[str, Any]:
    cognito = None
    if settings.cognito_issuer and settings.cognito_domain and settings.cognito_web_client_id:
        cognito = {
            "authority": settings.cognito_issuer,
            "domain": settings.cognito_domain,
            "client_id": settings.cognito_web_client_id,
            "redirect_uri": f"{settings.app_base_url}/",
            "scope": SCOPES,
        }
    return {"env": settings.env, "local_sign_in": local_sign_in, "cognito": cognito}


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def content_security_policy(settings: Settings) -> str:
    cognito = " ".join(
        _origin(url) for url in (settings.cognito_issuer, settings.cognito_domain) if url
    )
    return "; ".join(
        [
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self'",
            "img-src 'self' data:",
            f"connect-src 'self' {cognito}".strip(),
            f"form-action 'self' {cognito}".strip(),
            "frame-ancestors 'none'",
            "base-uri 'none'",
            "object-src 'none'",
        ]
    )


def install(app: FastAPI, settings: Settings, web_dist: Path, *, local_sign_in: bool) -> None:
    """Add the config route and, when the client has been built, the page and its assets."""
    config = client_config(settings, local_sign_in=local_sign_in)
    page_headers = {"Content-Security-Policy": content_security_policy(settings)}

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    @app.get("/api/config", include_in_schema=False)
    async def get_config() -> dict[str, Any]:
        return config

    index = web_dist / "index.html"
    if not index.is_file():
        return  # tests and `make test` run without a built client
    if (web_dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    async def page() -> FileResponse:
        return FileResponse(index, media_type="text/html", headers=page_headers)
