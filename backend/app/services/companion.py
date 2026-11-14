"""Companionship: daily chat (a Claude agent whose only search tool is Exa),
consented memories, background interest research shared from the agent's own
social account, and calls.

Safety rules: on signs of crisis Sola only *asks* for permission to contact a
trusted person and shows support lines; it never sends anything without an
explicit yes, and never encourages harmful behaviour."""
import re
from datetime import timedelta

from .. import agents, db, exa_client, llm
from ..config import settings
from ..errors import ApiError
from . import messaging

CRISIS = re.compile(r"\b(hurt myself|self[- ]?harm|end it|kill myself|suicid\w*|don'?t want to live|want to die)\b", re.I)

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
    rows = db.q("SELECT role,payload,created_at FROM chat_messages WHERE user_id=? ORDER BY created_at DESC, rowid DESC LIMIT ?", (user["id"], limit))
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
        if r.get("text") not in (OFFLINE, RETRY):
            _log(user, "bot", r, consent)
    return res


# ------------------------------------------------------------- chat agent
# Every chat message is answered by the Claude agent. Its tools are the only
# things it can reach: Exa is its single search tool (no Anthropic server-side
# web search is enabled), plus read-only access to the user's own data,
# memory saving (consent-gated) and an offer to contact a trusted person
# (which only shows a prompt; sending needs the user's explicit yes).
SEARCH_TOOL = "exa_search"
TOOLS = [
    {"name": SEARCH_TOOL,
     "description": "Search the web with Exa. This is your ONLY way to look anything up: use it for any fact, event, "
                    "opening hours, price, news, place or recommendation you are not certain about. Results are numbered; "
                    "cite them in your reply as [1], [2]. Keep queries short and specific; add the user's city for local things.",
     "input_schema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "What to search for."},
         "recent_only": {"type": "boolean", "description": "Only results from the last 30 days (events, news, what's on)."}},
         "required": ["query"], "additionalProperties": False}},
    {"name": "read_my_data",
     "description": "Read the user's own data in Sola (not a web search): 'sleep' = last nights from their watch, "
                    "'recent_groceries' = what they bought lately, 'shopping_list' = items still to buy.",
     "input_schema": {"type": "object", "properties": {
         "kind": {"type": "string", "enum": ["sleep", "recent_groceries", "shopping_list"]}},
         "required": ["kind"], "additionalProperties": False}},
    {"name": "save_memory",
     "description": "Remember a lasting preference or fact the user shared about themselves (e.g. 'Likes board games', "
                    "\"Doesn't like horror films\"). Short, third person, no sensitive health details.",
     "input_schema": {"type": "object", "properties": {"text": {"type": "string"}},
                      "required": ["text"], "additionalProperties": False}},
    {"name": "offer_reach_out",
     "description": "Show the user a button offering to message someone they trust that they could use company. "
                    "Use when they seem low, lonely or struggling. It sends nothing by itself; the user must tap yes.",
     "input_schema": {"type": "object", "properties": {"reason": {"type": "string"}},
                      "required": ["reason"], "additionalProperties": False}},
]
assert [x["name"] for x in TOOLS if "search" in x["name"]] == [SEARCH_TOOL] and all("type" not in x for x in TOOLS)

AGENT_RULES = (
    "\n\nHow you work:\n"
    "- Small talk is just small talk: reply like a friend, no tools.\n"
    "- Call exa_search only when they ask for information you'd have to look up (places, events, opening hours, prices, "
    "news, facts). It is the only search you have; never answer those from memory. If it fails or finds nothing useful, "
    "say you couldn't find it.\n"
    "- Cite search results inline as [n] using the numbers you were given. Never write URLs yourself.\n"
    "- Use read_my_data for questions about their sleep, groceries or shopping list.\n"
    "- When they share a new lasting like or dislike, call save_memory (skip it if you already remember it). If memory "
    "is off it tells you so: then ask whether they'd like to turn memory on instead of claiming you remembered.\n"
    "- Call offer_reach_out only when they clearly say they feel low, lonely, anxious or are struggling (not for being "
    "tired, busy or having a long day), and at most once a conversation. The app shows the button, so don't mention it.\n"
    "- Don't comment on your own earlier replies or errors. Reply in plain text (no markdown), 1-3 short sentences, "
    "like a friend texting.")
CRISIS_NOTE = ("\n\nThis message suggests they may be in crisis. The app is already showing them a button to contact someone "
               "they trust and a crisis helpline, so don't repeat those. Be warm, take it seriously, stay with them, and "
               "gently encourage them to accept help. Don't search.")
CRISIS_CARD = ("Hey, I'm really glad you told me. You matter a lot, and you don't have to go through this alone. "
               "Can I reach out to someone you trust right now? I'll only do it if you say yes.")
CARE_CARD = "If it'd help, I can quietly let someone you trust know you could use some company. Only with your OK though."
OFFLINE = "I can't think straight right now, my brain isn't connected 😅 Try me again in a bit?"
RETRY = "Sorry, I lost my train of thought there 🙈 Can you say that again?"
CITE = re.compile(r"\s?\[(\d{1,2})\]")


def _context(user, consent, ctx):
    today = db.now().strftime("%A %-d %B %Y")
    where = ", ".join(x for x in (user.get("home"), user.get("city"), user.get("country")) if x)
    mems = []
    if consent:
        mems = [r["text"] for r in memories(user)[:12]] if has_consent(user, "memory") else [str(m)[:200] for m in (ctx.get("memories") or [])[:12]]
    lines = ["\n\nAbout the user: name %s; lives in %s; today is %s." % (user.get("display_name") or "unknown", where or "unknown", today),
             "Memory is %s." % ("on" if consent else "off: don't save anything")]
    if mems:
        lines.append("Things you remember about them: " + "; ".join(mems))
    return "\n".join(lines)


