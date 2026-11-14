"""Generic research tasks (docs/api.md): POST /tasks returns 202 + id; a worker
thread runs Coordinator -> Researcher -> Planner and stores an immutable proposal.
Clients poll GET /tasks/:id with pollAfterMs."""
import logging
from concurrent.futures import ThreadPoolExecutor

from .. import agents, db
from ..errors import ApiError
from . import proposals

log = logging.getLogger("taimi.tasks")
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="taimi-task")

INTENT_MAP = {"groceries": "groceries", "discovery": "events", "events": "events", "travel": "travel", "product": "products",
              "products": "products", "medicine": "medicine", "wellbeing": "wellbeing"}
KIND = {"groceries": "shopping_plan", "events": "event_picks", "travel": "trip_plan", "products": "product_picks",
        "medicine": "medicine_options", "wellbeing": "wellbeing_plan"}


def _payload_for(intent, request, constraints, user):
    c = dict(constraints or {})
    if intent == "groceries":
        items = c.get("items")
        if not items:
            from . import organiser
            items = organiser.list_items(user, include_bought=False)
        return {"items": items, "strategy": {"one": "single", "split": "multi"}.get(c.get("storeMode"), c.get("storeMode") or "multi")}
    if intent == "products":
        from .treats import extract_keys
        keys, ptype = extract_keys(request)
        return {"query": request, "keys": c.get("keys") or keys, "productType": ptype}
    if intent == "wellbeing":
        return {"mood": c.get("mood") or "tired"}
    return {"query": request, "interests": c.get("interests") or []}


def _work(user, task_id, intent, payload):
    try:
        db.run("UPDATE tasks SET status='researching', updated_at=? WHERE id=?", (db.iso(), task_id))
        research_user = user
        if intent == "groceries":
            from .shopping_prices import search_user
            research_user = search_user(user)
        res = agents.run(research_user, intent, payload, task_id=task_id)
        current = db.q1("SELECT status FROM tasks WHERE id=?", (task_id,))
        if current and current["status"] == "cancelled":
            return
        if res.get("status") == "clarifying":
            db.run("UPDATE tasks SET status='clarifying', missing_fields=?, updated_at=? WHERE id=?",
                   (db.dumps(res["missingFields"]), db.iso(), task_id))
            return
        prop = proposals.create(user, KIND[intent], res, task_id=task_id)
        status = "partial" if res.get("hasUnknownCosts") or res.get("mode") == "demo" else "awaiting_approval"
        db.run("UPDATE tasks SET status=?, proposal_id=?, progress=?, updated_at=? WHERE id=?",
               (status, prop["proposalId"], res.get("summary"), db.iso(), task_id))
    except Exception as e:  # never leak internals
        log.exception("task %s failed", task_id)
        db.run("UPDATE tasks SET status='failed', error=?, updated_at=? WHERE id=?", ("Research failed. Try again.", db.iso(), task_id))


def create(user, intent, request, constraints=None):
    if intent not in INTENT_MAP:
        raise ApiError(400, "INVALID_INPUT", "intent must be one of: " + ", ".join(sorted(INTENT_MAP)))
    request = (request or "").strip()[:500]
    active = db.q1("SELECT COUNT(*) AS n FROM tasks WHERE user_id=? AND status IN ('queued','researching')", (user["id"],))["n"]
    if active >= 3:
        raise ApiError(429, "RATE_LIMITED", "You already have research running. Give it a moment.", True, {"Retry-After": "5"})
    tid = db.new_id("t_")
    agent_intent = INTENT_MAP[intent]
    db.run("INSERT INTO tasks(id,user_id,intent,request,constraints,status,progress,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
           (tid, user["id"], agent_intent, request, db.dumps(constraints or {}), "queued", "Queued", db.iso(), db.iso()))
    _pool.submit(_work, user, tid, agent_intent, _payload_for(agent_intent, request, constraints, user))
    return {"id": tid, "status": "queued", "pollAfterMs": 1500}


