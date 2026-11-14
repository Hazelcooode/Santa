"""Sign-in / sign-out / profile / consents / preferences."""
from typing import List, Optional

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from .. import auth, db, exa_client, regions
from ..auth import CurrentUser
from ..config import settings
from ..errors import ApiError
from ..services import companion

router = APIRouter(tags=["account"])

CONSENT_SCOPES = ("memory", "location_trail", "camera_derived_inventory", "health_device", "social_sharing", "calendar")


class LoginIn(BaseModel):
    email: str
    password: str = Field(..., max_length=200)


class RegisterIn(BaseModel):
    email: str = Field(..., max_length=200)
    password: str = Field(..., min_length=8, max_length=200)
    name: str = Field(..., min_length=1, max_length=60)
    city: Optional[str] = None
    country: Optional[str] = Field(None, description="ISO 3166-1 alpha-2, e.g. FI, US")
    timezone: Optional[str] = "UTC"
    home: Optional[str] = None


class PrefsIn(BaseModel):
    name: Optional[str] = None
    home: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None
    currency: Optional[str] = None
    siteRegion: Optional[str] = Field(None, description="Country whose websites agents should search")
    preferredDomains: Optional[List[str]] = Field(None, description="Restrict shopping searches to these sites")
    lat: Optional[float] = None
    lng: Optional[float] = None


def _set_cookie(resp, token, exp):
    resp.set_cookie(auth.COOKIE, token, httponly=True, samesite="lax", secure=settings.cookie_secure,
                    expires=exp.strftime("%a, %d %b %Y %H:%M:%S GMT"), path="/")


def me_payload(user):
    consents = [r["scope"] for r in db.q("SELECT scope FROM consents WHERE user_id=? AND revoked_at IS NULL", (user["id"],))]
    from ..services import media
    from .. import llm
    return {
        "id": user["id"], "email": user["email"], "name": user["display_name"], "home": user.get("home"), "city": user.get("city"),
        "country": user.get("country"), "timezone": user.get("timezone"), "currency": regions.currency(user),
        "siteRegion": user.get("site_region"), "preferredDomains": user.get("preferred_domains") or [],
        "groceryDomains": regions.grocery_domains(user), "consents": consents, "agentName": settings.agent_name,
        "capabilities": {"exa": exa_client.effective_mode(), "cloudinary": media.configured(), "llm": llm.available(),
                         "messaging": "simulated", "payments": "simulated"},
    }


@router.post("/api/v1/auth/login")
def login(body: LoginIn, request: Request, response: Response):
    row = auth.authenticate(body.email, body.password)
    if not row:
        raise ApiError(401, "INVALID_CREDENTIALS", "Email or password is wrong.")
    token, exp = auth.create_session(row["id"], request.headers.get("user-agent"))
    _set_cookie(response, token, exp)
    return {"token": token, "expiresAt": db.iso(exp), "user": me_payload(auth.user_for_token(token))}


@router.post("/api/v1/auth/register", status_code=201)
def register(body: RegisterIn, request: Request, response: Response):
    if "@" not in body.email:
        raise ApiError(400, "INVALID_INPUT", "Enter a valid email.")
    cc = (body.country or "").upper()[:2] or None
    uid = auth.create_user(body.email, body.password, body.name, city=body.city, country=cc, timezone=body.timezone or "UTC",
                           home=body.home, currency=regions.CURRENCY.get(cc or "", "EUR"), site_region=cc)
    from ..seed import DEVICES, SOCIAL
    for key, name, kind, local in DEVICES:
        db.run("INSERT INTO devices(id,user_id,device_key,name,kind,enabled,local_only) VALUES(?,?,?,?,?,?,?)",
               (db.new_id("d_"), uid, key, name, kind, 0, local))
    for name, _handle, _ in SOCIAL:
        db.run("INSERT INTO social_accounts(id,user_id,name,handle,linked) VALUES(?,?,?,?,?)", (db.new_id("s_"), uid, name, "not linked", 0))
    db.run("INSERT INTO contacts(id,user_id,name,via,enabled,police,sort) VALUES(?,?,?,?,?,?,?)",
           (db.new_id("c_"), uid, "Emergency services", "Call + SMS with location", 0, 1, 999))
    token, exp = auth.create_session(uid, request.headers.get("user-agent"))
    _set_cookie(response, token, exp)
    return {"token": token, "expiresAt": db.iso(exp), "user": me_payload(auth.user_for_token(token))}


@router.post("/api/v1/auth/logout")
def logout(request: Request, response: Response):
    auth.destroy_session(auth.token_from_request(request))
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


@router.get("/api/v1/auth/challenge")
def challenge(user=CurrentUser):
    """One-time challenge for fingerprint/Face ID step-up (check-in, SOS, I'm safe)."""
    return auth.issue_challenge(user)


@router.get("/api/v1/me")
def me(user=CurrentUser):
    return me_payload(user)


@router.patch("/api/v1/me/preferences")
def prefs(body: PrefsIn, user=CurrentUser):
    m = {"name": "display_name", "home": "home", "city": "city", "timezone": "timezone", "currency": "currency", "lat": "lat", "lng": "lng"}
    sets, vals = [], []
    data = body.model_dump(exclude_unset=True)
    for k, col in m.items():
        if k in data:
            sets.append(col + "=?")
            vals.append(data[k])
    if "country" in data:
        sets.append("country=?")
        vals.append((data["country"] or "").upper()[:2] or None)
    if "siteRegion" in data:
        sets.append("site_region=?")
        vals.append((data["siteRegion"] or "").upper()[:2] or None)
    if "preferredDomains" in data:
        doms = [exa_client.domain_of(d if "://" in d else "https://" + d) for d in (data["preferredDomains"] or [])]
        sets.append("preferred_domains=?")
        vals.append(db.dumps([d for d in doms if d][:20]))
    if sets:
        db.run("UPDATE users SET %s WHERE id=?" % ", ".join(sets), tuple(vals) + (user["id"],))
    row = db.q1("SELECT * FROM users WHERE id=?", (user["id"],))
    row["preferred_domains"] = db.loads(row["preferred_domains"], [])
    return me_payload(row)


