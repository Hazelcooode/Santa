"""Email + password sign-in with opaque server-side sessions.

Sessions are random tokens; only their SHA-256 is stored. The browser receives an
HttpOnly SameSite=Lax cookie (so the existing same-origin fetch() calls in the
frontends work unchanged); native/mobile clients can send `Authorization: Bearer`.
"""
import hashlib
import hmac
import os
import secrets
from datetime import timedelta

from fastapi import Depends, Request

from . import db
from .config import settings
from .errors import ApiError

COOKIE = "taimi_session"
_ITER = 200_000


def hash_password(pw):
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, _ITER)
    return "pbkdf2_sha256$%d$%s$%s" % (_ITER, salt.hex(), dk.hex())


def verify_password(pw, stored):
    try:
        algo, it, salt, dk = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(calc.hex(), dk)
    except (ValueError, AttributeError):
        return False


def _token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user_id, user_agent=None):
    token = secrets.token_urlsafe(32)
    exp = db.now() + timedelta(days=settings.session_days)
    db.run(
        "INSERT INTO sessions(token_hash,user_id,created_at,expires_at,user_agent) VALUES(?,?,?,?,?)",
        (_token_hash(token), user_id, db.iso(), db.iso(exp), (user_agent or "")[:200]),
    )
    return token, exp


def destroy_session(token):
    if token:
        db.run("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))


def token_from_request(request: Request):
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(COOKIE)


def user_for_token(token):
    if not token:
        return None
    row = db.q1(
        "SELECT u.* , s.expires_at AS s_exp FROM sessions s JOIN users u ON u.id=s.user_id "
        "WHERE s.token_hash=? AND u.deleted_at IS NULL",
        (_token_hash(token),),
    )
    if not row or db.parse_iso(row["s_exp"]) < db.now():
        return None
    row.pop("s_exp", None)
    row.pop("password_hash", None)
    row["preferred_domains"] = db.loads(row.get("preferred_domains"), [])
    return row


def current_user(request: Request):
    user = user_for_token(token_from_request(request))
    if not user:
        raise ApiError(401, "UNAUTHENTICATED", "Please sign in.")
    return user


def optional_user(request: Request):
    return user_for_token(token_from_request(request))


CurrentUser = Depends(current_user)


def authenticate(email, password):
    row = db.q1("SELECT * FROM users WHERE email=? AND deleted_at IS NULL", ((email or "").strip().lower(),))
    if not row or not verify_password(password or "", row["password_hash"]):
        return None
    return row


def create_user(email, password, display_name, **profile):
    email = email.strip().lower()
    if db.q1("SELECT id FROM users WHERE email=?", (email,)):
        raise ApiError(409, "EMAIL_TAKEN", "An account with this email already exists.")
    uid = db.new_id("u_")
    db.run(
        "INSERT INTO users(id,email,password_hash,display_name,home,city,country,timezone,currency,lat,lng,site_region,"
        "preferred_domains,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            uid, email, hash_password(password), display_name,
            profile.get("home"), profile.get("city"), profile.get("country"),
            profile.get("timezone", "UTC"), profile.get("currency", "EUR"),
            profile.get("lat"), profile.get("lng"),
            profile.get("site_region") or profile.get("country"),
            db.dumps(profile.get("preferred_domains") or []), db.iso(),
        ),
    )
    return uid


def require_verification(user, verification):
    """Step-up check for check-ins, SOS and "I'm safe".

    Fingerprint / Face ID run on the device (WebAuthn / platform biometrics);
    the device sends back the one-time challenge it signed. The prototype
    accepts a valid unexpired challenge for biometric methods, or the account
    password. Real deployments must verify the WebAuthn assertion signature.
    """
    verification = verification or {}
    method = verification.get("method", "")
    if method == "password":
        row = db.q1("SELECT password_hash FROM users WHERE id=?", (user["id"],))
        if row and verify_password(verification.get("password", ""), row["password_hash"]):
            return "password"
        raise ApiError(403, "VERIFICATION_FAILED", "That password didn't match.")
    if method in ("fingerprint", "face", "device"):
        challenge = verification.get("challenge", "")
        pending = db.get_state(user["id"], "auth_challenges", [])
        now = db.now()
        valid = [c for c in pending if db.parse_iso(c["exp"]) > now]
        match = [c for c in valid if hmac.compare_digest(c["value"], challenge or "")]
        if match:
            db.set_state(user["id"], "auth_challenges", [c for c in valid if c["value"] != challenge])
            return method
        raise ApiError(403, "VERIFICATION_FAILED", "Biometric confirmation expired. Try again.")
    raise ApiError(400, "VERIFICATION_REQUIRED", "This action needs fingerprint, Face ID or your password.")


def issue_challenge(user):
    value = secrets.token_urlsafe(18)
    exp = db.now() + timedelta(minutes=3)
    pending = [c for c in db.get_state(user["id"], "auth_challenges", []) if db.parse_iso(c["exp"]) > db.now()]
    pending = (pending + [{"value": value, "exp": db.iso(exp)}])[-5:]
    db.set_state(user["id"], "auth_challenges", pending)
    return {"challenge": value, "expiresAt": db.iso(exp), "methods": ["fingerprint", "face", "password"]}
