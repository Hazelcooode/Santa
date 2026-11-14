"""Laundry planner: basket camera (derived counts only) + wardrobe runway ->
wash loads -> reservation in a shared laundry room slot that is free for both
the room and the user's calendar, before clean clothes run out."""
import base64
import binascii
import hashlib
import json
import logging
import re
from collections import Counter
from datetime import timedelta

from .. import db, llm, mock_data
from ..errors import ApiError
from . import calendar, companion

log = logging.getLogger("taimi.laundry")

SLOT_TIMES = [8, 11, 14, 17, 20]
SLOT_HOURS = 3
DAYS = 3
LOADS = {
    "darks": {"t": "Darks", "temp": "40 °C", "prog": "Mixed · 1 h 20"},
    "whites": {"t": "Whites & towels", "temp": "60 °C", "prog": "Cotton · 1 h 50"},
    "sport": {"t": "Gym wear", "temp": "30 °C", "prog": "Synthetics · 50 min"},
    "colours": {"t": "Colours", "temp": "40 °C", "prog": "Mixed · 1 h"},
    "delicates": {"t": "Wool & delicates", "temp": "30 °C", "prog": "Wool · 40 min"},
}
CARE_RULES = {
    "whites": "White cotton, underwear and towels: 60 °C for hygiene.",
    "darks": "Dark cotton and denim: 40 °C, inside out, so the colour lasts.",
    "colours": "Bright colours on their own at 40 °C, so dyes can't run onto whites.",
    "sport": "Synthetic gym wear: 30 °C, no fabric softener.",
    "delicates": "Knitwear: 30 °C wool cycle, gentle spin, away from towels so it doesn't pill or felt.",
}
BASKET_CAPACITY = 12  # garments the basket holds before it's time to wash
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
    out = {
        "basket": basket["items"], "basketSeenAt": basket.get("seenAt"), "basketCount": total,
        "fullPct": min(100, round(total / BASKET_CAPACITY * 100)), "capacity": BASKET_CAPACITY,
        "wardrobe": [dict(w, runway=runway(w)) for w in wardrobe],
        "minRunway": min_run, "loads": loads,
        "tip": "Gym wear can go with darks at 40 °C if you only get one slot." if "sport" in groups and len(loads) > 1 else None,
        "slots": grid, "slotTimes": SLOT_TIMES, "best": best["key"] if best else None,
        "bookings": bookings(user),
        "room": "Shared laundry room, building B · 3 h slots, 2 machines",
        "basketSource": basket.get("source", "camera"),
    }
    out["camera"] = camera_info(user)
    out["suggestions"] = suggestions(user, out)
    head = db.get_state(user["id"], "laundry_headline")
    basis = _basis(out["suggestions"])
    out["headline"] = head if head and head.get("basis") == basis else {"text": _default_headline(out["suggestions"]), "by": "rules"}
    return out


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


# ======================================================================
# Basket camera: on-device summaries, a confidence router, the agent's
# second look (only with image consent), evidence
# ======================================================================
# The camera hub runs small vision models locally and sends only formatted
# summaries (labels, colours, confidence, boxes, an image fingerprint).
# Confidence is never shown to the user; a rule-based router uses it:
#   * every item >= ROUTE_CONFIDENCE  -> the on-device result is used;
#   * anything below it               -> if the user allows camera images to
#     leave the device, the photo (checked against its fingerprint) goes to
#     Taimi's agent, which works out what is in the basket; otherwise the
#     on-device result is used and the user is offered the second look.
# Without that consent the user never sees photos or agent results.
IMAGE_CONSENT = "camera_images_off_device"
MAX_IMAGE_BYTES = 600_000
ROUTE_CONFIDENCE = 0.8
LIVE_TRIGGERS = ("new_item", "periodic")
SINGULAR = {"dark_tshirt": "dark T-shirt", "white_tshirt": "white T-shirt", "colour_tshirt": "colour T-shirt", "jeans": "pair of jeans",
            "socks": "pair of socks", "underwear": "pair of underwear", "towel": "towel", "gym_wear": "pair of gym shorts",
            "knitwear": "cardigan or jumper", "joggers": "pair of joggers", "unknown_item": "unrecognised item"}
COLOUR_WORD = {"white": "white", "dark": "dark", "colour": "colour"}
LABELS = list(mock_data.BASKET_LABELS)


