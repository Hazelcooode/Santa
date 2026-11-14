"""Home / Today / full-state snapshot in the exact shape of the mobile app's
local state (FigmentAPI.seed()), so a client can hydrate from the server."""
from .. import db
from . import calendar, companion, health, laundry, organiser, safety

DECOS = ["deco-star", "deco-red-ball", "deco-garland", "deco-bell", "deco-candy", "deco-orange-ball"]


def today(user):
    key = calendar.local_now(user).date().isoformat()
    t = db.get_state(user["id"], "today", {"date": None, "done": {}})
    if t.get("date") != key:
        t = {"date": key, "done": {}}
        db.set_state(user["id"], "today", t)
    return t


def mark_done(user, deco):
    if deco not in DECOS:
        from ..errors import ApiError
        raise ApiError(400, "INVALID_INPUT", "Unknown task.")
    t = today(user)
    t["done"][deco] = True
    db.set_state(user["id"], "today", t)
    return t


def dashboard(user):
    items = organiser.list_items(user, include_bought=False)
    lst = laundry.state(user)
    ci = safety.status(user)
    hs = health.summary(user)
    flagged = [e for e in safety.door_events(user, 10) if e["flagged"]]
    return {
        "user": {"name": user["display_name"], "city": user.get("city")},
        "today": today(user),
        "alerts": {"shopping": len([i for i in items if i["prio"] == 1]), "laundry": lst["minRunway"] <= 2,
                   "safety": int(ci["overdue"]) + len(flagged), "health": len(hs["anomalies"])},
        "groceryTrip": organiser.grocery_trip(user),
        "laundry": {"minRunway": lst["minRunway"], "best": lst["best"]},
        "checkin": {"dueAt": ci["dueAt"], "doneToday": ci["doneToday"], "streak": ci["streak"]},
        "health": {"careprompt": hs["careprompt"]},
        "door": flagged[:1],
    }


def _hhmm(user, iso_s):
    return db.parse_iso(iso_s).astimezone(calendar.tz(user)).strftime("%H:%M")


def state(user):
    """Mirror of the mobile prototype's persisted state document."""
    trip = organiser.grocery_trip(user)
    lst = laundry.state(user)
    ci = safety.status(user)
    hs = health.summary(user)
    consent = companion.has_consent(user, "memory")
    return {
        "user": {"id": user["id"], "name": user["display_name"], "city": user.get("city"), "home": user.get("home")},
        "memoryConsent": consent,
        "memories": [{"id": m["id"], "text": m["text"], "tag": m["tag"], "date": m["date"]} for m in companion.memories(user)],
        "devices": [dict(d, last=_hhmm(user, d["last"]) if d["last"] else "—") for d in organiser.devices(user)],
        "contacts": [{"id": c["id"], "name": c["name"], "via": c["via"], "on": bool(c["enabled"]), "police": bool(c["police"]) or None}
                     for c in db.q("SELECT * FROM contacts WHERE user_id=? ORDER BY sort, name", (user["id"],))],
        "social": companion.social(user),
        "checkin": {"every": ci["every"], "grace": ci["grace"], "last": ci["last"], "streak": ci["streak"], "nextHour": ci["nextHour"]},
        "shopping": organiser.list_items(user),
        "groceryTrip": {"day": trip["day"], "start": trip["start"], "end": trip["end"], "booked": trip["booked"]},
        "wardrobe": [{k: w[k] for k in ("cat", "clean", "total", "perDay")} for w in lst["wardrobe"]],
        "basket": [{k: b[k] for k in ("name", "n", "group")} for b in lst["basket"]],
        "laundryBookings": [{"key": b["key"], "label": b["label"]} for b in lst["bookings"]],
        "healthLog": {"hr": hs["series"]["hr"], "sleep": hs["series"]["sleep"], "steps": hs["series"]["steps"]},
        "doorEvents": [{"t": e["t"], "title": e["title"], "kind": e["kind"], "detail": e["detail"]} for e in safety.door_events(user, 6)],
        "today": today(user),
        "chat": [{k: v for k, v in m.items() if k != "at"} for m in companion.history(user, 30)],
        "agentPosts": [{"text": p["text"], "when": p["when"], "sources": p["sources"]} for p in companion.posts(user, 5)],
    }
