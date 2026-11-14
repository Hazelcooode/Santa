"""Calendar + free-slot finder shared by grocery runs, laundry and appointments.

Times are stored in UTC; the user's IANA timezone is used for "today"/"tomorrow"
and the hour-of-day floats the mobile UI uses (17.5 == 17:30)."""
from datetime import datetime, time, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo

from .. import db

# Mirrors the mobile prototype's sample calendar (local hours).
DEMO_CAL = {
    0: [(12.0, 13.0, "Lunch"), (14.0, 16.0, "Study group"), (16.5, 17.25, "Call with Sami"), (18.5, 20.0, "Bouldering")],
    1: [(12.5, 13.5, "Lunch with Emma"), (16.0, 18.0, "Lecture")],
    2: [(10.0, 12.0, "Lecture"), (13.0, 14.0, "Lunch")],
    3: [(9.0, 12.0, "Lab"), (17.0, 18.5, "Bouldering")],
}


def tz(user):
    try:
        return ZoneInfo(user.get("timezone") or "UTC")
    except Exception:
        return timezone.utc


def local_now(user):
    return datetime.now(tz(user))


def at_local(user, day_offset, hour):
    base = local_now(user).date() + timedelta(days=day_offset)
    h = int(hour)
    m = int(round((hour - h) * 60))
    if m == 60:
        h, m = h + 1, 0
    return datetime.combine(base, time(h % 24, m), tzinfo=tz(user)) + timedelta(days=h // 24)


def to_hour(user, dt):
    d = dt.astimezone(tz(user))
    return d.hour + d.minute / 60.0


def day_offset(user, dt):
    return (dt.astimezone(tz(user)).date() - local_now(user).date()).days


def ensure_demo_calendar(user):
    """Keeps the demo account's sample calendar anchored to the current days."""
    if not db.get_state(user["id"], "demo_account"):
        return
    stamp = local_now(user).date().isoformat()
    if db.get_state(user["id"], "demo_calendar_day") == stamp:
        return
    db.run("DELETE FROM calendar_events WHERE user_id=? AND source='demo'", (user["id"],))
    for off, evs in DEMO_CAL.items():
        for s, e, title in evs:
            add_event(user, title, at_local(user, off, s), at_local(user, off, e), source="demo")
    db.set_state(user["id"], "demo_calendar_day", stamp)


def add_event(user, title, start, end, kind="busy", source="taimi"):
    eid = db.new_id("ev_")
    db.run("INSERT INTO calendar_events(id,user_id,title,start_at,end_at,kind,source) VALUES(?,?,?,?,?,?,?)",
           (eid, user["id"], title[:120], db.iso(start), db.iso(end), kind, source))
    return eid


def delete_event(user, event_id):
    db.run("DELETE FROM calendar_events WHERE id=? AND user_id=?", (event_id, user["id"]))


def events_between(user, start, end):
    ensure_demo_calendar(user)
    rows = db.q("SELECT * FROM calendar_events WHERE user_id=? AND end_at>? AND start_at<? ORDER BY start_at",
                (user["id"], db.iso(start), db.iso(end)))
    for r in rows:
        r["start"] = db.parse_iso(r["start_at"])
        r["end"] = db.parse_iso(r["end_at"])
    return rows


def conflicts(user, start, end, ignore_ids=()):
    return [e for e in events_between(user, start, end) if e["id"] not in ignore_ids]


def public_event(user, e):
    return {"id": e["id"], "title": e["title"], "start": e["start_at"], "end": e["end_at"], "kind": e["kind"], "source": e["source"],
            "day": day_offset(user, e["start"]), "s": round(to_hour(user, e["start"]), 2), "e": round(to_hour(user, e["end"]), 2)}


def free_slots(user, duration_min, days=2, earliest=8.0, latest=21.0, step_min=15, limit=8, buffer_min=0):
    """Earliest slots of `duration_min` that don't overlap calendar events, within day windows."""
    out = []
    now = local_now(user)
    for d in range(days):
        h = earliest
        while h + duration_min / 60.0 <= latest + 1e-9:
            s = at_local(user, d, h)
            e = s + timedelta(minutes=duration_min)
            if s > now + timedelta(minutes=10) and not conflicts(user, s - timedelta(minutes=buffer_min), e + timedelta(minutes=buffer_min)):
                out.append({"day": d, "start": round(h, 2), "end": round(h + duration_min / 60.0, 2),
                            "startAt": db.iso(s), "endAt": db.iso(e)})
                if len(out) >= limit:
                    return out
                h += max(duration_min, 60) / 60.0  # spread suggestions out
                continue
            h += step_min / 60.0
    return out