def wash_group(label, colour):
    if label == "gym_wear":
        return "sport"
    if label == "knitwear":
        return "delicates"
    if label == "jeans":
        return "whites" if colour == "white" else "darks"
    return {"white": "whites", "dark": "darks"}.get(colour, "colours")


def wardrobe_cat(label):
    return mock_data.BASKET_LABELS.get(label, (None, None, None))[2]


def basket_from_items(items):
    """Garments -> the basket format the frontends already use."""
    agg = {}
    for it in items:
        g = wash_group(it["label"], it["colour"])
        key = (it["label"], g)
        if key not in agg:
            name, default_group, _ = mock_data.BASKET_LABELS.get(it["label"], (it["label"].replace("_", " ").title(), g, None))
            if g != default_group and it["label"] not in ("unknown_item", "colour_tshirt", "knitwear") and g != "sport":
                name = "%s (%s)" % (name, COLOUR_WORD.get(it["colour"], it["colour"]))
            agg[key] = {"name": name, "n": 0, "group": g, "label": it["label"]}
        agg[key]["n"] += 1
    for b in agg.values():  # "1 × Colour T-shirt", "2 × Towels"
        if b["n"] == 1 and re.search(r"(T-shirts|Towels)\b", b["name"]):
            b["name"] = re.sub(r"(T-shirt|Towel)s\b", r"\1", b["name"])
    order = list(LOADS)
    return sorted(agg.values(), key=lambda b: (order.index(b["group"]) if b["group"] in order else 9, b["name"]))


def _obs_rows(uid):
    return db.q("SELECT * FROM laundry_observations WHERE user_id=? ORDER BY captured_at, received_at", (uid,))


def _reviews(uid):
    return {r["frame_id"]: {"items": db.loads(r["items"], []), "by": r["by"], "at": r["created_at"]}
            for r in db.q("SELECT * FROM laundry_agent_reviews WHERE user_id=?", (uid,))}


def needs_second_look(summary):
    """The router's rule: any garment the on-device models were not sure enough about."""
    return any(it["confidence"] < ROUTE_CONFIDENCE or it["label"] == "unknown_item" for it in summary.get("items", []))


def timeline(user):
    """Per frame: the items Taimi uses (agent's if it took a second look and images are
    allowed, else the device's) and the basket inventory. Garments get buried under
    newer ones, so a garment counts until the basket is seen empty again."""
    uid = user["id"]
    allowed = companion.has_consent(user, IMAGE_CONSENT)
    reviews = _reviews(uid) if allowed else {}
    out, inv = [], Counter()
    for r in _obs_rows(uid):
        s = db.loads(r["summary"], {})
        rev = reviews.get(r["frame_id"])
        items = rev["items"] if rev else s.get("items", [])
        seen = Counter((it["label"], it["colour"]) for it in items)
        before = inv
        inv = Counter() if not seen else before | seen   # | = per-garment max (occlusion-aware)
        out.append({"row": r, "summary": s, "items": items, "source": "agent" if rev else "device",
                    "secondLook": needs_second_look(s), "inventory": inv, "added": inv - before, "removed": before - inv})
    return out


def _refresh(user, tl=None):
    """Derive basket + wardrobe from the timeline (after new summaries, a review, or a consent change)."""
    uid = user["id"]
    tl = tl if tl is not None else timeline(user)
    if tl:
        last = tl[-1]
        items = [{"label": l, "colour": c} for (l, c), n in sorted(last["inventory"].items()) for _ in range(n)]
        db.set_state(uid, "basket", {"items": basket_from_items(items), "seenAt": last["row"]["captured_at"],
                                     "frame": last["row"]["frame_id"], "source": last["source"]})
        db.run("UPDATE devices SET last_seen=? WHERE user_id=? AND device_key='basket'", (last["row"]["captured_at"], uid))
    _sync_worn(user, tl)


def _sync_worn(user, tl):
    """A garment that newly appears in the basket (live capture, not history) was worn:
    one fewer clean in the wardrobe. Re-derived each time so corrections carry through."""
    uid = user["id"]
    want = {}
    for f in tl:
        if f["row"]["trigger"] not in LIVE_TRIGGERS:
            continue
        for (label, _c), n in f["added"].items():
            cat = wardrobe_cat(label)
            if cat:
                k = (f["row"]["frame_id"], label)
                want[k] = {"at": f["row"]["captured_at"], "frameId": k[0], "label": label, "cat": cat, "n": want.get(k, {}).get("n", 0) + n}
    have = {(x["frameId"], x["label"]): x for x in db.get_state(uid, "laundry_worn", [])}
    wardrobe = db.get_state(uid, "wardrobe", [])
    for k in set(want) | set(have):
        delta = want.get(k, {}).get("n", 0) - have.get(k, {}).get("n", 0)
        cat = (want.get(k) or have.get(k))["cat"]
        w = next((w for w in wardrobe if w["cat"] == cat), None)
        if delta and w:
            w["clean"] = max(0, min(w["total"], w["clean"] - delta))
    db.set_state(uid, "wardrobe", wardrobe)
    db.set_state(uid, "laundry_worn", sorted(want.values(), key=lambda x: x["at"])[-50:])


