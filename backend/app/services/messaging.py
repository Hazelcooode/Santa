"""Outbound messages to trusted contacts (SOS, missed check-ins, reach-outs).

No real SMS/WhatsApp/Telegram provider is wired in the prototype: messages are
written to the outbox with status `simulated` so the demo shows exactly what
would be sent, to whom and when. Plug a provider into `_deliver`."""
from .. import db


def _channel(via):
    v = (via or "").lower()
    for name in ("whatsapp", "telegram", "instagram", "sms", "email", "call"):
        if name in v:
            return name
    return "sms" if any(ch.isdigit() for ch in v) else "app"


def _deliver(channel, recipient, body):
    return "simulated"


def contacts(user, include_police=False, only_enabled=True):
    rows = db.q("SELECT * FROM contacts WHERE user_id=? ORDER BY sort, name", (user["id"],))
    out = []
    for c in rows:
        if only_enabled and not c["enabled"]:
            continue
        if c["police"] and not include_police:
            continue
        out.append(c)
    return out


def send(user, recipients, body, related_type=None, related_id=None):
    sent = []
    for c in recipients:
        ch = _channel(c["via"])
        status = _deliver(ch, c["via"], body)
        mid = db.new_id("ob_")
        db.run("INSERT INTO outbox(id,user_id,channel,recipient,body,related_type,related_id,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
               (mid, user["id"], ch, c["name"] + " <" + c["via"] + ">", body, related_type, related_id, status, db.iso()))
        sent.append({"id": mid, "name": c["name"], "via": c["via"], "channel": ch, "status": status})
    return sent


def outbox(user, limit=50):
    return db.q("SELECT id,channel,recipient,body,related_type AS relatedType,related_id AS relatedId,status,created_at AS createdAt "
                "FROM outbox WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (user["id"], limit))
