"""End-to-end API tests (Exa in mock mode -> demo data path)."""
import uuid


# ------------------------------------------------------------------ auth
def test_requires_auth(app_client):
    app_client.cookies.clear()
    r = app_client.post("/api/deals", json={"items": [{"id": "a", "name": "milk"}], "strategy": "multi"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHENTICATED"


def test_login_logout_and_pages(app_client):
    app_client.cookies.clear()
    assert app_client.get("/mobile/", follow_redirects=False).status_code == 303
    bad = app_client.post("/api/v1/auth/login", json={"email": "test@taimi.app", "password": "nope"})
    assert bad.status_code == 401
    ok = app_client.post("/api/v1/auth/login", json={"email": "test@taimi.app", "password": "taimi-demo-2026"})
    assert ok.status_code == 200 and ok.json()["user"]["name"] == "Alex"
    page = app_client.get("/mobile/")
    assert page.status_code == 200 and "FIGMENT_USE_BACKEND=true" in page.text and "taimi-bridge.js" in page.text
    assert app_client.get("/mobile/data.js").status_code == 200
    assert "taimi-bridge.js" in app_client.get("/").text
    assert app_client.post("/api/v1/auth/logout").status_code == 200
    assert app_client.get("/api/v1/me").status_code == 401


def test_bearer_token_and_register(app_client):
    app_client.cookies.clear()
    email = "u%s@example.com" % uuid.uuid4().hex[:6]
    r = app_client.post("/api/v1/auth/register", json={"email": email, "password": "longpassword", "name": "Mia", "city": "Austin",
                                                        "country": "us", "timezone": "America/Chicago"})
    assert r.status_code == 201
    token = r.json()["token"]
    app_client.cookies.clear()
    me = app_client.get("/api/v1/me", headers={"Authorization": "Bearer " + token}).json()
    assert me["country"] == "US" and me["currency"] == "USD" and "walmart.com" in me["groceryDomains"]
    # another user's data is invisible
    items = app_client.get("/api/v1/shopping/items", headers={"Authorization": "Bearer " + token}).json()
    assert items["items"] == []
    dup = app_client.post("/api/v1/auth/register", json={"email": email, "password": "longpassword", "name": "Mia"})
    assert dup.status_code == 409


def test_preferences_site_region(client):
    r = client.patch("/api/v1/me/preferences", json={"preferredDomains": ["https://www.lidl.fi/", "k-ruoka.fi"]})
    assert r.json()["groceryDomains"] == ["lidl.fi", "k-ruoka.fi"]
    client.patch("/api/v1/me/preferences", json={"preferredDomains": []})


def test_csrf_blocks_cross_site_cookie_write(client):
    r = client.post("/api/v1/shopping/items", json={"name": "x"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


# --------------------------------------------- mobile-compatible contract
def test_compat_deals_shape(client):
    items = [{"id": "i1", "name": "Oat milk 1 L", "qty": 2, "prio": 1, "from": "fridge"},
             {"id": "i4", "name": "Coffee beans 500 g", "qty": 1}]
    for strat in ("multi", "single", "mall", "nearest"):
        r = client.post("/api/deals", json={"items": items, "strategy": strat}).json()
        assert {"total", "saved", "note", "plan", "sources"} <= set(r)
        assert r["mode"] == "demo"
        for p in r["plan"]:
            assert {"name", "dist", "url"} <= set(p["store"])
            for l in p["lines"]:
                assert isinstance(l["price"], float) and l["item"]["name"]
        assert abs(sum(p["total"] for p in r["plan"]) - r["total"]) < 0.01
    multi = client.post("/api/deals", json={"items": items, "strategy": "multi"}).json()
    assert multi["total"] == round(2 * 1.49 + 6.49, 2)  # cheapest per item, same as the prototype
    mall = client.post("/api/deals", json={"items": items, "strategy": "mall"}).json()
    assert {p["store"]["mall"] for p in mall["plan"]} == {"REDI mall"}


def test_compat_explore_products_medicine_wellbeing(client):
    ev = client.post("/api/explore", json={"query": "jazz tonight", "kind": "events", "interests": ["jazz"]}).json()
    assert ev["results"][0]["art"] == "jazz" and ev["results"][0]["sources"]
    tr = client.post("/api/explore", json={"query": "Lapland this winter", "kind": "travel", "interests": []}).json()
    assert tr["results"][0]["details"]
    pr = client.post("/api/products", json={"query": "Warm waterproof winter boots, black, under €150", "liked": [], "disliked": [], "round": 1}).json()
    assert "under €150" in pr["keys"] and pr["results"][0]["matched"] and pr["strategy"].startswith("Searched")
    # feedback round: dislike the top result -> it drops to the bottom
    top = pr["results"][0]["id"]
    pr2 = client.post("/api/products", json={"query": "x", "keys": pr["keys"], "liked": [pr["results"][1]["id"]], "disliked": [top], "round": 2}).json()
    assert pr2["results"][-1]["id"] == top and pr2["strategy"].startswith("Round 2")
    med = client.post("/api/medicine", json={"symptom": "sore throat"}).json()
    assert med["results"] and all("price" in m and "pharmacy" in m for m in med["results"])
    urgent = client.post("/api/medicine", json={"symptom": "chest pain and can't breathe"}).json()
    assert urgent["urgent"] is True and urgent["results"] == []
    wb = client.post("/api/wellbeing", json={"mood": "stressed"}).json()
    assert wb["meals"] and wb["activities"] and wb["sources"]


def test_compat_chat_safety_and_memory(client):
    crisis = client.post("/api/chat", json={"text": "I want to hurt myself", "memoryConsent": True}).json()
    assert crisis["replies"][0]["kind"] == "care" and crisis["replies"][0]["crisis"] is True
    assert "memory" not in crisis
    sad = client.post("/api/chat", json={"text": "feeling really lonely today", "memoryConsent": False}).json()
    assert any(r.get("kind") == "care" for r in sad["replies"])
    pref = client.post("/api/chat", json={"text": "I really love board games", "memoryConsent": True}).json()
    assert pref["memory"] == "Likes board games"
    mems = client.get("/api/v1/memories").json()["items"]
    assert any(m["text"] == "Likes board games" for m in mems)
    off = client.post("/api/chat", json={"text": "I like karaoke", "memoryConsent": False}).json()
    assert "memory" not in off and "Memory is off" in off["replies"][0]["text"]
    hi = client.post("/api/chat", json={"text": "hey"}).json()
    assert "Alex" in hi["replies"][0]["text"]


# -------------------------------------------------------------- organiser
def test_shopping_crud_and_versions(client):
    it = client.post("/api/v1/shopping/items", json={"name": "Bananas", "prio": 3}).json()
    up = client.patch("/api/v1/shopping/items/" + it["id"], json={"prio": 1, "expectedVersion": it["version"]}).json()
    assert up["prio"] == 1 and up["version"] == it["version"] + 1
    stale = client.patch("/api/v1/shopping/items/" + it["id"], json={"prio": 2, "expectedVersion": it["version"]})
    assert stale.status_code == 409
    assert client.delete("/api/v1/shopping/items/" + it["id"]).json()["ok"]


def test_camera_scan_adds_missing_regulars(client):
    frames = client.get("/api/v1/devices/fridge/frames").json()["items"]
    assert len(frames) == 2 and frames[0]["detections"]
    client.post("/api/v1/devices/fridge/scan?frame=0")
    r = client.post("/api/v1/devices/fridge/scan?frame=1").json()  # evening: milk + eggs gone, butter low
    names = [i["name"] for i in client.get("/api/v1/shopping/items").json()["items"] if not i["bought"]]
    assert "Butter 500 g" in names
    assert r["frame"]["id"] == "fridge-1900"
    milk = [i for i in client.get("/api/v1/shopping/items").json()["items"] if i["name"] == "Oat milk 1 L"][0]
    assert milk["prio"] == 1  # none left -> urgent
    # real devices post derived detections only
    obs = client.post("/api/v1/devices/storage/observations", json={"detections": [{"label": "dish_soap", "level": 0}]}).json()
    assert obs["device"] == "storage"


def test_deals_order_print_and_idempotency(client):
    plan = client.post("/api/v1/shopping/deals", json={"strategy": "single"}).json()
    assert plan["proposalId"] and plan["payloadHash"].startswith("sha256:")
    html = client.get("/api/v1/shopping/proposals/%s/print" % plan["proposalId"]).text
    assert "Shopping list" in html
    key = str(uuid.uuid4())
    body = {"proposalId": plan["proposalId"], "expectedVersion": 1, "payloadHash": plan["payloadHash"]}
    a = client.post("/api/v1/shopping/orders", json=body, headers={"Idempotency-Key": key}).json()
    assert a["status"] == "succeeded" and a["result"]["simulated"] is True
    b = client.post("/api/v1/shopping/orders", json=body, headers={"Idempotency-Key": key}).json()
    assert b["actionId"] == a["actionId"] and b["replayed"] is True
    c = client.post("/api/v1/shopping/orders", json=dict(body, payloadHash="sha256:other"), headers={"Idempotency-Key": key})
    assert c.status_code == 409
    open_items = [i for i in client.get("/api/v1/shopping/items").json()["items"] if not i["bought"]]
    assert all(i["name"] not in [l["item"]["name"] for p in plan["plan"] for l in p["lines"]] for i in open_items)


def test_grocery_trip_slot_edit_and_book(client):
    t = client.get("/api/v1/shopping/trip").json()
    assert {"day", "start", "end", "booked", "options", "calendar"} <= set(t)
    t2 = client.put("/api/v1/shopping/trip", json={"day": "tomorrow", "start": 16.5}).json()
    assert t2["day"] == "tomorrow" and "Lecture" in t2["conflicts"]
    t3 = client.put("/api/v1/shopping/trip", json={"day": "tomorrow", "start": 19}).json()
    assert t3["conflicts"] == []
    booked = client.post("/api/v1/shopping/trip/book").json()
    assert booked["booked"] is True
    titles = [e["title"] for e in client.get("/api/v1/calendar/events").json()["items"]]
    assert "Grocery run" in titles


def test_free_slots_avoid_calendar(client):
    slots = client.get("/api/v1/calendar/free-slots?duration=60&days=2").json()["items"]
    evs = client.get("/api/v1/calendar/events?days=2").json()["items"]
    for s in slots:
        for e in evs:
            if e["day"] == s["day"]:
                assert not (s["start"] < e["e"] and s["end"] > e["s"])


# ---------------------------------------------------------------- laundry
def test_laundry_plan_and_booking(client):
    st = client.get("/api/v1/laundry").json()
    assert st["minRunway"] == 2 and st["loads"] and st["best"]
    assert any(s["status"] == "taken" for s in st["slots"])
    best = st["best"]
    b = client.post("/api/v1/laundry/bookings", json={"key": best}).json()
    assert b["key"] == best
    again = client.post("/api/v1/laundry/bookings", json={"key": best})
    assert again.status_code == 409
    st2 = client.get("/api/v1/laundry").json()
    assert [x for x in st2["slots"] if x["key"] == best][0]["status"] == "mine"
    assert client.delete("/api/v1/laundry/bookings/" + best).json()["ok"]
    scan = client.post("/api/v1/devices/basket/scan").json()
    assert scan["basketCount"] >= 23


# ----------------------------------------------------------------- safety
def test_checkin_requires_verification(client, challenge):
    assert client.post("/api/v1/safety/checkin", json={"verification": {"method": "fingerprint", "challenge": "forged"}}).status_code == 403
    st = client.post("/api/v1/safety/checkin", json={"verification": challenge()}).json()
    assert st["doneToday"] is True and st["streak"] >= 1
    pw = client.post("/api/v1/safety/checkin", json={"verification": {"method": "password", "password": "taimi-demo-2026"}}).json()
    assert pw.get("already") is True


def test_missed_checkin_escalates_with_trail(client):
    from datetime import timedelta
    from app import db
    from app.services import safety
    user = db.q1("SELECT * FROM users WHERE email='test@taimi.app'")
    db.run("DELETE FROM checkins WHERE user_id=?", (user["id"],))
    db.run("INSERT INTO locations(id,user_id,at,lat,lng,accuracy_m,label) VALUES('lx',?,?,60.17,24.94,8,'Library')", (user["id"], db.iso()))
    due = safety.due_at(user)
    esc = safety.evaluate(user, now=due + timedelta(hours=3))
    assert esc and esc["sentTo"]
    assert safety.evaluate(user, now=due + timedelta(hours=4)) is None  # once per deadline
    msgs = client.get("/api/v1/outbox").json()["items"]
    alert = [m for m in msgs if m["relatedType"] == "escalation"][0]
    assert "Library" in alert["body"] and "maps.google.com" in alert["body"]


def test_sos_flow(client, challenge):
    assert client.post("/api/v1/safety/sos", json={"verification": {"method": "face"}}).status_code == 403
    s = client.post("/api/v1/safety/sos", json={"verification": challenge(), "type": "Being followed", "police": True,
                                                 "location": {"lat": 60.1841, "lng": 24.9497, "accuracy": 5}}).json()
    assert s["status"] == "active" and s["police"] and len(s["to"]) >= 3
    assert "60.1841" in s["location"]["text"]
    assert client.get("/api/v1/safety/sos/active").json()["sos"]["id"] == s["id"]
    assert client.post("/api/v1/safety/sos/%s/resolve" % s["id"], json={"verification": challenge()}).json()["ok"]
    no_type = client.post("/api/v1/safety/sos", json={"verification": challenge()}).json()
    assert no_type["type"] is None


def test_door_monitoring(client):
    evs = client.get("/api/v1/safety/door/events").json()["items"]
    flagged = [e for e in evs if e["flagged"]]
    assert flagged and "lingered" in flagged[0]["title"]
    new = client.post("/api/v1/safety/door/events", json={"detections": [{"person": "unknown", "dwell_s": 300, "knocked": False}]}).json()
    assert new["items"][0]["kind"] == "bad"
    r = client.post("/api/v1/safety/door/events/%s/review" % new["items"][0]["id"], json={"action": "alert"}).json()
    assert r["sentTo"]
    ok = client.post("/api/v1/safety/door/events", json={"detections": [{"person": "courier", "dwell_s": 20, "knocked": True}]}).json()
    assert ok["items"][0]["kind"] == "ok"


def test_location_consent(client):
    assert client.post("/api/v1/safety/locations", json={"lat": 60.1, "lng": 24.9}).status_code == 201
    client.delete("/api/v1/consents/location_trail")
    assert client.post("/api/v1/safety/locations", json={"lat": 60.1, "lng": 24.9}).status_code == 403
    client.post("/api/v1/consents/location_trail")


# ----------------------------------------------------------------- health
def test_health_flow(client):
    s = client.get("/api/v1/health/summary").json()
    types = {a["type"] for a in s["anomalies"]}
    assert {"resting_hr_up", "short_sleep"} <= types and s["careprompt"]
    meds = client.post("/api/v1/health/medicine", json={"symptom": "headache"}).json()
    o = client.post("/api/v1/health/medicine/orders", json={"proposalId": meds["proposalId"], "index": 0}).json()
    assert o["result"]["simulated"] and o["result"]["total"] > o["result"]["price"]
    sug = client.get("/api/v1/health/appointments/suggestions").json()["suggestions"]
    assert len(sug) >= 2
    booked = client.post("/api/v1/health/appointments", json={"suggestionId": sug[0]["id"]}).json()
    assert booked["bookingId"]
    ride = client.post("/api/v1/health/rides", json={"destination": "Meilahti Hospital ER"}).json()
    assert ride["eta"]
    v = client.post("/api/v1/health/vitals", json={"samples": [{"day": "2030-01-01", "hr": 60, "sleep": 8, "steps": 9000}]}).json()
    assert v["stored"] == 1


# -------------------------------------------------------------- companion
def test_companion_social_calls(client):
    soc = client.get("/api/v1/social").json()["items"]
    tg = [s for s in soc if s["name"] == "Telegram"][0]
    assert client.patch("/api/v1/social/" + tg["id"], json={"linked": True}).json()["items"]
    assert client.post("/api/v1/calls", json={"kind": "video"}).json()["agent"] == "Taimi"
    assert client.get("/api/v1/companion/posts").json()["items"]
    reach = client.post("/api/v1/chat/reach-out", json={"confirmed": True}).json()
    assert reach["sent"] and "Taimi" in reach["message"]
    assert client.post("/api/v1/chat/reach-out", json={"confirmed": False}).status_code == 400


# ------------------------------------------------------- tasks / watches
def test_task_lifecycle(client):
    import time
    t = client.post("/api/v1/tasks", json={"intent": "discovery", "request": "jazz this weekend"})
    assert t.status_code == 202
    tid = t.json()["id"]
    for _ in range(50):
        st = client.get("/api/v1/tasks/" + tid).json()
        if st["status"] not in ("queued", "researching"):
            break
        time.sleep(0.1)
    assert st["status"] in ("partial", "awaiting_approval") and [s["role"] for s in st["steps"]] == ["coordinator", "researcher", "planner"]
    p = client.get("/api/v1/proposals/" + st["proposalId"]).json()
    a = client.post("/api/v1/proposals/%s/approve" % p["id"], json={"expectedVersion": p["version"], "payloadHash": p["payloadHash"]}).json()
    assert a["status"] == "succeeded"
    assert "<h1>" in client.get("/api/v1/tasks/%s/export" % tid).text


def test_price_watch_crud(client):
    w = client.post("/api/v1/price-watches", json={"query": "Sony WH-1000XM5", "targetMinor": 25000}).json()
    assert w["status"] == "active"
    p = client.patch("/api/v1/price-watches/" + w["id"], json={"paused": True, "expectedVersion": w["version"]}).json()
    assert p["status"] == "paused"
    chk = client.post("/api/v1/price-watches/%s/checks" % w["id"]).json()
    assert chk["checkState"] in ("partial", "error", "stale")
    assert client.delete("/api/v1/price-watches/" + w["id"]).json()["ok"]


def test_state_snapshot_matches_mobile_seed_keys(client):
    s = client.get("/api/v1/state").json()
    for k in ("user", "memoryConsent", "memories", "devices", "contacts", "social", "checkin", "shopping", "groceryTrip", "wardrobe",
              "basket", "laundryBookings", "healthLog", "doorEvents", "today", "chat", "agentPosts"):
        assert k in s, k
    assert len(s["healthLog"]["hr"]) == 7


def test_media_not_configured_is_explicit(client):
    r = client.post("/api/v1/media/itinerary", json={"title": "Trip", "items": [{"time": "Fri", "title": "Fly"}]})
    assert r.status_code == 503 and r.json()["error"]["code"] == "PROVIDER_NOT_CONFIGURED"


def test_usage_ledger(client):
    u = client.get("/api/v1/usage").json()
    assert u["exa"]["totalBudgetUsd"] <= 50
