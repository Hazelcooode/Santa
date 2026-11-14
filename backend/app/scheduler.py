"""Deterministic background jobs (not an agent): missed check-ins every minute,
interest research at most every 12 h per active user, due price watches."""
import logging
import threading
from datetime import timedelta

from . import db, exa_client
from .config import settings

log = logging.getLogger("taimi.scheduler")
_stop = threading.Event()


def _active_users():
    since = db.iso(db.now() - timedelta(days=2))
    return db.q("SELECT DISTINCT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.created_at>=? AND u.deleted_at IS NULL", (since,))


def tick():
    from .services import companion, safety, watches
    for u in db.q("SELECT * FROM users WHERE deleted_at IS NULL"):
        try:
            safety.evaluate(u)
        except Exception:
            log.exception("check-in evaluation failed for %s", u["id"])
    if exa_client.effective_mode() != "live":
        return
    for u in _active_users():
        u["preferred_domains"] = db.loads(u.get("preferred_domains"), [])
        try:
            companion.refresh_posts(u)
        except Exception:
            log.exception("interest refresh failed")
    for w in watches.due()[:5]:
        u = db.q1("SELECT * FROM users WHERE id=?", (w["user_id"],))
        if u:
            u["preferred_domains"] = db.loads(u.get("preferred_domains"), [])
            try:
                watches.check(u, w["id"], automatic=True)
            except Exception:
                log.exception("watch check failed")


def _loop():
    while not _stop.wait(settings.scheduler_interval_s):
        try:
            tick()
        except Exception:
            log.exception("scheduler tick failed")


def start():
    if not settings.scheduler_enabled:
        return
    _stop.clear()
    t = threading.Thread(target=_loop, name="taimi-scheduler", daemon=True)
    t.start()


def stop():
    _stop.set()