def get(user, tid):
    row = db.q1("SELECT * FROM tasks WHERE id=? AND user_id=?", (tid, user["id"]))
    if not row:
        raise ApiError(404, "NOT_FOUND", "Task not found.")
    steps = db.q("SELECT role,seq,status,summary,duration_ms AS durationMs FROM agent_steps WHERE task_id=? ORDER BY seq", (tid,))
    out = {"id": row["id"], "intent": row["intent"], "request": row["request"], "status": row["status"], "progress": row["progress"],
           "proposalId": row["proposal_id"], "steps": steps, "createdAt": row["created_at"], "updatedAt": row["updated_at"]}
    if row["missing_fields"]:
        out["missingFields"] = db.loads(row["missing_fields"], [])
    if row["error"]:
        out["error"] = {"code": "TASK_FAILED", "message": row["error"], "retryable": True}
    if row["status"] in ("queued", "researching", "planning"):
        out["pollAfterMs"] = 1500
    return out


def clarify(user, tid, answers):
    row = db.q1("SELECT * FROM tasks WHERE id=? AND user_id=?", (tid, user["id"]))
    if not row:
        raise ApiError(404, "NOT_FOUND", "Task not found.")
    if row["status"] != "clarifying":
        raise ApiError(409, "NOT_CLARIFYING", "This task isn't waiting for an answer.")
    constraints = dict(db.loads(row["constraints"], {}), **(answers or {}))
    request = row["request"] + " " + " ".join(str(v) for v in (answers or {}).values() if isinstance(v, str))
    db.run("UPDATE tasks SET status='queued', constraints=?, request=?, missing_fields=NULL, updated_at=? WHERE id=?",
           (db.dumps(constraints), request.strip(), db.iso(), tid))
    _pool.submit(_work, user, tid, row["intent"], _payload_for(row["intent"], request.strip(), constraints, user))
    return get(user, tid)


def cancel(user, tid):
    row = db.q1("SELECT * FROM tasks WHERE id=? AND user_id=?", (tid, user["id"]))
    if not row:
        raise ApiError(404, "NOT_FOUND", "Task not found.")
    if row["status"] in ("queued", "researching", "clarifying", "awaiting_approval", "partial"):
        db.run("UPDATE tasks SET status='cancelled', updated_at=? WHERE id=?", (db.iso(), tid))
        db.run("UPDATE proposals SET status='cancelled' WHERE task_id=? AND status='awaiting_approval'", (tid,))
    return get(user, tid)


def list_proposals(user, tid):
    rows = db.q("SELECT id FROM proposals WHERE task_id=? AND user_id=? ORDER BY version DESC", (tid, user["id"]))
    return {"items": [proposals.get(user, r["id"]) for r in rows]}


def export_html(user, tid):
    import html
    t = get(user, tid)
    if not t["proposalId"]:
        raise ApiError(409, "NOT_READY", "No plan yet.")
    p = proposals.get(user, t["proposalId"])
    body = []
    for key in ("plan", "results", "meals"):
        for x in p.get(key, []) or []:
            if key == "plan":
                for l in x["lines"]:
                    body.append("<li>%s — %s €%.2f</li>" % (html.escape(l["item"]["name"]), html.escape(x["store"]["name"]), l["price"] * l["qty"]))
            else:
                body.append("<li>%s</li>" % html.escape(str(x.get("title") or x.get("name") or "")))
    srcs = "".join('<li><a href="%s">%s</a></li>' % (html.escape(s["url"], quote=True), html.escape(s.get("title", s["url"])))
                   for s in p.get("sources", []) if isinstance(s, dict) and s.get("url"))
    return "<!doctype html><meta charset='utf-8'><title>Taimi plan</title><h1>%s</h1><ul>%s</ul><h3>Sources</h3><ul>%s</ul>" % (
        html.escape(t["request"] or t["intent"]), "".join(body), srcs)


def sources(user, source_url_hash=None):
    return db.q("SELECT * FROM sources WHERE user_id=? ORDER BY fetched_at DESC LIMIT 50", (user["id"],))
