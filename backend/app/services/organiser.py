"""Intelligent life organiser: camera-derived inventory, prioritised shopping
list, multi-strategy price search, online order / printable list and a grocery
run scheduled into a free calendar slot."""
import html
import math
from urllib.parse import urlparse
from datetime import timedelta

from .. import agents, db, mock_data
from ..errors import ApiError
from . import calendar, proposals, shopping_prices

PRIO_LABEL = {1: "Urgent", 2: "This week", 3: "Nice to have"}


# ------------------------------------------------------------------ shopping
def _item(row, user=None):
    qty = row["qty"]
    item = {"id": row["id"], "name": row["name"], "qty": int(qty) if float(qty).is_integer() else qty, "prio": row["prio"],
            "from": row["origin"], "note": row["note"] or "", "bought": row["bought"] or False, "version": row["version"], "brand": row.get("brand") or "", "details": row.get("details") or "", "attributes": db.loads(row.get("attributes"), {})}
    return shopping_prices.attach(user, item) if user else item


def list_items(user, include_bought=True):
    rows = db.q("SELECT * FROM shopping_items WHERE user_id=? ORDER BY prio, created_at", (user["id"],))
    return [_item(r, user) for r in rows if include_bought or not r["bought"]]


def get_item(user, item_id):
    row = db.q1("SELECT * FROM shopping_items WHERE id=? AND user_id=?", (item_id, user["id"]))
    if not row:
        raise ApiError(404, "NOT_FOUND", "Item not found.")
    return row


def add_item(user, name, qty=1, prio=2, origin="you", note=None, regular_id=None, brand="", details="", attributes=None):
    name = " ".join((name or "").split())[:80]
    if not name:
        raise ApiError(400, "INVALID_INPUT", "Item name is required.")
    iid = db.new_id("it_")
    db.run("INSERT INTO shopping_items(id,user_id,name,qty,prio,origin,note,regular_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
           (iid, user["id"], name, max(0.01, float(qty or 1)), int(prio) if int(prio) in (1, 2, 3) else 2, origin,
            note if note is not None else ("Added by you" if origin == "you" else None), regular_id, db.iso()))
    db.run("UPDATE shopping_items SET brand=?,details=?,attributes=? WHERE id=?", ((brand or "")[:100],(details or "")[:400],db.dumps(attributes or {}),iid))
    return _item(get_item(user, iid), user)


def update_item(user, item_id, changes, expected_version=None):
    row = get_item(user, item_id)
    if expected_version is not None and int(expected_version) != row["version"]:
        raise ApiError(409, "VERSION_CONFLICT", "This item changed on another device.", details={"current": _item(row)})
    fields = {}
    if "name" in changes and changes["name"]:
        fields["name"] = " ".join(changes["name"].split())[:80]
    if "qty" in changes and changes["qty"] is not None:
        fields["qty"] = max(0.01, float(changes["qty"]))
    if "prio" in changes and changes["prio"] in (1, 2, 3):
        fields["prio"] = changes["prio"]
    if "note" in changes:
        fields["note"] = (changes["note"] or "")[:200]
    for key in ("brand", "details"):
        if key in changes:
            fields[key] = (changes[key] or "")[:100 if key == "brand" else 400]
    if "attributes" in changes:
        fields["attributes"] = db.dumps(changes["attributes"] or {})
    if "bought" in changes:
        b = changes["bought"]
        fields["bought"] = (b if isinstance(b, str) else db.iso()) if b else None
    if fields:
        sets = ", ".join("%s=?" % k for k in fields) + ", version=version+1"
        cursor = db.run("UPDATE shopping_items SET %s WHERE id=? AND user_id=? AND version=?" % sets, tuple(fields.values()) + (item_id, user["id"], row["version"]))
        if cursor.rowcount != 1:
            raise ApiError(409,"VERSION_CONFLICT","This item changed on another device. Reload before editing.")
    return _item(get_item(user, item_id), user)


def delete_item(user, item_id):
    get_item(user, item_id)
    db.run("DELETE FROM shopping_items WHERE id=? AND user_id=?", (item_id, user["id"]))


# --------------------------------------------------------- camera inventory
def devices(user):
    rows = db.q("SELECT * FROM devices WHERE user_id=? ORDER BY rowid", (user["id"],))
    return [{"id": r["device_key"], "name": r["name"], "kind": r["kind"], "on": bool(r["enabled"]), "last": r["last_seen"],
             "local": bool(r["local_only"])} for r in rows]


