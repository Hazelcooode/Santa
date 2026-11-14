"""Health: wearable data, caring anomaly check-ins, OTC medicine search and
delivery, appointment suggestions from free calendar time, and rides to care.

Not a medical device: only non-prescription products are suggested, red-flag
symptoms point to emergency services, and anomaly rules are simple and
explainable."""
from datetime import timedelta

from .. import agents, db, exa_client
from ..errors import ApiError
from . import calendar, proposals

RED_FLAGS = ("chest pain", "can't breathe", "cannot breathe", "trouble breathing", "fainted", "fainting", "stroke", "severe bleeding",
             "overdose", "suicid")


def vitals(user, days=7):
    rows = db.q("SELECT day,hr,sleep,steps FROM vitals WHERE user_id=? ORDER BY day DESC LIMIT ?", (user["id"], days))
    rows.reverse()
    return rows


def ingest_vitals(user, samples):
    n = 0
    for s in samples[:400]:
        day = str(s.get("day") or s.get("date") or "")[:10]
        if len(day) != 10:
            continue
        db.run("INSERT INTO vitals(user_id,day,hr,sleep,steps) VALUES(?,?,?,?,?) ON CONFLICT(user_id,day) DO UPDATE SET "
               "hr=COALESCE(excluded.hr,hr), sleep=COALESCE(excluded.sleep,sleep), steps=COALESCE(excluded.steps,steps)",
               (user["id"], day, s.get("hr"), s.get("sleep"), s.get("steps")))
        n += 1
    db.run("UPDATE devices SET last_seen=? WHERE user_id=? AND device_key='watch'", (db.iso(), user["id"]))
    return {"stored": n, "summary": summary(user)}


def anomalies(series):
    out = []
    hr = [r["hr"] for r in series if r.get("hr")]
    sl = [r["sleep"] for r in series if r.get("sleep") is not None]
    st = [r["steps"] for r in series if r.get("steps") is not None]
    if len(hr) >= 5:
        base = sum(hr[:4]) / 4
        if hr[-1] > base * 1.1:
            out.append({"type": "resting_hr_up", "text": "Resting heart rate %d bpm vs your usual %d" % (hr[-1], round(base)), "severity": "watch"})
    short = 0
    for v in reversed(sl):
        if v < 6:
            short += 1
        else:
            break
    if short >= 3:
        out.append({"type": "short_sleep", "text": "Under 6 h of sleep for %d nights" % short, "severity": "watch"})
    if len(st) >= 5 and st[-1] < 0.5 * (sum(st[:4]) / 4):
        out.append({"type": "low_activity", "text": "Much less movement than usual", "severity": "info"})
    return out


def summary(user):
    s = vitals(user)
    a = anomalies(s)
    prompt = None
    if a:
        bits = [x["text"].lower() for x in a[:2]]
        prompt = "Hey, I noticed %s. How are you feeling?" % " and ".join(bits)
    return {"series": {"hr": [r["hr"] for r in s], "sleep": [r["sleep"] for r in s], "steps": [r["steps"] for r in s],
                       "days": [r["day"] for r in s]},
            "latest": s[-1] if s else None, "anomalies": a, "careprompt": prompt,
            "moods": [{"id": "great", "t": "Actually great"}, {"id": "tired", "t": "Tired"}, {"id": "stressed", "t": "Stressed"}, {"id": "unwell", "t": "A bit unwell"}]}


def wellbeing(user, mood):
    if mood not in ("great", "tired", "stressed", "unwell"):
        mood = "tired"
    db.set_state(user["id"], "last_mood", {"mood": mood, "at": db.iso()})
    return agents.run(user, "wellbeing", {"mood": mood})


def find_medicine(user, symptom):
    s = (symptom or "").strip()[:120]
    if not s:
        raise ApiError(400, "INVALID_INPUT", "Tell me the symptom or medicine.")
    if any(f in s.lower() for f in RED_FLAGS):
        return {"results": [], "urgent": True, "mode": "safety",
                "message": "That sounds like it needs urgent care. Please call your local emergency number (112 in Europe) now."}
    res = agents.run(user, "medicine", {"query": s})
    res.update(proposals.create(user, "medicine_options", res, ttl_min=120))
    return res