def ingest_observations(user, observations, reset=False):
    """Store on-device summaries (already schema-validated) and update the basket."""
    uid = user["id"]
    now = db.now()
    for o in observations:
        at = o["capturedAt"]
        if at > now + timedelta(minutes=5) or at < now - timedelta(days=7):
            raise ApiError(400, "INVALID_INPUT", "capturedAt must be within the last 7 days.")
    if reset:
        _sync_worn(user, [])  # give back what the camera counted as worn
        for t in ("laundry_observations", "laundry_frame_images", "laundry_agent_reviews"):
            db.run("DELETE FROM %s WHERE user_id=?" % t, (uid,))
    inserted = []
    for o in sorted(observations, key=lambda x: x["capturedAt"]):
        if db.q1("SELECT 1 FROM laundry_observations WHERE user_id=? AND frame_id=?", (uid, o["frameId"])):
            continue
        summary = dict(o, capturedAt=db.iso(o["capturedAt"]))
        db.run("INSERT INTO laundry_observations(id,user_id,frame_id,captured_at,trigger,summary,image_sha256,received_at) VALUES(?,?,?,?,?,?,?,?)",
               (db.new_id("lo_"), uid, o["frameId"], summary["capturedAt"], o["trigger"], db.dumps(summary), o["imageSha256"], db.iso()))
        inserted.append(summary)
    _refresh(user)
    st = state(user)
    if inserted:
        _refresh_headline(user, st)
        st = state(user)
    return st


def _route(f, allowed, have_image):
    if not f["summary"].get("items"):
        return "device"
    if not f["secondLook"]:
        return "device"           # the camera was sure
    if f["source"] == "agent":
        return "agent"
    if not allowed:
        return "device-private"   # photos stay home, so the device's result stands
    return "agent-pending" if have_image and llm.available() else "device"


def camera_info(user):
    uid = user["id"]
    allowed = companion.has_consent(user, IMAGE_CONSENT)
    have = {r["frame_id"] for r in db.q("SELECT frame_id FROM laundry_frame_images WHERE user_id=?", (uid,))} if allowed else set()
    tl = timeline(user)
    frames = []
    for f in tl:
        r, fid = f["row"], f["row"]["frame_id"]
        frame = {
            "frameId": fid, "capturedAt": r["captured_at"], "trigger": r["trigger"], "itemCount": sum(f["inventory"].values()),
            "visible": len(f["items"]), "source": f["source"], "route": _route(f, allowed, fid in have),
            "added": [{"label": l, "colour": c, "n": n, "name": SINGULAR.get(l, l)} for (l, c), n in sorted(f["added"].items())],
            "removed": [{"label": l, "colour": c, "n": n, "name": SINGULAR.get(l, l)} for (l, c), n in sorted(f["removed"].items())],
            "model": f["summary"].get("model"), "processingMs": f["summary"].get("processingMs"), "imageSha256": r["image_sha256"],
            "image": None, "boxes": [],
        }
        if allowed and fid in have:   # evidence: the photo + what was recognised where (no confidence)
            frame["image"] = "/api/v1/laundry/frames/%s/image" % fid
            frame["boxes"] = [{"label": it["label"], "name": SINGULAR.get(it["label"], it["label"]), "colour": it["colour"],
                               "bbox": it.get("bbox"), "by": f["source"]} for it in f["items"] if it.get("bbox")]
        frames.append(frame)
    last = tl[-1] if tl else None
    return {
        "frames": frames[-24:], "model": last["summary"].get("model") if last else None,
        "imagesAllowed": allowed, "imagesUploaded": len(have), "consentScope": IMAGE_CONSENT,
        "secondLookNeeded": bool(last and last["secondLook"] and last["source"] != "agent"),
        "agentAvailable": llm.available(),
        "privacy": "The camera's own models look at each photo on your device and Taimi gets only a summary. "
                   "Photos leave the device only if you allow it.",
    }


