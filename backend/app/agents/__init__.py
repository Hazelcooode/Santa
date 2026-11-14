"""Exactly three application agents (docs/exa-agents.md):

  Coordinator -> TaskSpec        (what to look for, where, under which constraints)
  Researcher  -> ResearchBundle  (Exa searches with inline structured extraction)
  Planner     -> result/proposal (deterministic ranking, totals, explanation)

Exa is a shared tool; deterministic code performs approved actions (not an agent).
`run()` is used synchronously by the mobile-compatible endpoints and asynchronously
by POST /api/v1/tasks.
"""
import time

from .. import db
from . import coordinator, planner, researcher


class Trace:
    """Records concise agent steps (never hidden reasoning) for a task."""

    def __init__(self, user, task_id=None):
        self.user = user
        self.task_id = task_id
        self.seq = 0
        self.steps = []

    def step(self, role, status, summary, started):
        self.seq += 1
        ms = int((time.time() - started) * 1000)
        self.steps.append({"role": role, "status": status, "summary": summary, "durationMs": ms})
        if self.task_id:
            db.run(
                "INSERT INTO agent_steps(id,user_id,task_id,role,seq,status,summary,duration_ms,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (db.new_id("st_"), self.user["id"], self.task_id, role, self.seq, status, summary[:400], ms, db.iso()),
            )
            db.run("UPDATE tasks SET progress=?, updated_at=? WHERE id=?", (summary[:200], db.iso(), self.task_id))


def run(user, intent, payload, task_id=None):
    trace = Trace(user, task_id)

    t = time.time()
    spec = coordinator.plan(user, intent, payload)
    if spec.get("missingFields"):
        trace.step("coordinator", "clarifying", "Need: " + ", ".join(spec["missingFields"]), t)
        return {"status": "clarifying", "missingFields": spec["missingFields"], "spec": spec, "steps": trace.steps}
    trace.step("coordinator", "ok", "%s: %d search step(s)%s" % (intent, len(spec["queries"]),
               " in " + spec["location"] if spec.get("location") else ""), t)

    t = time.time()
    bundle = researcher.research(user, spec)
    trace.step("researcher", "ok" if bundle["available"] else "fallback",
               "%d sources, %d candidates%s" % (len(bundle["sources"]), len(bundle["candidates"]),
                                                "" if bundle["available"] else " (demo data: %s)" % bundle["reason"]), t)

    t = time.time()
    result = planner.plan(user, spec, bundle)
    result.setdefault("mode", "live" if bundle["available"] else "demo")
    if not bundle["available"]:
        result.setdefault("notice", "Showing demo data because live search is unavailable (%s)." % bundle["reason"])
    trace.step("planner", "ok", result.get("summary") or "plan ready", t)
    result["steps"] = trace.steps
    result["status"] = "ready"
    return result