def set_device(user, key, enabled):
    db.run("UPDATE devices SET enabled=? WHERE user_id=? AND device_key=?", (1 if enabled else 0, user["id"], key))
    return devices(user)


def frames(device_key):
    fr = mock_data.CAMERA_FRAMES.get(device_key)
    if fr is None:
        raise ApiError(404, "NOT_FOUND", "Unknown device.")
    return fr


def ingest_observation(user, device_key, detections, frame_id=None):
    """Derived detections from the on-device model -> inventory -> shopping list.

    Missing regular items (level 0) become Urgent if they're essentials;
    running low (< min_level) uses the item's usual priority."""
    dev = db.q1("SELECT * FROM devices WHERE user_id=? AND device_key=?", (user["id"], device_key))
    if not dev:
        raise ApiError(404, "NOT_FOUND", "Unknown device.")
    if not dev["enabled"]:
        raise ApiError(409, "DEVICE_PAUSED", "This camera is paused.")
    db.run("INSERT INTO inventory_observations(id,user_id,device_key,frame_id,detections,observed_at) VALUES(?,?,?,?,?,?)",
           (db.new_id("ob_"), user["id"], device_key, frame_id, db.dumps(detections), db.iso()))
    db.run("UPDATE devices SET last_seen=? WHERE id=?", (db.iso(), dev["id"]))
    levels = {d["label"]: float(d.get("level", 1)) for d in detections if "label" in d}
    added, updated = [], []
    for reg in db.q("SELECT * FROM regular_items WHERE user_id=? AND device_key=?", (user["id"], device_key)):
        lvl = levels.get(reg["label"], 0.0 if reg["label"] not in levels and detections else None)
        if lvl is None or lvl >= reg["min_level"]:
            continue
        prio = 1 if (lvl <= 0.01 and reg["prio"] <= 2) else reg["prio"]
        note = "None left" if lvl <= 0.01 else "Running low (~%d%%)" % round(lvl * 100)
        open_row = db.q1("SELECT * FROM shopping_items WHERE user_id=? AND bought IS NULL AND (regular_id=? OR lower(name)=lower(?))",
                         (user["id"], reg["id"], reg["name"]))
        if open_row:
            if prio < open_row["prio"] or note != open_row["note"]:
                db.run("UPDATE shopping_items SET prio=?, note=?, version=version+1 WHERE id=?", (min(prio, open_row["prio"]), note, open_row["id"]))
                updated.append(reg["name"])
            continue
        added.append(add_item(user, reg["name"], 1, prio, device_key, note, reg["id"]))
    return {"device": device_key, "added": added, "updated": updated, "observedAt": db.iso()}


def scan(user, device_key, frame_index=None):
    """Replays the next mocked camera frame (demo stand-in for on-device video)."""
    fr = frames(device_key)
    pos = db.get_state(user["id"], "frame_pos", {})
    idx = (pos.get(device_key, -1) + 1) % len(fr) if frame_index is None else int(frame_index) % len(fr)
    pos[device_key] = idx
    db.set_state(user["id"], "frame_pos", pos)
    frame = fr[idx]
    res = ingest_observation(user, device_key, frame["detections"], frame["id"])
    res["frame"] = {"id": frame["id"], "at": frame["at"], "caption": frame.get("caption"), "detections": frame["detections"],
                    "index": idx, "of": len(fr)}
    return res


def regulars(user):
    return db.q("SELECT id,label,name,device_key AS device,min_level AS minLevel,prio FROM regular_items WHERE user_id=?", (user["id"],))