def _turns(user, t, consent):
    rows = history(user, 12) if consent else []
    msgs = []
    for h in rows:
        txt = (h.get("text") or "").strip()
        if not txt or txt in (OFFLINE, RETRY):
            continue
        role = "assistant" if h["from"] == "bot" else "user"
        if msgs and msgs[-1]["role"] == role:
            msgs[-1]["content"] += "\n" + txt
        else:
            msgs.append({"role": role, "content": txt})
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    if not msgs or msgs[-1]["role"] != "user" or not msgs[-1]["content"].endswith(t):
        if msgs and msgs[-1]["role"] == "user":
            msgs[-1]["content"] += "\n" + t
        else:
            msgs.append({"role": "user", "content": t})
    return msgs


def _reply(user, t, consent, ctx):
    crisis = bool(CRISIS.search(t))
    state = {"results": [], "memory": None, "care": crisis, "link": None, "searched": False}

    def execute(name, args):
        if name == SEARCH_TOOL:
            q = " ".join(str(args.get("query") or "").split())[:300]
            if not q:
                raise ValueError("query is required")
            since = (db.now() - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00.000Z") if args.get("recent_only") else None
            res = exa_client.search(user["id"], "chat", q, num_results=5, user_location=user.get("country"), start_published_date=since)
            state["searched"] = True
            if not res.get("available"):
                return "Search unavailable (%s). Tell the user you couldn't look it up right now; don't guess." % res.get("reason", "error")
            if not res["results"]:
                return "No results."
            out = []
            for r in res["results"]:
                state["results"].append(r)
                n = len(state["results"])
                bits = [r.get("title") or r["domain"], r["domain"]] + ([r["publishedDate"][:10]] if r.get("publishedDate") else [])
                out.append("[%d] %s\n%s" % (n, " · ".join(bits), " … ".join(r.get("highlights") or [])[:900]))
            return "\n\n".join(out)
        if name == "read_my_data":
            kind = args.get("kind")
            if kind == "sleep":
                v = db.q("SELECT day,sleep FROM vitals WHERE user_id=? AND sleep IS NOT NULL ORDER BY day DESC LIMIT 5", (user["id"],))
                state["link"] = "#/health"
                return "; ".join("%s: %.1f h" % (x["day"], x["sleep"]) for x in v) or "No sleep data."
            if kind == "recent_groceries":
                rows = db.q("SELECT name,bought FROM shopping_items WHERE user_id=? AND bought IS NOT NULL ORDER BY bought DESC LIMIT 8", (user["id"],))
                return ", ".join(r["name"] for r in rows) or "Nothing bought recently."
            if kind == "shopping_list":
                rows = db.q("SELECT name,prio FROM shopping_items WHERE user_id=? AND bought IS NULL ORDER BY prio, created_at LIMIT 15", (user["id"],))
                state["link"] = "#/shopping"
                return ", ".join(r["name"] + (" (urgent)" if r["prio"] == 1 else "") for r in rows) or "The list is empty."
            raise ValueError("unknown kind")
        if name == "save_memory":
            txt = " ".join(str(args.get("text") or "").split())[:120]
            if not txt:
                raise ValueError("text is required")
            if not consent:
                return "Memory is off, nothing saved. Ask if they'd like to turn memory on."
            state["memory"] = txt
            if has_consent(user, "memory"):
                add_memory(user, txt, _guess_tag(txt))
            return "Saved. Now reply to them."
        if name == "offer_reach_out":
            state["care"] = True
            return ("The offer button is now shown under your message. Still write your reply: be warm, talk with them, "
                    "don't mention the button and don't say you contacted anyone.")
        raise ValueError("unknown tool")

    system = (PERSONA.format(name=settings.agent_name) + AGENT_RULES + _context(user, consent, ctx)
              + (CRISIS_NOTE if crisis else ""))
    tools = [x for x in TOOLS if x["name"] != SEARCH_TOOL] if crisis else TOOLS
    out = llm.run_agent(system, _turns(user, t, consent), tools, execute, max_steps=5, max_tokens=4096, effort="low")

    replies = []
    if crisis:
        replies.append({"kind": "care", "crisis": True, "text": CRISIS_CARD})
    if out:
        cited = [int(n) for n in CITE.findall(out)]
        text = CITE.sub("", out).strip()[:700]
        reply = {"text": text}
        picked = [state["results"][n - 1] for n in dict.fromkeys(cited) if 0 < n <= len(state["results"])]
        if picked or state["results"]:
            reply["kind"] = "find"
            reply["sources"] = exa_client.sources_from(picked or state["results"][:2], 4)
        if state["link"]:
            reply["link"] = state["link"]
        replies.append(reply)
    elif not crisis:
        replies.append({"text": OFFLINE if not llm.available() else RETRY})
    if state["care"] and not crisis:
        replies.append({"kind": "care", "text": CARE_CARD})
    if crisis:
        line, src = _support(user)
        replies.append({"text": "And if you want to talk to someone right now: " + line, "sources": [src]})
    res = {"replies": replies, "agent": bool(out)}
    if state["memory"]:
        res["memory"] = state["memory"]
    return res


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
