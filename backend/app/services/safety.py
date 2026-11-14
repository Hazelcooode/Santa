"""Safety: authenticated regular check-ins with escalation, one-tap SOS with
exact location, and front-door monitoring (on-device detection -> events).

Location history is kept only with consent and only since the last confirmed
check-in; a confirmed check-in deletes older points."""
from datetime import timedelta

from .. import auth, db
from ..errors import ApiError
from . import calendar, messaging

SOS_TYPES = ["Medical", "Break-in", "Being followed", "Fire", "Other"]


def _consent(user, scope):
    return bool(db.q1("SELECT 1 FROM consents WHERE user_id=? AND scope=? AND revoked_at IS NULL", (user["id"], scope)))


# ------------------------------------------------------------------ check-in
def config(user):
    return db.get_state(user["id"], "checkin_config", {"every": 24, "grace": 2, "nextHour": 21, "streak": 0})


def set_config(user, every=None, grace=None, next_hour=None):
    c = config(user)
    if every is not None:
        if every not in (12, 24, 48):
            raise ApiError(400, "INVALID_INPUT", "every must be 12, 24 or 48 hours.")
        c["every"] = every
    if grace is not None:
        if grace not in (1, 2, 4):
            raise ApiError(400, "INVALID_INPUT", "grace must be 1, 2 or 4 hours.")
        c["grace"] = grace
    if next_hour is not None:
        c["nextHour"] = max(6, min(23, int(next_hour)))
    db.set_state(user["id"], "checkin_config", c)
    return status(user)


def last_checkin(user):
    return db.q1("SELECT * FROM checkins WHERE user_id=? ORDER BY confirmed_at DESC LIMIT 1", (user["id"],))


def due_at(user):
    c = config(user)
    last = last_checkin(user)
    last_dt = db.parse_iso(last["confirmed_at"]) if last else None
    if c["every"] == 24:
        d = calendar.at_local(user, 0, c["nextHour"])
        if last_dt:
            while d <= last_dt:
                d += timedelta(days=1)
            while d - last_dt > timedelta(hours=36):  # very old check-in: deadline is the next one after it
                d -= timedelta(days=1)
        return d
    base = last_dt or db.parse_iso(db.q1("SELECT created_at FROM users WHERE id=?", (user["id"],))["created_at"])
    return base + timedelta(hours=c["every"])


def trail(user):
    last = last_checkin(user)
    since = last["confirmed_at"] if last else "0000"
    rows = db.q("SELECT at,lat,lng,accuracy_m,label FROM locations WHERE user_id=? AND at>=? ORDER BY at", (user["id"], since))
    for r in rows:
        r["t"] = db.parse_iso(r["at"]).astimezone(calendar.tz(user)).strftime("%H:%M")
        r["p"] = r["label"] or "%.4f, %.4f" % (r["lat"], r["lng"])
    return rows


def status(user):
    c = config(user)
    last = last_checkin(user)
    due = due_at(user)
    today = calendar.local_now(user).date()
    done_today = bool(last and db.parse_iso(last["confirmed_at"]).astimezone(calendar.tz(user)).date() == today)
    open_esc = db.q1("SELECT * FROM escalations WHERE user_id=? AND status='sent' ORDER BY created_at DESC LIMIT 1", (user["id"],))
    return {"every": c["every"], "grace": c["grace"], "nextHour": c["nextHour"], "streak": c.get("streak", 0),
            "last": last["confirmed_at"] if last else None, "doneToday": done_today, "dueAt": db.iso(due),
            "escalateAt": db.iso(due + timedelta(hours=c["grace"])), "overdue": db.now() > due and not done_today,
            "escalation": open_esc, "trail": [{"t": r["t"], "p": r["p"]} for r in trail(user)],
            "recipients": [x["name"] for x in messaging.contacts(user)]}


def checkin(user, verification):
    method = auth.require_verification(user, verification)
    c = config(user)
    last = last_checkin(user)
    now = db.now()
    if last and db.parse_iso(last["confirmed_at"]).astimezone(calendar.tz(user)).date() == calendar.local_now(user).date():
        return dict(status(user), already=True)
    gap_ok = not last or (now - db.parse_iso(last["confirmed_at"])) <= timedelta(hours=c["every"] + c["grace"] + 24)
    c["streak"] = (c.get("streak", 0) + 1) if gap_ok else 1
    db.set_state(user["id"], "checkin_config", c)
    db.run("INSERT INTO checkins(id,user_id,confirmed_at,method) VALUES(?,?,?,?)", (db.new_id("ci_"), user["id"], db.iso(now), method))
    # retention: keep location points only since the last confirmation
    db.run("DELETE FROM locations WHERE user_id=? AND at<?", (user["id"], db.iso(now)))
    for esc in db.q("SELECT * FROM escalations WHERE user_id=? AND status='sent'", (user["id"],)):
        db.run("UPDATE escalations SET status='resolved', resolved_at=? WHERE id=?", (db.iso(), esc["id"]))
        messaging.send(user, messaging.contacts(user), "Update from Taimi: %s just checked in and is okay 💚" % user["display_name"], "escalation", esc["id"])
    return status(user)