# --------------------------------------------------------------------- deals
def find_deals(user, strategy="multi", items=None, force_refresh=False, item_ids=None, refresh_id=None, cached_only=False):
    if strategy not in ("multi", "single", "mall", "nearest", "route"):
        raise ApiError(400, "INVALID_INPUT", "strategy must be multi, single, mall, nearest or route.")
    if items is None:
        items = list_items(user, include_bought=False)
    if item_ids is not None:
        items = [i for i in items if i["id"] in item_ids]
    items = [{"brand": i.get("brand") or "", "details": i.get("details") or "", "attributes": i.get("attributes") or {}, "id": str(i.get("id") or ""), "name": str(i.get("name") or "")[:80], "qty": i.get("qty") or 1, "prio": i.get("prio", 2)}
             for i in items if (i.get("name") or "").strip() and not i.get("bought")]
    if any(not math.isfinite(float(i["qty"])) or float(i["qty"]) <= 0 or float(i["qty"]) > 10000 for i in items):
        raise ApiError(400,"INVALID_INPUT","Quantity must be positive and at most 10000.")
    if not items:
        raise ApiError(422, "EMPTY_LIST", "Your list is empty.")
    research_user = shopping_prices.search_user(user,resolve_shops=not cached_only)
    saved_candidates = []
    if not force_refresh:
        for it in items:
            enriched = shopping_prices.attach(user, dict(it))
            for quote in enriched["offers"]:
                if quote["stale"]:
                    continue
                saved_candidates.append({"_identity_verified": True, "key": it["id"], "schema": "price", "url": quote["url"], "domain": urlparse(quote["url"]).hostname.removeprefix("www."),
                    "image": quote.get("image"), "title": quote["product"], "summary": {"product": quote["product"], "price": quote["priceMinor"]/100, "currency": quote["currency"], "store": quote["store"],
                    "price_text": format(quote["priceMinor"]/100, ".2f"), "price_basis": quote.get("priceBasis") or "package",
                    "request_match": "matches", "match_evidence": quote.get('evidence') or quote['product']},
                    "highlights": [quote["evidence"]], "fetchedAt": quote["fetchedAt"], "cached": True})
    quoted_context = shopping_prices.context_hash(user)
    if cached_only:
        research_user=dict(research_user,preferred_domains=sorted({c['domain'] for c in saved_candidates}) or research_user.get('preferred_domains',[]))
        from ..agents import planner,coordinator
        spec=coordinator.plan(research_user,'groceries',{'items':items,'strategy':strategy,'cachedItemIds':[i['id'] for i in items]})
        res=planner.plan_groceries(research_user,spec,{'available':True,'candidates':saved_candidates,'sources':[],'lookups':[]})
        res['notice']='Compared saved quotes only. Unknown items stay unpriced; no new price research was started.'
    else:
        res = agents.run(research_user, "groceries", {"items": items, "strategy": strategy, "forceRefresh": force_refresh, "savedCandidates": saved_candidates, "cachedItemIds": list({c["key"] for c in saved_candidates})})
    shopping_prices.persist_quotes(user, items, res, refresh_id or db.new_id("rf_"), quoted_context)
    res.update(proposals.create(user, "shopping_plan", res, ttl_min=180))
    return res


def _order_executor(user, delivery_fee_per_store=3.9):
    def run(p):
        stores = [{"store": pl["store"]["name"], "items": len(pl["lines"]), "total": pl["total"]} for pl in p.get("plan", [])]
        fee = round(delivery_fee_per_store * len(stores), 2)
        ids = [l["item"]["id"] for pl in p.get("plan", []) for l in pl["lines"]]
        for iid in ids:
            db.run("UPDATE shopping_items SET bought='ordered', version=version+1 WHERE id=? AND user_id=? AND bought IS NULL", (iid, user["id"]))
        slot = (db.now() + timedelta(days=1)).date().isoformat() + " 10:00–12:00"
        bid = db.new_id("bk_")
        payload = {"stores": stores, "deliveryFee": fee, "total": round(p.get("total", 0) + fee, 2), "deliveryWindow": slot,
                   "address": user.get("home"), "simulated": True}
        db.run("INSERT INTO bookings(id,user_id,kind,payload,status,created_at) VALUES(?,?,?,?,?,?)",
               (bid, user["id"], "grocery_order", db.dumps(payload), "placed", db.iso()))
        return dict(payload, orderId=bid, message="Order placed with %d store(s) (simulated checkout)." % len(stores))
    return run


def place_order(user, proposal_id, idem_key=None, expected_version=None, payload_hash=None):
    return proposals.approve(user, proposal_id, idem_key, "grocery_order", _order_executor(user), expected_version, payload_hash)