def _frames_with(camera, pred, limit=6):
    hits = [f["frameId"] for f in camera["frames"] if any(pred(a) for a in f["added"])]
    return hits[-limit:]


def _day_label(d):
    return "today" if d <= 0 else "tomorrow" if d == 1 else "in %d days" % d


def suggestions(user, st):
    """Advice for the user, each with the evidence it is based on."""
    cam, out = st["camera"], []
    wardrobe = st["wardrobe"]
    worn = db.get_state(user["id"], "laundry_worn", [])
    cam_source = "Basket camera (models run on your device)"

    # 1. Wardrobe runway: what runs out first.
    essentials = sorted([w for w in wardrobe if w.get("perDay", 0) >= 1] or wardrobe, key=lambda w: w["runway"])
    if essentials:
        w = essentials[0]
        labels = [l for l, v in mock_data.BASKET_LABELS.items() if v[2] == w["cat"]]
        recent = [x for x in worn if x["cat"] == w["cat"]][-3:]
        out.append({
            "id": "runway", "kind": "runway", "tone": "urgent" if w["runway"] <= 2 else "info",
            "title": "Wash before %s runs out %s" % (w["cat"].lower(), _day_label(w["runway"])),
            "detail": "%d of %d clean and you use about %s a day." % (w["clean"], w["total"], ("%g" % w["perDay"])),
            "evidence": {
                "why": "Days left = clean items ÷ items used per day, for everyday items.",
                "facts": [{"label": x["cat"], "value": "%d/%d clean · %s a day" % (x["clean"], x["total"], "%g" % x["perDay"])} for x in essentials[:4]] +
                         [{"label": "Camera update", "value": "−%d clean %s (seen %s)" % (x["n"], x["cat"].lower(), x["at"])} for x in recent],
                "frames": _frames_with(cam, lambda a: a["label"] in labels, 3),
                "sources": ["Your wardrobe counts", cam_source],
                "rules": ["Runway = floor(clean ÷ per day)."],
            },
        })

    # 2. One load per wash group.
    for i, ld in enumerate(st["loads"]):
        g = ld["group"]
        items = [b for b in st["basket"] if b["group"] == g]
        out.append({
            "id": "load-" + g, "kind": "load", "tone": "info",
            "title": "Load %d: %s · %s" % (i + 1, ld["t"], ld["temp"]),
            "detail": "%s · %s" % (", ".join("%d %s" % (b["n"], b["name"].lower()) for b in items), ld["prog"]),
            "evidence": {"why": "Grouped by garment type and colour, and the care rule for that group.",
                         "facts": [{"label": b["name"], "value": "%d in the basket" % b["n"]} for b in items],
                         "frames": _frames_with(cam, lambda a, g=g: wash_group(a["label"], a["colour"]) == g),
                         "sources": [cam_source], "rules": [CARE_RULES.get(g, "Mixed load at 40 °C.")]},
        })

    groups = {b["group"] for b in st["basket"]}
    # 3. Care: colour next to whites; knitwear.
    if "colours" in groups and "whites" in groups:
        out.append({
            "id": "colours", "kind": "care", "tone": "info", "title": "Keep the colour item out of the whites",
            "detail": "Wash it with colours at 40 °C.",
            "evidence": {"why": "New coloured fabrics can bleed dye at 60 °C.", "facts": [],
                         "frames": _frames_with(cam, lambda a: wash_group(a["label"], a["colour"]) == "colours", 3),
                         "sources": [cam_source], "rules": [CARE_RULES["colours"]]},
        })
    if "delicates" in groups:
        out.append({
            "id": "knitwear", "kind": "care", "tone": "info", "title": "Knitwear on the wool cycle",
            "detail": "30 °C, gentle spin, and not with the towels.",
            "evidence": {"why": "Hot water and rough company make knits shrink and pill.", "facts": [],
                         "frames": _frames_with(cam, lambda a: a["label"] == "knitwear", 3),
                         "sources": [cam_source], "rules": [CARE_RULES["delicates"]]},
        })

    # 4. The laundry-room slot.
    best = next((s for s in st["slots"] if s["key"] == st["best"]), None)
    if best:
        statuses = Counter(s["status"] for s in st["slots"])
        label = "%s %02d:00–%02d:00" % (_day_label(best["day"]).capitalize(), best["start"], best["end"])
        out.append({
            "id": "slot", "kind": "slot", "tone": "info", "slotKey": best["key"],
            "title": "Book %s" % label,
            "detail": "The room is free, your calendar is free at the start and end, and it's before you run out.",
            "evidence": {
                "why": "Earliest slot that is free for both you and the room, before your first item runs out, preferring evenings.",
                "facts": [{"label": "Runs out", "value": _day_label(st["minRunway"])},
                          {"label": "Slots in the next 3 days", "value": "%d free for both · %d taken · %d clash with your calendar" % (statuses["free"], statuses["taken"], statuses["busy"])}],
                "frames": [], "sources": ["Laundry room booking grid (simulated)", "Your calendar"],
                "rules": ["You need 30 min free at the start (loading) and 20 min at the end (unloading)."],
            },
        })

    # 5. Basket fullness.
    if st["fullPct"] >= 75:
        out.append({
            "id": "full", "kind": "fullness", "tone": "urgent" if st["fullPct"] >= 90 else "info",
            "title": "Basket is %d%% full" % st["fullPct"],
            "detail": "%d items in a basket that holds about %d." % (st["basketCount"], BASKET_CAPACITY),
            "evidence": {"why": "Garments seen since the basket was last empty.", "facts": [],
                         "frames": [f["frameId"] for f in cam["frames"]][-1:], "sources": [cam_source], "rules": []},
        })

    # 6. The camera wasn't sure and photos stay home: offer the agent's second look.
    if cam["secondLookNeeded"] and not cam["imagesAllowed"]:
        out.append({
            "id": "second-look", "kind": "check", "tone": "info",
            "title": "Some pieces are hard to tell apart",
            "detail": "Allow the photos to leave your device and Taimi's agent will take a second look.",
            "evidence": {"why": "Overlapping clothes are hard for the small on-device models.", "facts": [], "frames": [],
                         "sources": [cam_source], "rules": []},
        })
    return out


