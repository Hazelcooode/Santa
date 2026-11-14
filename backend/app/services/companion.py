"""Companionship: casual daily chat, consented memories, background interest
research shared from the agent's own social account, and calls.

Safety rules: on signs of crisis Taimi only *asks* for permission to contact a
trusted person and shows support lines; it never sends anything without an
explicit yes, and never encourages harmful behaviour."""
import random
import re
from datetime import timedelta

from .. import agents, db, exa_client, llm
from ..config import settings
from ..errors import ApiError
from . import messaging

DISTRESS = re.compile(r"\b(sad|lonely|alone|depress\w*|anxious|anxiety|hopeless|worthless|can'?t cope|cry(ing)?|panic|empty|hurt myself|self[- ]?harm|end it|give up)\b", re.I)
CRISIS = re.compile(r"\b(hurt myself|self[- ]?harm|end it|kill myself|suicid\w*|don'?t want to live|want to die)\b", re.I)
PREF = re.compile(r"\bi (?:really )?(?:love|like|enjoy|am into|'m into|prefer|hate|don'?t like)\s+(.+?)[.!?]*$", re.I)
INFO = re.compile(r"^(what|where|when|who|which|how|is there|are there|any|can you find|find|recommend|tell me about)\b|\?$", re.I)

SUPPORT_LINES = {
    "FI": ("MIELI Crisis Helpline: 09 2525 0111 (24/7). In an emergency, call 112.", {"title": "MIELI Mental Health Finland", "url": "https://mieli.fi/en/"}),
    "default": ("You can find a free, confidential helpline in your country at findahelpline.com. In an emergency, call your local emergency number.",
                {"title": "Find A Helpline", "url": "https://findahelpline.com/"}),
}

PERSONA = ("You are {name}, a warm, casual friend-like assistant for a young person who lives alone. Talk like a close friend: short "
           "(1-3 sentences), relaxed, an emoji now and then. Use the user's remembered preferences when relevant. Never give "
           "medical, legal or financial advice beyond gentle general tips. Never encourage anything harmful to the user or others. "
           "If they seem to be struggling, be kind and ask if they'd like you to reach out to someone they trust; never claim you did "
           "something you didn't. Don't invent facts, events, prices or links.")


def has_consent(user, scope):
    return bool(db.q1("SELECT 1 FROM consents WHERE user_id=? AND scope=? AND revoked_at IS NULL", (user["id"], scope)))


def set_consent(user, scope, granted):
    if granted and not has_consent(user, scope):
        db.run("INSERT INTO consents(id,user_id,scope,granted_at) VALUES(?,?,?,?)", (db.new_id("cs_"), user["id"], scope, db.iso()))
    elif not granted:
        db.run("UPDATE consents SET revoked_at=? WHERE user_id=? AND scope=? AND revoked_at IS NULL", (db.iso(), user["id"], scope))
    return {"scope": scope, "granted": bool(granted)}


# ------------------------------------------------------------------ memories
def memories(user):
    rows = db.q("SELECT id,text,tag,source,created_at FROM memories WHERE user_id=? ORDER BY created_at DESC", (user["id"],))
    for r in rows:
        r["date"] = db.parse_iso(r["created_at"]).strftime("%-d %b")
    return rows


def add_memory(user, text, tag="chat", source="chat"):
    if not has_consent(user, "memory"):
        raise ApiError(403, "CONSENT_REQUIRED", "Memory is off. Turn it on first.")
    text = " ".join((text or "").split())[:200]
    if not text:
        raise ApiError(400, "INVALID_INPUT", "Memory text is required.")
    mid = db.new_id("m_")
    db.run("INSERT INTO memories(id,user_id,text,tag,source,created_at) VALUES(?,?,?,?,?,?)", (mid, user["id"], text, tag[:20], source, db.iso()))
    return {"id": mid, "text": text, "tag": tag}


def delete_memory(user, mid):
    db.run("DELETE FROM memories WHERE id=? AND user_id=?", (mid, user["id"]))


def _guess_tag(thing):
    low = thing.lower()
    if re.search(r"food|milk|eat|cook|vegan|coffee|tea|pizza|sushi", low):
        return "food"
    if re.search(r"travel|trip|visit|lapland|beach|city", low):
        return "travel"
    return "hobby"


# ---------------------------------------------------------------------- chat
def _log(user, role, payload, persist):
    if persist:
        db.run("INSERT INTO chat_messages(id,user_id,role,payload,created_at) VALUES(?,?,?,?,?)",
               (db.new_id("cm_"), user["id"], role, db.dumps(payload), db.iso()))