def printable(user, proposal_id):
    p = proposals.get(user, proposal_id)
    trip = grocery_trip(user)
    rows = []
    for pl in p.get("plan", []):
        for l in pl["lines"]:
            rows.append("<tr><td>☐</td><td>%s%s</td><td>%s</td><td>€%.2f</td></tr>" % (
                ("%s × " % l["qty"]) if l["qty"] != 1 else "", html.escape(l["item"]["name"]), html.escape(pl["store"]["name"]), l["price"] * l["qty"]))
    for u in p.get("unpriced", []):
        rows.append("<tr><td>☐</td><td>%s</td><td>any</td><td>?</td></tr>" % html.escape(u["name"]))
    srcs = "".join('<li><a href="%s">%s</a></li>' % (html.escape(s["url"], quote=True), html.escape(s["title"])) for s in p.get("sources", []))
    return ("<!doctype html><html><head><meta charset='utf-8'><title>Shopping list · Taimi</title><style>body{font-family:system-ui;margin:24px}"
            "table{border-collapse:collapse;width:100%%}td,th{border-bottom:1px solid #ddd;padding:6px;text-align:left}</style></head><body>"
            "<h1>Shopping list</h1><p>Trip: %s %s · estimated €%.2f%s</p><table><thead><tr><th></th><th>Item</th><th>Store</th><th>Price</th></tr>"
            "</thead><tbody>%s</tbody></table><h3>Prices found via Exa</h3><ul>%s</ul><script>window.print&&setTimeout(()=>print(),300)</script></body></html>") % (
        "today" if trip["day"] == "today" else trip["day"], trip["label"], p.get("total", 0),
        " (demo prices)" if p.get("mode") == "demo" else "", "".join(rows), srcs)


# -------------------------------------------------------------- grocery run
def _fmt(h):
    hh = int(h)
    mm = int(round((h - hh) * 60))
    return "%02d:%02d" % (hh, mm)


def grocery_trip(user, duration_min=45):
    trip = db.get_state(user["id"], "grocery_trip")
    today = calendar.local_now(user).date().isoformat()
    if not trip or trip.get("date") != today and not trip.get("booked"):
        slots = calendar.free_slots(user, duration_min, days=2, earliest=12, latest=20.25, step_min=15, limit=4)
        s = slots[0] if slots else {"day": 0, "start": 17.5, "end": 18.25}
        trip = {"date": today, "dayOffset": s["day"], "start": s["start"], "end": round(s["start"] + duration_min / 60, 2), "booked": False}
        db.set_state(user["id"], "grocery_trip", trip)
    off = trip.get("dayOffset", 0)
    start = calendar.at_local(user, off, trip["start"])
    end = calendar.at_local(user, off, trip["end"])
    clashes = [] if trip.get("booked") else calendar.conflicts(user, start, end)
    options = calendar.free_slots(user, duration_min, days=2, earliest=12, latest=20.25, limit=4)
    return {
        "day": "today" if off == 0 else "tomorrow" if off == 1 else "in %d days" % off, "dayOffset": off,
        "start": trip["start"], "end": trip["end"], "booked": bool(trip.get("booked")), "label": "%s–%s" % (_fmt(trip["start"]), _fmt(trip["end"])),
        "startAt": db.iso(start), "endAt": db.iso(end), "conflicts": [e["title"] for e in clashes],
        "options": [{"day": "today" if o["day"] == 0 else "tomorrow", "start": o["start"], "label": ("Today " if o["day"] == 0 else "Tomorrow ") + _fmt(o["start"])} for o in options],
        "calendar": [calendar.public_event(user, e) for e in calendar.events_between(user, calendar.at_local(user, off, 0), calendar.at_local(user, off + 1, 0))],
    }


def set_trip(user, day, start, duration_min=45):
    off = {"today": 0, "tomorrow": 1}.get(day, day if isinstance(day, int) else 0)
    start = max(6.0, min(22.0, float(start)))
    trip = db.get_state(user["id"], "grocery_trip") or {}
    if trip.get("eventId"):
        calendar.delete_event(user, trip["eventId"])
    db.set_state(user["id"], "grocery_trip", {"date": calendar.local_now(user).date().isoformat(), "dayOffset": off, "start": start,
                                              "end": round(start + duration_min / 60, 2), "booked": False})
    return grocery_trip(user)


def book_trip(user):
    t = grocery_trip(user)
    if t["booked"]:
        return t
    eid = calendar.add_event(user, "Grocery run", db.parse_iso(t["startAt"]), db.parse_iso(t["endAt"]), kind="busy", source="taimi")
    trip = db.get_state(user["id"], "grocery_trip")
    trip.update(booked=True, eventId=eid)
    db.set_state(user["id"], "grocery_trip", trip)
    return dict(grocery_trip(user), conflicts=t["conflicts"])