def _basis(sugs):
    return hashlib.sha1(db.dumps([(s["title"], s["detail"]) for s in sugs]).encode()).hexdigest()[:16]


def _default_headline(sugs):
    if not sugs:
        return "Nothing to wash yet."
    top = next((s for s in sugs if s["tone"] == "urgent"), sugs[0])
    slot = next((s for s in sugs if s["kind"] == "slot"), None)
    return top["title"] + (". " + slot["title"] + "." if slot and slot is not top else ".")


def _refresh_headline(user, st):
    """One friendly sentence from the agent's model, built only from the computed advice."""
    sugs = st["suggestions"]
    text, by = None, "rules"
    if llm.available() and sugs:
        facts = [{"title": s["title"], "detail": s["detail"]} for s in sugs[:5]]
        text = llm.complete(
            "You are Taimi, a warm, concise personal assistant. Write ONE sentence (max 28 words) telling the user the most "
            "important laundry step right now. Use only the facts given; do not add numbers, days or items that are not in them.",
            [("user", json.dumps(facts, ensure_ascii=False))], max_tokens=1024)
        if text:
            text, by = " ".join(text.split())[:240], llm.model_name()
    db.set_state(user["id"], "laundry_headline", {"text": text or _default_headline(sugs), "by": by, "basis": _basis(sugs)})


# ----------------------------------------------------------- the agent's second look
REVIEW_SCHEMA = llm.obj({"items": {"type": "array", "items": llm.obj({
    "label": {"type": "string", "enum": LABELS},
    "colour": {"type": "string", "enum": ["white", "dark", "colour"]},
    "bbox": {"type": "array", "items": {"type": "number"}},
})}})
REVIEW_PROMPT = (
    "You are Taimi's laundry agent. You get one photo from the user's laundry-basket camera, taken from above, and what the "
    "small on-device models thought they saw (they were unsure). List every garment visible in the basket, including ones "
    "partly covered by others. Ignore the basket itself. For each give: label (dark_tshirt / white_tshirt / colour_tshirt by "
    "the T-shirt's colour; knitwear for cardigans and jumpers; joggers for sweatpants and track pants; jeans only for denim; "
    "gym_wear for sports shorts and leggings; unknown_item if you can't tell), colour family (white = white, cream or light "
    "grey; dark = black, navy, charcoal, dark denim; colour = anything else) and bbox = [x, y, width, height] as fractions of "
    "the image. Count each physical garment once.")


