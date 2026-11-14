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


def _fake_claude(monkeypatch, script):
    """Scripted Claude: script(kw) -> list of content blocks for each messages.create call."""
    from types import SimpleNamespace as NS
    from app import llm
    from app.config import settings
    calls = []

    class Msgs:
        def create(self, **kw):
            calls.append(kw)
            blocks = [NS(**b) for b in script(kw)]
            stop = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
            return NS(stop_reason=stop, content=blocks)
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(llm, "_client", NS(messages=Msgs()))
    return calls


def _tool_results(kw):
    last = kw["messages"][-1]["content"]
    return [b for b in last if isinstance(b, dict) and b.get("type") == "tool_result"] if isinstance(last, list) else []


def test_chat_is_the_claude_agent_with_exa_as_its_only_search(client, monkeypatch):
    from app import exa_client
    searched = []

    def fake_search(user_id, kind, query, **kw):
        searched.append((kind, query))
        return {"available": True, "source": "live", "results": [
            {"url": "https://helmet.fi/en/events/boardgames", "title": "Board game night", "domain": "helmet.fi", "highlights": ["Oodi, Fri 18:00"]},
            {"url": "https://example.org/other", "title": "Other", "domain": "example.org", "highlights": ["x"]}]}
    monkeypatch.setattr(exa_client, "search", fake_search)

    def script(kw):
        res = _tool_results(kw)
        if not res:
            return [{"type": "tool_use", "id": "t1", "name": "exa_search", "input": {"query": "board game night Helsinki", "recent_only": True}},
                    {"type": "tool_use", "id": "t2", "name": "save_memory", "input": {"text": "Likes board games"}}]
        assert [r["tool_use_id"] for r in res] == ["t1", "t2"] and "[1] Board game night" in res[0]["content"]
        return [{"type": "text", "text": "Oodi has a board game night on Friday at 18:00 [1] 🎲"}]
    calls = _fake_claude(monkeypatch, script)

    r = client.post("/api/chat", json={"text": "I love board games, anything on this week?", "memoryConsent": True}).json()
    tools = calls[0]["tools"]
    assert [t["name"] for t in tools if "search" in t["name"]] == ["exa_search"]
    assert all("type" not in t for t in tools)          # no Anthropic server tools (e.g. web_search)
    assert calls[0]["model"] == "claude-haiku-5-5" and searched == [("chat", "board game night Helsinki")]
    rep = r["replies"][0]
    assert r["agent"] is True and rep["kind"] == "find" and "[1]" not in rep["text"] and "Oodi" in rep["text"]
    assert rep["sources"] == [{"title": "Board game night", "url": "https://helmet.fi/en/events/boardgames"}]
    assert r["memory"] == "Likes board games"
    assert any(m["text"] == "Likes board games" for m in client.get("/api/v1/memories").json()["items"])


def test_chat_agent_memory_off_and_care(client, monkeypatch):
    def script(kw):
        res = _tool_results(kw)
        if not res:
            return [{"type": "tool_use", "id": "m", "name": "save_memory", "input": {"text": "Likes karaoke"}},
                    {"type": "tool_use", "id": "c", "name": "offer_reach_out", "input": {"reason": "lonely"}}]
        assert "Memory is off" in res[0]["content"]
        return [{"type": "text", "text": "Karaoke is the best. Want me to turn memory on so I keep that?"}]
    _fake_claude(monkeypatch, script)
    r = client.post("/api/chat", json={"text": "feeling lonely, I like karaoke though", "memoryConsent": False}).json()
    assert "memory" not in r and any(x.get("kind") == "care" for x in r["replies"])
    assert not any(m["text"] == "Likes karaoke" for m in client.get("/api/v1/memories").json()["items"])


def test_chat_crisis_safety_net_holds_without_the_model(client, monkeypatch):
    from app.config import settings
    calls = _fake_claude(monkeypatch, lambda kw: [{"type": "text", "text": "I'm right here with you."}])
    r = client.post("/api/chat", json={"text": "I want to hurt myself", "memoryConsent": True}).json()
    assert r["replies"][0]["kind"] == "care" and r["replies"][0]["crisis"] is True
    assert r["replies"][1]["text"] == "I'm right here with you." and "MIELI" in r["replies"][-1]["text"]
    assert "exa_search" not in [t["name"] for t in calls[0]["tools"]] and "memory" not in r
    monkeypatch.setattr(settings, "llm_enabled", False)        # model down: the care card and helpline still show
    r = client.post("/api/chat", json={"text": "I want to hurt myself"}).json()
    assert r["replies"][0]["crisis"] is True and "MIELI" in r["replies"][-1]["text"] and r["agent"] is False
    off = client.post("/api/chat", json={"text": "hey"}).json()
    assert off["agent"] is False and "brain" in off["replies"][0]["text"]


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
    assert client.post("/api/v1/price-watches/%s/checks" % w["id"]).status_code == 409
    client.patch("/api/v1/price-watches/" + w["id"], json={"paused": False})
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


def test_deals_compare_modes_like_for_like_and_on_the_way(client):
    from app import db, seed
    client.post("/api/v1/consents/location_trail")
    me = client.get("/api/v1/me").json()
    db.run("DELETE FROM locations WHERE user_id=?", (me["id"],))
    seed.seed_location_trail(db.q1("SELECT * FROM users WHERE id=?", (me["id"],)))
    items = [{"id": "i1", "name": "Oat milk 1 L", "qty": 2}, {"id": "i2", "name": "Eggs (10)", "qty": 1}, {"id": "i4", "name": "Coffee beans 500 g", "qty": 1}]
    r = client.post("/api/deals", json={"items": items, "strategy": "route"}).json()
    assert r["strategy"] == "route" and r["itemCount"] == 3 and r["pricedCount"] == 3
    # on the way = stores within 500 m of the usual Home → University → Café Regatta → Home path
    assert {p["store"]["name"] for p in r["plan"]} <= {"Alepa Kallio", "K-Supermarket Kamppi"}
    assert all(p["store"]["detourKm"] <= 0.5 for p in r["plan"]) and "University" in r["note"]
    # one search, every mode; totals on the same items, so cheapest overall is never beaten
    modes = {m["id"]: m for m in r["modes"]}
    assert set(modes) == {"multi", "single", "mall", "nearest", "route"} and set(r["alternatives"]) == set(modes) - {"route"}
    assert all(modes["multi"]["comparableTotal"] <= m["comparableTotal"] + 1e-9 for m in modes.values())
    bad = client.post("/api/deals", json={"items": items, "strategy": "teleport"})
    assert bad.status_code == 400