def order_medicine(user, proposal_id, index, idem_key=None):
    p = proposals.get(user, proposal_id)
    items = p.get("results", [])
    if not (0 <= int(index) < len(items)):
        raise ApiError(400, "INVALID_INPUT", "Pick one of the listed products.")

    def run(prop):
        m = prop["results"][int(index)]
        fee = 4.9
        payload = {"item": m["name"], "pharmacy": m["pharmacy"], "price": m["price"], "deliveryFee": fee,
                   "total": round((m["price"] or 0) + fee, 2), "eta": m.get("eta"), "address": user.get("home"), "simulated": True,
                   "note": "Payment and pharmacist questions happen in the pharmacy's own checkout."}
        bid = db.new_id("bk_")
        db.run("INSERT INTO bookings(id,user_id,kind,payload,status,created_at) VALUES(?,?,?,?,?,?)",
               (bid, user["id"], "medicine_order", db.dumps(payload), "placed", db.iso()))
        return dict(payload, orderId=bid)
    return proposals.approve(user, proposal_id, idem_key or "%s:%s" % (proposal_id, index), "medicine_order", run, extra=int(index))


def appointment_suggestions(user):
    """Free slots in the next days that fit a GP visit, plus a remote option."""
    slots = calendar.free_slots(user, 60, days=4, earliest=8, latest=17, limit=6, buffer_min=30)
    clinics = []
    if user.get("city"):
        r = exa_client.search(user["id"], "places", "health centre general practitioner appointment booking %s" % user["city"],
                              num_results=4, user_location=user.get("country"))
        clinics = [{"name": x["title"][:80], "url": x["url"]} for x in r["results"]][:3]
    if not clinics:
        clinics = [{"name": "Kallio Health Centre (GP)", "url": "https://www.hel.fi/"}, {"name": "Mehiläinen Ruoholahti", "url": "https://www.mehilainen.fi/"}]
    out = []
    picks = [slots[0], slots[len(slots) // 2]] if len(slots) > 1 else slots
    for i, sl in enumerate(picks):
        dt = db.parse_iso(sl["startAt"]).astimezone(calendar.tz(user))
        out.append({"id": "a%d" % (i + 1), "when": dt.strftime("%a %d · %H:%M").replace(" 0", " "), "startAt": sl["startAt"], "endAt": sl["endAt"],
                    "where": clinics[i % len(clinics)]["name"], "url": clinics[i % len(clinics)]["url"],
                    "why": "Your calendar is free then (with 30 min travel buffer)"})
    out.append({"id": "a%d" % (len(out) + 1), "when": "Today · video", "startAt": None, "where": "Online nurse chat",
                "why": "No travel, short wait", "url": None})
    db.set_state(user["id"], "appt_suggestions", out)
    return {"suggestions": out, "sources": clinics}


def book_appointment(user, suggestion_id):
    sug = next((s for s in db.get_state(user["id"], "appt_suggestions", []) if s["id"] == suggestion_id), None)
    if not sug:
        raise ApiError(404, "NOT_FOUND", "Suggestion expired. Refresh the list.")
    eid = None
    if sug.get("startAt"):
        eid = calendar.add_event(user, "Doctor: " + sug["where"], db.parse_iso(sug["startAt"]), db.parse_iso(sug["endAt"]), source="taimi")
    bid = db.new_id("bk_")
    payload = dict(sug, calendarEventId=eid, simulated=True)
    db.run("INSERT INTO bookings(id,user_id,kind,payload,status,created_at) VALUES(?,?,?,?,?,?)",
           (bid, user["id"], "appointment", db.dumps(payload), "booked", db.iso()))
    return dict(payload, bookingId=bid)


def ride_options(user):
    city = user.get("city") or ""
    r = exa_client.search(user["id"], "places", "hospital emergency department %s address" % city, num_results=4, user_location=user.get("country"))
    dests = [{"n": x["title"][:60], "url": x["url"]} for x in r["results"]][:2]
    if not dests:
        dests = [{"n": "Haartman Hospital ER", "url": "https://www.hel.fi/"}, {"n": "Meilahti Hospital ER", "url": "https://www.hus.fi/"}]
    for i, d in enumerate(dests):
        d.update({"d": "%.1f km · %d min" % (4.1 + 1.5 * i, 11 + 3 * i), "f": "€%d–%d" % (14 + 3 * i, 18 + 3 * i)})
    return {"destinations": dests, "provider": "Uber (linked account)", "note": "Fares are estimates. In an emergency call 112."}


def book_ride(user, destination):
    payload = {"car": "Toyota Corolla · white · ZKT-482", "dest": "To " + str(destination)[:80], "eta": "4 min away",
               "provider": "Uber", "simulated": True, "requestedAt": db.iso()}
    bid = db.new_id("bk_")
    db.run("INSERT INTO bookings(id,user_id,kind,payload,status,created_at) VALUES(?,?,?,?,?,?)",
           (bid, user["id"], "ride", db.dumps(payload), "requested", db.iso()))
    return dict(payload, rideId=bid)