def _agent_review(user, f, data_url):
    hints = [{"label": it["label"], "colour": it["colour"], "bbox": it.get("bbox")} for it in f["summary"].get("items", [])]
    out = llm.complete(REVIEW_PROMPT, [("user", "On-device guess: " + json.dumps(hints))], schema=REVIEW_SCHEMA,
                       image_data_url=data_url, max_tokens=2048)
    if not out or not isinstance(out.get("items"), list):
        return None
    items = []
    for it in out["items"][:30]:
        if it.get("label") not in mock_data.BASKET_LABELS or it.get("colour") not in COLOUR_WORD:
            continue
        b = [min(1.0, max(0.0, float(v))) for v in (it.get("bbox") or [])[:4]]
        items.append({"label": it["label"], "colour": it["colour"], "bbox": [round(v, 3) for v in b] if len(b) == 4 else None})
    return items


def route_frame(user, frame_id, data_url=None):
    """The router: only frames the device wasn't sure about, only with consent, go to the agent."""
    uid = user["id"]
    f = next((x for x in timeline(user) if x["row"]["frame_id"] == frame_id), None)
    if not f or not f["summary"].get("items") or not f["secondLook"]:
        return {"route": "device", "reason": "sure"}
    if f["source"] == "agent":
        return {"route": "agent", "reason": "done"}
    if not companion.has_consent(user, IMAGE_CONSENT):
        return {"route": "device", "reason": "private"}
    if not llm.available():
        return {"route": "device", "reason": "agent-unavailable"}
    if data_url is None:
        row = db.q1("SELECT mime, data FROM laundry_frame_images WHERE user_id=? AND frame_id=?", (uid, frame_id))
        if not row:
            return {"route": "device", "reason": "no-image"}
        data_url = "data:%s;base64,%s" % (row["mime"], base64.b64encode(bytes(row["data"])).decode())
    items = _agent_review(user, f, data_url)
    if items is None:
        return {"route": "device", "reason": "agent-failed"}
    db.run("INSERT OR REPLACE INTO laundry_agent_reviews(user_id,frame_id,items,by,created_at) VALUES(?,?,?,?,?)",
           (uid, frame_id, db.dumps(items), llm.model_name(), db.iso()))
    _refresh(user)
    _refresh_headline(user, state(user))
    return {"route": "agent", "reason": "reviewed", "items": len(items)}


def upload_image(user, frame_id, data_url):
    if not companion.has_consent(user, IMAGE_CONSENT):
        raise ApiError(403, "CONSENT_REQUIRED", "Allow camera images to leave your device first.")
    row = db.q1("SELECT image_sha256 FROM laundry_observations WHERE user_id=? AND frame_id=?", (user["id"], frame_id))
    if not row:
        raise ApiError(404, "NOT_FOUND", "No summary was received for this frame.")
    m = re.match(r"data:(image/(?:jpeg|png));base64,([A-Za-z0-9+/=\s]+)$", data_url or "")
    if not m:
        raise ApiError(400, "INVALID_INPUT", "Send a JPEG or PNG data URL.")
    try:
        raw = base64.b64decode(m.group(2), validate=False)
    except (binascii.Error, ValueError):
        raise ApiError(400, "INVALID_INPUT", "Image data is not valid base64.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ApiError(413, "PAYLOAD_TOO_LARGE", "Image is too large.")
    if hashlib.sha256(raw).hexdigest() != row["image_sha256"]:
        raise ApiError(422, "IMAGE_MISMATCH", "This image is not the one the on-device model analysed for this frame.")
    db.run("INSERT OR REPLACE INTO laundry_frame_images(user_id,frame_id,mime,data,uploaded_at) VALUES(?,?,?,?,?)",
           (user["id"], frame_id, m.group(1), raw, db.iso()))
    return {"frameId": frame_id, "stored": True, "bytes": len(raw), "route": route_frame(user, frame_id, data_url)}


def get_image(user, frame_id):
    if not companion.has_consent(user, IMAGE_CONSENT):
        raise ApiError(403, "CONSENT_REQUIRED", "Camera images stay on your device.")
    row = db.q1("SELECT mime, data FROM laundry_frame_images WHERE user_id=? AND frame_id=?", (user["id"], frame_id))
    if not row:
        raise ApiError(404, "NOT_FOUND", "This image has not left the device.")
    return row["mime"], bytes(row["data"])


def forget_images(user):
    """Consent withdrawn: delete the photos and everything the agent derived from them."""
    db.run("DELETE FROM laundry_frame_images WHERE user_id=?", (user["id"],))
    db.run("DELETE FROM laundry_agent_reviews WHERE user_id=?", (user["id"],))
    _refresh(user)