@router.post("/api/v1/consents/{scope}")
def grant(scope: str, user=CurrentUser):
    if scope not in CONSENT_SCOPES:
        raise ApiError(400, "INVALID_INPUT", "Unknown consent scope.")
    return companion.set_consent(user, scope, True)


@router.delete("/api/v1/consents/{scope}")
def revoke(scope: str, user=CurrentUser):
    if scope not in CONSENT_SCOPES:
        raise ApiError(400, "INVALID_INPUT", "Unknown consent scope.")
    if scope == "location_trail":
        db.run("DELETE FROM locations WHERE user_id=?", (user["id"],))
    return companion.set_consent(user, scope, False)


@router.get("/api/v1/usage")
def usage(user=CurrentUser):
    """Exa spend ledger and budget caps (cost transparency)."""
    mine = db.q("SELECT kind, COUNT(*) AS calls, SUM(cached) AS cached, ROUND(SUM(cost_usd),4) AS usd FROM exa_ledger "
                "WHERE user_id=? GROUP BY kind", (user["id"],))
    return {"exa": exa_client.spend_summary(), "mine": mine}


# ---------------------------------------------------------------- HTML pages
LOGIN_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sign in · Taimi</title><style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f7f7f3;font-family:'DM Sans',system-ui,sans-serif;color:#353b35}
.card{background:#fffefa;border:1px solid #e7e8e1;border-radius:18px;padding:32px;width:min(360px,90vw);box-shadow:0 10px 30px rgba(0,0,0,.05)}
h1{font-family:Manrope,system-ui;margin:0 0 4px;font-size:1.8rem}p{margin:0 0 20px;color:#6b6f68}
label{display:block;font-size:.8rem;font-weight:600;margin:12px 0 6px}input{width:100%;box-sizing:border-box;padding:11px 12px;border:1px solid #e7e8e1;border-radius:8px;font:inherit}
button{margin-top:18px;width:100%;padding:12px;border:0;border-radius:8px;background:#353b35;color:#fff;font:inherit;font-weight:700;cursor:pointer}
.err{color:#d6744c;font-size:.85rem;min-height:1.2em;margin-top:10px}.hint{font-size:.8rem;background:#ece8f7;border-radius:8px;padding:10px;margin-top:16px}
.dot{display:inline-block;width:12px;height:12px;border-radius:50%;background:#b8a1d3;margin-right:8px}</style></head><body>
<form class="card" id="f"><h1><span class="dot"></span>Taimi</h1><p>A little help for life on your own.</p>
<label for="e">Email</label><input id="e" name="email" type="email" autocomplete="username" required value="__EMAIL__">
<label for="p">Password</label><input id="p" name="password" type="password" autocomplete="current-password" required>
<button type="submit">Sign in</button><div class="err" id="err" role="alert"></div>
<div class="hint">Demo account: <b>__EMAIL__</b> (password in backend/README.md)</div></form>
<script>
document.getElementById('f').addEventListener('submit',async e=>{e.preventDefault();const err=document.getElementById('err');err.textContent='';
const r=await fetch('/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:e.target.email.value,password:e.target.password.value})});
if(r.ok){const n=new URLSearchParams(location.search).get('next')||'/mobile/';location.href=n.startsWith('/')&&!n.startsWith('//')?n:'/mobile/';}
else{const j=await r.json().catch(()=>({}));err.textContent=(j.error&&j.error.message)||'Sign-in failed';}});
</script></body></html>"""


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page():
    import html
    page = LOGIN_HTML.replace("__EMAIL__", html.escape(settings.test_email if settings.seed_demo_account else ""))
    if not settings.seed_demo_account:
        page = page.replace('<div class="hint">Demo account: <b></b> (password in backend/README.md)</div>', '')
    return HTMLResponse(page.replace('</form>', '<p style="margin-top:15px"><a href="/register">Create a fresh account</a></p></form>'))


@router.get("/logout", include_in_schema=False)
def logout_page(request: Request):
    auth.destroy_session(auth.token_from_request(request))
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(auth.COOKIE, path="/")
    return resp


@router.get("/register", response_class=HTMLResponse, include_in_schema=False)
def register_page():
    page = LOGIN_HTML.replace("__EMAIL__", "")
    page = page.replace('<button type="submit">Sign in</button>', '<label for="n">Name</label><input id="n" name="name" maxlength="60" required><label for="c">City</label><input id="c" name="city" maxlength="100" required><label for="cc">Country code (e.g. FI)</label><input id="cc" name="country" minlength="2" maxlength="2" required><button type="submit">Create account</button>')
    page = page.replace('<div class="hint">Demo account: <b></b> (password in backend/README.md)</div>', '<p style="margin-top:15px"><a href="/login">Already have an account? Sign in</a></p>')
    page = page.replace("fetch('/api/v1/auth/login'", "fetch('/api/v1/auth/register'")
    page = page.replace('JSON.stringify({email:e.target.email.value,password:e.target.password.value})', 'JSON.stringify({email:e.target.email.value,password:e.target.password.value,name:e.target.elements.namedItem("name").value,city:e.target.city.value,country:e.target.country.value.toUpperCase(),timezone:Intl.DateTimeFormat().resolvedOptions().timeZone})')
    return HTMLResponse(page)