def _escalation_message(user, due):
    pts = trail(user)
    last = last_checkin(user)
    lines = ["⚠️ Taimi safety alert", "%s hasn't confirmed their check-in (due %s)." % (
        user["display_name"], due.astimezone(calendar.tz(user)).strftime("%a %H:%M"))]
    lines.append("Last confirmed: %s." % (db.parse_iso(last["confirmed_at"]).astimezone(calendar.tz(user)).strftime("%a %d %b %H:%M") if last else "never"))
    if pts:
        lines.append("Locations since then:")
        lines += ["%s %s (https://maps.google.com/?q=%.5f,%.5f)" % (p["t"], p["p"], p["lat"], p["lng"]) for p in pts[-8:]]
    else:
        lines.append("No location history was shared.")
    lines.append("Please try to reach them.")
    return "\n".join(lines)


def preview_missed(user):
    return {"recipients": [{"name": c["name"], "via": c["via"]} for c in messaging.contacts(user)],
            "message": _escalation_message(user, due_at(user)), "afterHours": config(user)["grace"]}


def evaluate(user, now=None):
    """Called by the scheduler. Sends one escalation per missed deadline."""
    now = now or db.now()
    due = due_at(user)
    grace = timedelta(hours=config(user)["grace"])
    if now <= due + grace:
        return None
    if db.q1("SELECT 1 FROM escalations WHERE user_id=? AND due_at=?", (user["id"], db.iso(due))):
        return None
    eid = db.new_id("es_")
    db.run("INSERT INTO escalations(id,user_id,reason,due_at,created_at,status) VALUES(?,?,?,?,?,?)",
           (eid, user["id"], "missed_checkin", db.iso(due), db.iso(), "sent"))
    sent = messaging.send(user, messaging.contacts(user), _escalation_message(user, due), "escalation", eid)
    return {"id": eid, "dueAt": db.iso(due), "sentTo": sent}


def record_location(user, lat, lng, accuracy=None, label=None, at=None):
    if not _consent(user, "location_trail"):
        raise ApiError(403, "CONSENT_REQUIRED", "Location trail sharing is off.")
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ApiError(400, "INVALID_INPUT", "Invalid coordinates.")
    db.run("INSERT INTO locations(id,user_id,at,lat,lng,accuracy_m,label) VALUES(?,?,?,?,?,?,?)",
           (db.new_id("l_"), user["id"], at or db.iso(), lat, lng, accuracy, (label or "")[:80] or None))
    return {"ok": True}


# ----------------------------------------------------------------------- SOS
def _sos_public(user, row):
    msgs = db.q("SELECT recipient,channel,status,created_at FROM outbox WHERE user_id=? AND related_type='sos' AND related_id=? ORDER BY created_at",
                (user["id"], row["id"]))
    return {"id": row["id"], "at": db.parse_iso(row["at"]).astimezone(calendar.tz(user)).strftime("%H:%M"), "createdAt": row["at"],
            "type": row["type"], "police": bool(row["police"]), "status": row["status"],
            "location": {"lat": row["lat"], "lng": row["lng"], "accuracyM": row["accuracy_m"],
                         "text": ("%.4f° N, %.4f° E · ±%d m" % (row["lat"], row["lng"], row["accuracy_m"] or 10)) if row["lat"] is not None else None},
            "to": [{"name": m["recipient"].split(" <")[0], "via": m["channel"], "status": m["status"]} for m in msgs]}


def sos(user, verification, sos_type=None, location=None, police=False):
    auth.require_verification(user, verification)
    if sos_type and sos_type not in SOS_TYPES:
        sos_type = "Other"
    loc = location or {}
    lat, lng = loc.get("lat", user.get("lat")), loc.get("lng", user.get("lng"))
    acc = loc.get("accuracy", 5 if location else 50)
    sid = db.new_id("sos_")
    db.run("INSERT INTO sos_events(id,user_id,at,type,lat,lng,accuracy_m,police,status) VALUES(?,?,?,?,?,?,?,?,?)",
           (sid, user["id"], db.iso(), sos_type, lat, lng, acc, 1 if police else 0, "active"))
    where = ("https://maps.google.com/?q=%.5f,%.5f (±%d m)" % (lat, lng, acc)) if lat is not None else "location unavailable"
    body = "🆘 SOS from %s via Taimi%s. Exact location: %s. Live location updates every 10 s until they're safe." % (
        user["display_name"], (" (" + sos_type + ")") if sos_type else "", where)
    messaging.send(user, messaging.contacts(user, include_police=False), body, "sos", sid)
    if police:
        police_contacts = [c for c in messaging.contacts(user, include_police=True, only_enabled=False) if c["police"]] or \
                          [{"name": "Emergency services 112", "via": "Call + SMS"}]
        messaging.send(user, police_contacts[:1], body, "sos", sid)
    return _sos_public(user, db.q1("SELECT * FROM sos_events WHERE id=?", (sid,)))


