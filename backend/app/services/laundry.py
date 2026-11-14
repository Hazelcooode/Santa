"""Laundry planner: basket camera (derived counts only) + wardrobe runway ->
wash loads -> reservation in a shared laundry room slot that is free for both
the room and the user's calendar, before clean clothes run out."""
import hashlib
from datetime import timedelta

from .. import db, mock_data
from ..errors import ApiError
from . import calendar

SLOT_TIMES = [8, 11, 14, 17, 20]
SLOT_HOURS = 3
DAYS = 3
LOADS = {
    "darks": {"t": "Darks", "temp": "40 °C", "prog": "Mixed · 1 h 20"},
    "whites": {"t": "Whites & towels", "temp": "60 °C", "prog": "Cotton · 1 h 50"},
    "sport": {"t": "Gym wear", "temp": "30 °C", "prog": "Synthetics · 50 min"},
}
# Mocked building laundry-room booking system (t = taken by a neighbour).
DEMO_ROOM = [["t", "t", "f", "f", "f"], ["f", "f", "f", "f", "f"], ["t", "f", "f", "f", "f"]]


def record_basket(user_id, frame):
    basket = []
    for d in frame["detections"]:
        name, group, _cat = mock_data.BASKET_LABELS.get(d["label"], (d["label"].replace("_", " ").title(), "darks", None))
        basket.append({"name": name, "n": int(d.get("n", 1)), "group": group, "label": d["label"]})
    db.set_state(user_id, "basket", {"items": basket, "seenAt": db.iso(), "frame": frame["id"]})
    db.run("UPDATE devices SET last_seen=? WHERE user_id=? AND device_key='basket'", (db.iso(), user_id))
    return basket


def scan(user, frame_index=None):
    fr = mock_data.CAMERA_FRAMES["basket"]
    pos = db.get_state(user["id"], "frame_pos", {})
    idx = (pos.get("basket", 0) + 1) % len(fr) if frame_index is None else int(frame_index) % len(fr)
    pos["basket"] = idx
    db.set_state(user["id"], "frame_pos", pos)
    record_basket(user["id"], fr[idx])
    return state(user)


def ingest(user, detections):
    record_basket(user["id"], {"id": "device", "detections": detections})
    return state(user)


