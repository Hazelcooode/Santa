"""Taimi backend: FastAPI app serving the API and both existing frontends.

  /            website (src/)            - requires sign-in
  /mobile/     mobile app (mobile/)      - requires sign-in, runs against the API
  /login       sign-in page              /logout  sign out
  /api/...     mobile-compatible endpoints (FigmentAPI contract)
  /api/v1/...  full API (docs/api.md)    /docs    OpenAPI explorer
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import auth, db, errors, exa_client, scheduler, seed
from .config import BACKEND_DIR, REPO_DIR, settings
from .routers import account, care, compat, organiser, research

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
MAX_BODY = 6 * 1024 * 1024  # product photos as data URLs


@asynccontextmanager
async def lifespan(app):
    db.connect()
    seed.ensure_test_account()
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(title="Taimi API", version="1.0.0", lifespan=lifespan,
              description="Backend for the Taimi personal assistant (web + mobile). Exa is the agents' only search source.")
errors.install(app)
if settings.cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def guard(request: Request, call_next):
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > MAX_BODY:
        return errors.JSONResponse({"error": {"code": "PAYLOAD_TOO_LARGE", "message": "Request is too large.", "retryable": False}}, status_code=413)
    # CSRF: cookie-authenticated writes must come from our own origin.
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/") \
            and not request.headers.get("authorization") and request.cookies.get(auth.COOKIE):
        origin = request.headers.get("origin")
        host = request.headers.get("host", "")
        if origin and origin.split("://", 1)[-1] != host and origin not in settings.cors_origins:
            return errors.JSONResponse({"error": {"code": "FORBIDDEN", "message": "Cross-site request blocked.", "retryable": False}}, status_code=403)
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


for r in (account.router, compat.router, organiser.router, care.router, research.router):
    app.include_router(r)


@app.get("/healthz", include_in_schema=False)
def healthz():
    db.q1("SELECT 1 AS ok")
    return {"ok": True, "exa": exa_client.effective_mode()}


# ------------------------------------------------------------- frontends
STATIC = BACKEND_DIR / "app" / "static"
MOBILE = REPO_DIR / "mobile"
WEB_SRC = REPO_DIR / "src"


def _gate(request):
    return auth.user_for_token(auth.token_from_request(request))


def _inject(path, before_tag, snippet):
    html = path.read_text(encoding="utf-8")
    return html.replace(before_tag, snippet + before_tag, 1) if before_tag in html else html + snippet


@app.get("/", include_in_schema=False)
def website(request: Request):
    if not _gate(request):
        return RedirectResponse("/login?next=/", status_code=303)
    return HTMLResponse(_inject(REPO_DIR / "index.html", "</body>", '<script src="/taimi-bridge.js" defer></script>'))


@app.get("/mobile", include_in_schema=False)
def mobile_redirect():
    return RedirectResponse("/mobile/", status_code=307)


@app.get("/mobile/", include_in_schema=False)
def mobile(request: Request):
    if not _gate(request):
        return RedirectResponse("/login?next=/mobile/", status_code=303)
    html = _inject(MOBILE / "index.html", '<script src="data.js"></script>', "<script>window.FIGMENT_USE_BACKEND=true;</script>")
    html = html.replace('<script src="app.js"></script>', '<script src="/taimi-bridge.js"></script><script src="app.js"></script>', 1)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/taimi-bridge.js", include_in_schema=False)
def bridge():
    return FileResponse(STATIC / "taimi-bridge.js", media_type="application/javascript")


app.mount("/src", StaticFiles(directory=str(WEB_SRC)), name="web-src")
app.mount("/mobile", StaticFiles(directory=str(MOBILE)), name="mobile")
