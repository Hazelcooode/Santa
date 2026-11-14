"""Immutable proposals + approval with idempotency (docs/api.md "Approval").

Research never acts by itself: anything with an external effect (orders,
bookings, messages) is executed by a deterministic action function only after
the user approves a specific proposal version/hash."""
import hashlib
from datetime import timedelta

from .. import db
from ..errors import ApiError


def _hash(payload):
    return "sha256:" + hashlib.sha256(db.dumps(payload).encode()).hexdigest()


def create(user, kind, payload, task_id=None, ttl_min=120):
    pid = db.new_id("pr_")
    version = 1
    if task_id:
        row = db.q1("SELECT MAX(version) AS v FROM proposals WHERE task_id=? AND user_id=?", (task_id, user["id"]))
        version = (row["v"] or 0) + 1
        db.run("UPDATE proposals SET status='superseded' WHERE task_id=? AND user_id=? AND status='awaiting_approval'", (task_id, user["id"]))
    clean = {k: v for k, v in payload.items() if k != "steps"}
    exp = db.now() + timedelta(minutes=ttl_min)
    h = _hash(clean)
    db.run("INSERT INTO proposals(id,user_id,task_id,kind,version,status,payload,payload_hash,expires_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
           (pid, user["id"], task_id, kind, version, "awaiting_approval", db.dumps(clean), h, db.iso(exp), db.iso()))
    return {"proposalId": pid, "version": version, "payloadHash": h, "expiresAt": db.iso(exp)}


def get(user, pid):
    row = db.q1("SELECT * FROM proposals WHERE id=? AND user_id=?", (pid, user["id"]))
    if not row:
        raise ApiError(404, "NOT_FOUND", "Proposal not found.")
    return {"id": row["id"], "taskId": row["task_id"], "kind": row["kind"], "version": row["version"], "status": row["status"],
            "payloadHash": row["payload_hash"], "expiresAt": row["expires_at"], "createdAt": row["created_at"],
            **db.loads(row["payload"], {})}


def approve(user, pid, idem_key, action_type, executor, expected_version=None, payload_hash=None, extra=None):
    """executor(proposal_dict) -> result dict. Same key + same body replays the stored result."""
    if not idem_key:
        idem_key = "%s:%s:%s" % (pid, action_type, expected_version or "latest")
    req_hash = hashlib.sha256(db.dumps([pid, action_type, expected_version, payload_hash, extra]).encode()).hexdigest()
    prior = db.q1("SELECT * FROM actions WHERE user_id=? AND idempotency_key=?", (user["id"], idem_key))
    if prior:
        if prior["request_hash"] != req_hash:
            raise ApiError(409, "IDEMPOTENCY_CONFLICT", "This idempotency key was already used for a different request.")
        return {"actionId": prior["id"], "status": prior["status"], "result": db.loads(prior["result"]), "replayed": True}
    with db.tx():
        row = db.q1("SELECT * FROM proposals WHERE id=? AND user_id=?", (pid, user["id"]))
        if not row:
            raise ApiError(404, "NOT_FOUND", "Proposal not found.")
        if expected_version is not None and int(expected_version) != row["version"]:
            raise ApiError(409, "PROPOSAL_STALE", "The plan changed. Review the updated version.")
        if payload_hash and payload_hash != row["payload_hash"]:
            raise ApiError(409, "PROPOSAL_STALE", "The plan changed. Review the updated version.")
        if row["status"] == "superseded":
            raise ApiError(409, "PROPOSAL_STALE", "A newer version of this plan exists.")
        if db.parse_iso(row["expires_at"]) < db.now():
            raise ApiError(410, "PROPOSAL_EXPIRED", "Prices may have changed. Search again to refresh the plan.")
        aid = db.new_id("ac_")
        db.run("INSERT INTO actions(id,user_id,proposal_id,type,status,idempotency_key,request_hash,created_at) VALUES(?,?,?,?,?,?,?,?)",
               (aid, user["id"], pid, action_type, "running", idem_key, req_hash, db.iso()))
        db.run("UPDATE proposals SET status='approved' WHERE id=?", (pid,))
    proposal = get(user, pid)
    try:
        result = executor(proposal)
        status = result.pop("_status", "succeeded")
    except ApiError:
        db.run("UPDATE actions SET status='failed' WHERE id=?", (aid,))
        db.run("UPDATE proposals SET status='awaiting_approval' WHERE id=?", (pid,))
        raise
    db.run("UPDATE actions SET status=?, result=? WHERE id=?", (status, db.dumps(result), aid))
    return {"actionId": aid, "status": status, "result": result, "replayed": False}


def get_action(user, aid):
    row = db.q1("SELECT * FROM actions WHERE id=? AND user_id=?", (aid, user["id"]))
    if not row:
        raise ApiError(404, "NOT_FOUND", "Action not found.")
    return {"id": row["id"], "proposalId": row["proposal_id"], "type": row["type"], "status": row["status"],
            "result": db.loads(row["result"]), "createdAt": row["created_at"]}
