"""Price watches (docs/price-watch.md): saved searches or exact items, a target
price, scheduled + manual checks through the agents, immutable observation
history and de-duplicated alerts. Thresholds are deterministic code."""
from datetime import timedelta

from .. import agents, db
from ..errors import ApiError

MAX_WATCHES = 50


def _public(row):
    d = db.loads(row["data"], {})
    obs = db.q("SELECT at,price_minor AS priceMinor,currency,title,url,store FROM price_observations WHERE watch_id=? ORDER BY at DESC LIMIT 1",
               (row["id"],))
    return dict(d, id=row["id"], status=row["status"], version=row["version"], createdAt=row["created_at"], updatedAt=row["updated_at"],
                latest=obs[0] if obs else None)


def list_watches(user):
    return {"items": [_public(r) for r in db.q("SELECT * FROM price_watches WHERE user_id=? ORDER BY created_at DESC", (user["id"],))],
            "nextCursor": None}


def get(user, wid):
    row = db.q1("SELECT * FROM price_watches WHERE id=? AND user_id=?", (wid, user["id"]))
    if not row:
        raise ApiError(404, "NOT_FOUND", "Watch not found.")
    return row


def create(user, body):
    n = db.q1("SELECT COUNT(*) AS n FROM price_watches WHERE user_id=?", (user["id"],))["n"]
    if n >= MAX_WATCHES:
        raise ApiError(422, "LIMIT_REACHED", "You can keep up to %d watches." % MAX_WATCHES)
    query = (body.get("query") or body.get("name") or "").strip()[:160]
    if not query:
        raise ApiError(400, "INVALID_INPUT", "What should I watch?")
    data = {"query": query, "category": body.get("category"), "targetMinor": body.get("targetMinor"),
            "currency": body.get("currency") or user.get("currency") or "EUR", "sites": (body.get("sites") or [])[:10],
            "cadenceHours": max(6, int(body.get("cadenceHours") or 24)), "buyBy": body.get("buyBy"),
            "notify": bool(body.get("notify", True)), "alerts": [], "checkState": "idle", "lastCheckedAt": None}
    wid = db.new_id("pw_")
    db.run("INSERT INTO price_watches(id,user_id,data,status,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
           (wid, user["id"], db.dumps(data), "active", 1, db.iso(), db.iso()))
    return _public(get(user, wid))


def update(user, wid, body):
    row = get(user, wid)
    if body.get("expectedVersion") is not None and int(body["expectedVersion"]) != row["version"]:
        raise ApiError(409, "VERSION_CONFLICT", "This watch changed elsewhere.")
    data = db.loads(row["data"], {})
    status = row["status"]
    if "paused" in body:
        status = "paused" if body["paused"] else "active"
    if "targetMinor" in body:
        data["targetMinor"] = body["targetMinor"]
        data["alerts"] = []  # re-arm
    for k in ("query", "sites", "cadenceHours", "notify", "buyBy"):
        if k in body:
            data[k] = body[k]
    db.run("UPDATE price_watches SET data=?, status=?, version=version+1, updated_at=? WHERE id=?", (db.dumps(data), status, db.iso(), wid))
    return _public(get(user, wid))


def delete(user, wid):
    get(user, wid)
    db.run("DELETE FROM price_observations WHERE watch_id=? AND user_id=?", (wid, user["id"]))
    db.run("DELETE FROM price_watches WHERE id=?", (wid,))


def check(user, wid):
    row = get(user, wid)
    data = db.loads(row["data"], {})
    res = agents.run(user, "watch", {"query": data["query"], "sites": data.get("sites")})
    offers = res.get("offers") or []
    data["lastCheckedAt"] = db.iso()
    if not offers:
        data["checkState"] = "stale" if row and data.get("lastPriceMinor") else ("partial" if res.get("mode") == "demo" else "error")
    else:
        best = offers[0]
        data["checkState"] = "ready"
        data["lastPriceMinor"] = best["priceMinor"]
        db.run("INSERT INTO price_observations(id,user_id,watch_id,at,price_minor,currency,title,url,store) VALUES(?,?,?,?,?,?,?,?,?)",
               (db.new_id("po_"), user["id"], wid, db.iso(), best["priceMinor"], best["currency"], best["title"], best["url"], best["store"]))
        tgt = data.get("targetMinor")
        if tgt and best["priceMinor"] <= tgt and not data.get("alerts"):
            data["alerts"] = [{"at": db.iso(), "priceMinor": best["priceMinor"], "url": best["url"], "store": best["store"]}]
    db.run("UPDATE price_watches SET data=?, updated_at=? WHERE id=?", (db.dumps(data), db.iso(), wid))
    return dict(_public(get(user, wid)), offers=offers[:5], mode=res.get("mode"))


def history(user, wid):
    get(user, wid)
    return {"items": db.q("SELECT at,price_minor AS priceMinor,currency,title,url,store FROM price_observations WHERE watch_id=? AND user_id=? ORDER BY at",
                          (wid, user["id"]))}


def due(now=None):
    now = now or db.now()
    out = []
    for r in db.q("SELECT * FROM price_watches WHERE status='active'"):
        d = db.loads(r["data"], {})
        last = db.parse_iso(d.get("lastCheckedAt")) if d.get("lastCheckedAt") else None
        if not last or now - last >= timedelta(hours=d.get("cadenceHours", 24)):
            out.append(r)
    return out