def history(user, limit=50):
    rows = db.q("SELECT role,payload,created_at FROM chat_messages WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (user["id"], limit))
    return [dict(db.loads(r["payload"], {}), **{"from": r["role"], "at": r["created_at"]}) for r in reversed(rows)]


def _support(user):
    return SUPPORT_LINES.get((user.get("country") or "").upper(), SUPPORT_LINES["default"])


def chat(user, text, ctx=None):
    ctx = ctx or {}
    t = (text or "").strip()[:1000]
    if not t:
        raise ApiError(400, "INVALID_INPUT", "Say something first.")
    consent = ctx.get("memoryConsent")
    consent = has_consent(user, "memory") if consent is None else bool(consent)
    _log(user, "me", {"text": t}, consent)
    res = _reply(user, t, consent, ctx)
    for r in res["replies"]:
        _log(user, "bot", r, consent)
    return res


def _reply(user, t, consent, ctx):
    low = t.lower()
    name = user.get("display_name") or "you"
    if CRISIS.search(low):
        line, src = _support(user)
        return {"replies": [{"kind": "care", "crisis": True,
                             "text": "Hey, I'm really glad you told me. You matter a lot, and you don't have to go through this alone. "
                                     "Can I reach out to someone you trust right now? I'll only do it if you say yes."},
                            {"text": "And if you want to talk to someone right now: " + line, "sources": [src]}]}
    if DISTRESS.search(low):
        return {"replies": [{"text": "Ah, that sounds really heavy. I'm here, no rush. Want to tell me a bit more about what's going on?"},
                            {"kind": "care", "text": "If it'd help, I can quietly let someone you trust know you could use some company. Only with your OK though."}]}

    m = PREF.search(t)
    if m:
        thing = " ".join(m.group(1).split())[:120]
        memory = ("Doesn't like " if re.search(r"hate|don'?t like", t, re.I) else "Likes ") + thing
        res = {"replies": [{"text": "Ooh, noted! " + ("I'll keep an eye out for %s stuff for you 👀" % thing if consent
                                                       else "Want me to remember that? Memory is off right now.")}]}
        if consent:
            res["memory"] = memory
            if has_consent(user, "memory"):
                add_memory(user, memory, _guess_tag(thing))
        return res

    if re.search(r"weekend|event|bored|do tonight|what's on|whats on", low):
        ev = agents.run(user, "events", {"query": t if len(t) > 12 else "", "interests": [r["text"] for r in memories(user)[:3]]})
        top = ev.get("results", [])[:2]
        if top:
            txt = "Bored? Say no more 😄 " + " Also: ".join("%s (%s)" % (e["title"], e["when"]) for e in top)
            srcs = [s for e in top for s in e.get("sources", [])[:1]]
            return {"replies": [{"kind": "find", "text": txt, "sources": srcs, "link": "#/explore"}], "mode": ev.get("mode")}

    if re.search(r"tired|sleep|exhausted", low):
        v = db.q("SELECT sleep FROM vitals WHERE user_id=? ORDER BY day DESC LIMIT 3", (user["id"],))
        short = [x["sleep"] for x in v if x["sleep"] is not None and x["sleep"] < 6]
        msg = ("Your watch agrees, you've been under 6 h of sleep for %d nights 😴 Early night? I put some ideas in Health." % len(short)
               if len(short) >= 2 else "Rough one? Maybe an early night tonight 😴 I put some ideas in Health.")
        return {"replies": [{"text": msg, "link": "#/health"}]}

    if re.search(r"hungry|dinner|cook|recipe|eat", low):
        have = [r["name"] for r in db.q("SELECT name FROM shopping_items WHERE user_id=? AND bought IS NOT NULL ORDER BY created_at DESC LIMIT 3", (user["id"],))]
        return {"replies": [{"text": ("You've got %s from the last shop. Something quick with those? 🍳" % ", ".join(have)) if have
                             else "Hmm, how about something quick like shakshuka or a stir-fry? 🍳 I can add the ingredients to your list."}]}

    if re.match(r"^(hi|hey|hello|moi|morning|yo)\b", low):
        return {"replies": [{"text": "Heyy %s 👋 How's your day going so far?" % name.split()[0]}]}
    if "thank" in low:
        return {"replies": [{"text": "Anytime! That's what friends are for 🫶"}]}

    if INFO.search(t):
        ans = exa_client.answer(user["id"], t + (" (near %s)" % user["city"] if user.get("city") and re.search(r"near|around|here|local", low) else ""),
                                user.get("country"))
        if ans.get("available") and ans.get("answer"):
            return {"replies": [{"kind": "find", "text": _casual(ans["answer"]), "sources": ans["citations"]}]}

    if llm.available():
        mem = "; ".join(r["text"] for r in memories(user)[:8]) if consent else ""
        system = PERSONA.format(name=settings.agent_name) + (" Things you remember about them: " + mem if mem else "")
        turns = [("model" if h["from"] == "bot" else "user", h.get("text", "")) for h in history(user, 10) if h.get("text")]
        if not turns or turns[-1][1] != t:
            turns.append(("user", t))
        out = llm.complete(system, turns)
        if out:
            return {"replies": [{"text": out[:600]}]}
    return {"replies": [{"text": random.choice(["Haha fair. Tell me more?", "Okay, I'm listening 👂 what happened next?",
                                                "Honestly same. Anything I can sort out for you today?",
                                                "Love that. Want me to dig up anything related?"])}]}


def _casual(answer):
    a = " ".join(answer.split())
    if len(a) > 420:
        a = a[:400].rsplit(" ", 1)[0] + "…"
    return "Okay so, from what I found: " + a


# --------------------------------------------------- interest research + social
def interest_topics(user):
    rows = db.q("SELECT text FROM memories WHERE user_id=? AND tag IN ('hobby','travel','chat') ORDER BY created_at DESC LIMIT 6", (user["id"],))
    topics = []
    for r in rows:
        txt = re.sub(r"^(likes|loves|started|wants to visit|wants to)\s+", "", r["text"], flags=re.I)
        txt = re.sub(r",.*$|\bin \w+$|\bthis \w+$", "", txt).strip()
        if txt and not txt.lower().startswith("doesn't"):
            topics.append(" ".join(txt.split()[:4]))
    return list(dict.fromkeys(topics))[:3]


def refresh_posts(user, force=False):
    """Background research on the user's interests (max once per 12 h unless forced)."""
    last = db.get_state(user["id"], "interests_refreshed_at")
    if not force and last and db.parse_iso(last) > db.now() - timedelta(hours=12):
        return {"refreshed": False, "posts": posts(user)}
    topics = interest_topics(user) if has_consent(user, "memory") else []
    new = []
    if topics:
        res = agents.run(user, "interests", {"topics": topics})
        known = {p["text"] for p in posts(user, 50)}
        for p in res.get("posts", []):
            if p["text"] in known:
                continue
            pid = db.new_id("ap_")
            db.run("INSERT INTO agent_posts(id,user_id,text,sources,channel,topic,created_at) VALUES(?,?,?,?,?,?,?)",
                   (pid, user["id"], p["text"], db.dumps(p["sources"]), "instagram", p["topic"], db.iso()))
            new.append(p)
        if new and has_consent(user, "social_sharing"):
            linked = db.q("SELECT * FROM social_accounts WHERE user_id=? AND linked=1", (user["id"],))
            if linked:
                acct = linked[0]
                messaging.send(user, [{"name": acct["name"], "via": acct["name"] + " " + acct["handle"]}],
                               "@%s.agent shared %d new find(s) with you" % (settings.agent_name.lower(), len(new)), "agent_post", None)
    db.set_state(user["id"], "interests_refreshed_at", db.iso())
    return {"refreshed": True, "topics": topics, "new": len(new), "posts": posts(user)}


def _ago(dt):
    s = (db.now() - dt).total_seconds()
    if s < 3600:
        return "%d min ago" % max(1, s // 60)
    if s < 86400:
        return "%d h ago" % (s // 3600)
    return "yesterday" if s < 172800 else "%d days ago" % (s // 86400)


def posts(user, limit=10):
    rows = db.q("SELECT * FROM agent_posts WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (user["id"], limit))
    return [{"id": r["id"], "text": r["text"], "when": _ago(db.parse_iso(r["created_at"])), "sources": db.loads(r["sources"], []),
             "channel": r["channel"], "topic": r["topic"], "createdAt": r["created_at"]} for r in rows]


def social(user):
    return [{"id": r["id"], "name": r["name"], "handle": r["handle"], "on": bool(r["linked"])}
            for r in db.q("SELECT * FROM social_accounts WHERE user_id=? ORDER BY rowid", (user["id"],))]


def set_social(user, sid, linked, handle=None):
    row = db.q1("SELECT * FROM social_accounts WHERE id=? AND user_id=?", (sid, user["id"]))
    if not row:
        raise ApiError(404, "NOT_FOUND", "Account not found.")
    h = handle or row["handle"]
    if linked and h == "not linked":
        h = "@" + (user.get("display_name") or "me").lower()
    db.run("UPDATE social_accounts SET linked=?, handle=? WHERE id=?", (1 if linked else 0, h, sid))
    return social(user)


def start_call(user, kind):
    if kind not in ("voice", "video", "social"):
        raise ApiError(400, "INVALID_INPUT", "kind must be voice, video or social.")
    linked = [s for s in social(user) if s["on"]]
    return {"callId": db.new_id("call_"), "kind": kind, "agent": settings.agent_name,
            "agentHandle": "@%s.agent" % settings.agent_name.lower(),
            "via": linked[0]["name"] if kind == "social" and linked else "in-app",
            "status": "connected", "simulated": True}