def runway(w):
    return int(w["clean"] // w["perDay"]) if w.get("perDay") else 99


def _room_status(user, day, si):
    if db.get_state(user["id"], "demo_account") and day < len(DEMO_ROOM):
        return DEMO_ROOM[day][si]
    h = int(hashlib.sha1(("%s%s%s" % (calendar.local_now(user).date(), day, si)).encode()).hexdigest(), 16)
    return "t" if h % 4 == 0 else "f"


def _slot_key(day, si):
    return "%d-%d" % (day, si)


def slots(user):
    now = calendar.local_now(user)
    mine = {b["slot_key"]: b for b in bookings(user, raw=True)}
    grid = []
    for d in range(DAYS):
        for si, t in enumerate(SLOT_TIMES):
            key = _slot_key(d, si)
            s = calendar.at_local(user, d, t)
            e = s + timedelta(hours=SLOT_HOURS)
            if key in mine:
                st = "mine"
            elif _room_status(user, d, si) == "t":
                st = "taken"
            elif s < now:
                st = "past"
            elif calendar.conflicts(user, s, s + timedelta(minutes=30)) or calendar.conflicts(user, e - timedelta(minutes=20), e):
                st = "busy"  # you need to be there to load and unload
            else:
                st = "free"
            grid.append({"key": key, "day": d, "slot": si, "start": t, "end": t + SLOT_HOURS, "status": st,
                         "startAt": db.iso(s), "endAt": db.iso(e)})
    return grid


def state(user):
    wardrobe = db.get_state(user["id"], "wardrobe", [])
    basket = db.get_state(user["id"], "basket", {"items": []})
    essentials = [w for w in wardrobe if w.get("perDay", 0) >= 1] or wardrobe
    min_run = min([runway(w) for w in essentials] or [99])
    groups = {}
    for b in basket["items"]:
        groups.setdefault(b["group"], []).append(b)
    loads = [{"group": g, **LOADS.get(g, {"t": g.title(), "temp": "40 °C", "prog": "Mixed"}),
              "items": [{"name": b["name"], "n": b["n"]} for b in groups[g]]} for g in groups]
    grid = slots(user)
    free = [s for s in grid if s["status"] == "free"]
    # Best: earliest free slot that finishes before essentials run out, preferring evenings.
    deadline_day = max(0, min_run)
    candidates = [s for s in free if s["day"] <= deadline_day] or free
    best = sorted(candidates, key=lambda s: (s["day"], 0 if s["start"] >= 17 else 1, s["start"]))[0] if candidates else None
    total = sum(b["n"] for b in basket["items"])
    return {
        "basket": basket["items"], "basketSeenAt": basket.get("seenAt"), "basketCount": total,
        "fullPct": min(100, round(total / 30 * 100)),
        "wardrobe": [dict(w, runway=runway(w)) for w in wardrobe],
        "minRunway": min_run, "loads": loads,
        "tip": "Gym wear can go with darks at 40 °C if you only get one slot." if len(loads) > 1 else None,
        "slots": grid, "slotTimes": SLOT_TIMES, "best": best["key"] if best else None,
        "bookings": bookings(user),
        "room": "Shared laundry room, building B · 3 h slots, 2 machines",
    }


def bookings(user, raw=False):
    rows = db.q("SELECT * FROM laundry_bookings WHERE user_id=? AND status='booked' ORDER BY slot_start", (user["id"],))
    out = []
    for r in rows:
        s = db.parse_iso(r["slot_start"])
        d = calendar.day_offset(user, s)
        if d < 0 or d >= DAYS:
            if db.parse_iso(r["slot_end"]) < db.now():
                continue
        si = SLOT_TIMES.index(int(calendar.to_hour(user, s))) if int(calendar.to_hour(user, s)) in SLOT_TIMES else 0
        r["slot_key"] = _slot_key(d, si)
        out.append(r if raw else {"id": r["id"], "key": r["slot_key"], "label": r["label"], "start": r["slot_start"],
                                  "end": r["slot_end"], "machine": r["machine"]})
    return out


def book(user, key=None, day=None, slot=None):
    if key:
        try:
            day, slot = [int(x) for x in key.split("-")]
        except ValueError:
            raise ApiError(400, "INVALID_INPUT", "Slot key must look like '1-0'.")
    if day is None or slot is None or not (0 <= day < DAYS and 0 <= slot < len(SLOT_TIMES)):
        raise ApiError(400, "INVALID_INPUT", "Pick a valid slot.")
    cell = next(s for s in slots(user) if s["day"] == day and s["slot"] == slot)
    if cell["status"] != "free":
        raise ApiError(409, "SLOT_UNAVAILABLE", "That slot is %s." % cell["status"])
    t = SLOT_TIMES[slot]
    label = "%s %02d:00–%02d:00" % ("Today" if day == 0 else "Tomorrow" if day == 1 else (calendar.local_now(user) + timedelta(days=day)).strftime("%a"),
                                    t, t + SLOT_HOURS)
    s, e = db.parse_iso(cell["startAt"]), db.parse_iso(cell["endAt"])
    eid = calendar.add_event(user, "Laundry (room B)", s, e, kind="busy", source="taimi")
    bid = db.new_id("lb_")
    db.run("INSERT INTO laundry_bookings(id,user_id,slot_start,slot_end,machine,label,slot_key,status,calendar_event_id,created_at) "
           "VALUES(?,?,?,?,?,?,?,?,?,?)", (bid, user["id"], cell["startAt"], cell["endAt"], "Room B · machine 1", label, cell["key"], "booked", eid, db.iso()))
    return {"id": bid, "key": cell["key"], "label": label, "reminder": "15 min before", "simulatedProvider": True}


def cancel(user, booking_id_or_key):
    rows = bookings(user, raw=True)
    row = next((r for r in rows if r["id"] == booking_id_or_key or r["slot_key"] == booking_id_or_key), None)
    if not row:
        raise ApiError(404, "NOT_FOUND", "Booking not found.")
    db.run("UPDATE laundry_bookings SET status='cancelled' WHERE id=?", (row["id"],))
    if row["calendar_event_id"]:
        calendar.delete_event(user, row["calendar_event_id"])
    return {"ok": True}


def update_wardrobe(user, wardrobe):
    clean = []
    for w in wardrobe[:30]:
        clean.append({"cat": str(w["cat"])[:40], "clean": max(0, int(w["clean"])), "total": max(0, int(w["total"])),
                      "perDay": max(0.0, float(w.get("perDay", 0)))})
    db.set_state(user["id"], "wardrobe", clean)
    return state(user)