def active_sos(user):
    row = db.q1("SELECT * FROM sos_events WHERE user_id=? AND status='active' ORDER BY at DESC LIMIT 1", (user["id"],))
    return _sos_public(user, row) if row else None


def resolve_sos(user, sos_id, verification):
    auth.require_verification(user, verification)
    row = db.q1("SELECT * FROM sos_events WHERE id=? AND user_id=?", (sos_id, user["id"]))
    if not row:
        raise ApiError(404, "NOT_FOUND", "SOS not found.")
    db.run("UPDATE sos_events SET status='resolved', resolved_at=? WHERE id=?", (db.iso(), sos_id))
    messaging.send(user, messaging.contacts(user), "%s is safe now 💚 (SOS closed)" % user["display_name"], "sos", sos_id)
    return {"ok": True}


# ---------------------------------------------------------------------- door
def door_settings(user):
    return db.get_state(user["id"], "door_settings", {"loiterSeconds": 60, "alerts": True})


def classify(det, settings_):
    person = det.get("person", "none")
    dwell = int(det.get("dwell_s", 0))
    knocked = bool(det.get("knocked"))
    if person == "none":
        return "warn", "Motion, no person", det.get("detail") or "Probably lights or shadows"
    if person == "known":
        return "ok", "%s (known face)" % (det.get("name") or "Known person"), "Walked past"
    if person == "courier":
        return "ok", "Courier — parcel left", "Delivery uniform detected, %d s" % dwell
    if dwell >= settings_["loiterSeconds"] and not knocked:
        extra = ", looked through the peephole %d×" % det["peephole_looks"] if det.get("peephole_looks") else ""
        return "bad", "Unknown person lingered %d min %02d s" % (dwell // 60, dwell % 60), "No knock%s" % extra
    return ("ok" if knocked else "warn"), ("Visitor knocked" if knocked else "Unknown person passed"), "%d s at the door" % dwell


def ingest_door_frame(user, frame, seeded=False):
    s = door_settings(user) if not seeded else {"loiterSeconds": 60, "alerts": True}
    out = []
    for det in frame["detections"]:
        kind, title, detail = classify(det, s)
        at = calendar.at_local(db.q1("SELECT * FROM users WHERE id=?", (user["id"],)) or user, 0,
                               int(frame["at"][:2]) + int(frame["at"][3:5]) / 60) if seeded and "at" in frame else db.now()
        if seeded and at > db.now():
            at -= timedelta(days=1)
        eid = db.new_id("de_")
        db.run("INSERT INTO door_events(id,user_id,at,title,kind,detail,person,dwell_s,knocked) VALUES(?,?,?,?,?,?,?,?,?)",
               (eid, user["id"], db.iso(at), title, kind, detail, det.get("person"), det.get("dwell_s"), 1 if det.get("knocked") else 0))
        out.append({"id": eid, "kind": kind, "title": title, "detail": detail})
    return out


def door_events(user, limit=20):
    rows = db.q("SELECT * FROM door_events WHERE user_id=? ORDER BY at DESC LIMIT ?", (user["id"], limit))
    today = calendar.local_now(user).date()
    out = []
    for r in rows:
        local = db.parse_iso(r["at"]).astimezone(calendar.tz(user))
        out.append({"id": r["id"], "t": local.strftime("%H:%M") if local.date() == today else "Yest. " + local.strftime("%H:%M"),
                    "title": r["title"], "kind": r["kind"], "detail": r["detail"], "reviewed": r["reviewed"],
                    "flagged": r["kind"] == "bad" and not r["reviewed"], "at": r["at"]})
    return out


def review_door(user, event_id, action):
    row = db.q1("SELECT * FROM door_events WHERE id=? AND user_id=?", (event_id, user["id"]))
    if not row:
        raise ApiError(404, "NOT_FOUND", "Event not found.")
    if action not in ("known", "alert", "dismiss"):
        raise ApiError(400, "INVALID_INPUT", "action must be known, alert or dismiss.")
    db.run("UPDATE door_events SET reviewed=?, kind=CASE WHEN ?='known' THEN 'ok' ELSE kind END WHERE id=?", (action, action, event_id))
    sent = []
    if action == "alert":
        local = db.parse_iso(row["at"]).astimezone(calendar.tz(user)).strftime("%H:%M")
        sent = messaging.send(user, messaging.contacts(user), "🚪 Taimi door alert for %s: %s at %s. %s. Clip saved on their phone." % (
            user["display_name"], row["title"], local, row["detail"] or ""), "door", event_id)
    return {"ok": True, "sentTo": sent}


def simulate_door(user):
    from .. import mock_data
    frames = mock_data.CAMERA_FRAMES["door"]
    pos = db.get_state(user["id"], "frame_pos", {})
    idx = (pos.get("door", len(frames) - 1) + 1) % len(frames)
    pos["door"] = idx
    db.set_state(user["id"], "frame_pos", pos)
    frame = frames[idx]
    new = ingest_door_frame(user, {"detections": frame["detections"]})
    return {"frame": frame["id"], "events": new, "alert": any(e["kind"] == "bad" for e in new)}
