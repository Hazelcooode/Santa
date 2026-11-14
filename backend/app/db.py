"""SQLite persistence. One file, WAL mode, a connection per thread.

SQLite keeps the hackathon deployment dependency-free. Every user-owned row has
user_id and every query in the services is scoped by it. Money is stored as
integer minor units; NULL means unknown.
"""
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from .config import settings

_local = threading.local()
_init_lock = threading.Lock()
_initialised_paths = set()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  display_name TEXT NOT NULL,
  home TEXT, city TEXT, country TEXT, timezone TEXT DEFAULT 'UTC',
  locale TEXT DEFAULT 'en', currency TEXT DEFAULT 'EUR',
  lat REAL, lng REAL,
  site_region TEXT,               -- ISO country code(s) whose websites agents should search
  preferred_domains TEXT DEFAULT '[]',
  created_at TEXT NOT NULL, deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL, expires_at TEXT NOT NULL, user_agent TEXT
);
CREATE TABLE IF NOT EXISTS consents (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, scope TEXT NOT NULL,
  granted_at TEXT NOT NULL, revoked_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS consents_active ON consents(user_id, scope) WHERE revoked_at IS NULL;
CREATE TABLE IF NOT EXISTS user_state (
  user_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, key)
);
CREATE TABLE IF NOT EXISTS memories (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, text TEXT NOT NULL, tag TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'chat', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS devices (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, device_key TEXT NOT NULL, name TEXT NOT NULL,
  kind TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, last_seen TEXT, local_only INTEGER NOT NULL DEFAULT 1,
  UNIQUE(user_id, device_key)
);
CREATE TABLE IF NOT EXISTS contacts (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL, via TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1, police INTEGER NOT NULL DEFAULT 0, sort INTEGER NOT NULL DEFAULT 0,
  verified_at TEXT
);
CREATE TABLE IF NOT EXISTS social_accounts (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL, handle TEXT NOT NULL,
  linked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS shopping_items (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
  qty REAL NOT NULL DEFAULT 1 CHECK (qty > 0), prio INTEGER NOT NULL DEFAULT 2 CHECK (prio BETWEEN 1 AND 3),
  origin TEXT NOT NULL DEFAULT 'you', note TEXT, bought TEXT, regular_id TEXT,
  version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS regular_items (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, label TEXT NOT NULL, name TEXT NOT NULL,
  device_key TEXT NOT NULL, min_level REAL NOT NULL DEFAULT 0.25, prio INTEGER NOT NULL DEFAULT 2
);
CREATE TABLE IF NOT EXISTS inventory_observations (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, device_key TEXT NOT NULL, frame_id TEXT,
  detections TEXT NOT NULL, observed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS calendar_events (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL,
  start_at TEXT NOT NULL, end_at TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'busy', source TEXT NOT NULL DEFAULT 'calendar'
);
CREATE TABLE IF NOT EXISTS laundry_bookings (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, slot_start TEXT NOT NULL, slot_end TEXT NOT NULL,
  machine TEXT NOT NULL, label TEXT NOT NULL, slot_key TEXT, status TEXT NOT NULL DEFAULT 'booked',
  calendar_event_id TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vitals (
  user_id TEXT NOT NULL, day TEXT NOT NULL, hr REAL, sleep REAL, steps INTEGER,
  PRIMARY KEY (user_id, day)
);
CREATE TABLE IF NOT EXISTS door_events (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, at TEXT NOT NULL, title TEXT NOT NULL, kind TEXT NOT NULL,
  detail TEXT, person TEXT, dwell_s INTEGER, knocked INTEGER, reviewed TEXT
);
CREATE TABLE IF NOT EXISTS checkins (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, confirmed_at TEXT NOT NULL, method TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS locations (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, at TEXT NOT NULL, lat REAL NOT NULL, lng REAL NOT NULL,
  accuracy_m REAL, label TEXT
);
CREATE TABLE IF NOT EXISTS sos_events (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, at TEXT NOT NULL, type TEXT, lat REAL, lng REAL,
  accuracy_m REAL, police INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'active', resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS escalations (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, reason TEXT NOT NULL, due_at TEXT, created_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'sent', resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS outbox (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, channel TEXT NOT NULL, recipient TEXT NOT NULL,
  body TEXT NOT NULL, related_type TEXT, related_id TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_messages (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, role TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_posts (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, text TEXT NOT NULL, sources TEXT NOT NULL,
  channel TEXT NOT NULL DEFAULT 'instagram', topic TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bookings (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
  status TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products_seen (
  id TEXT NOT NULL, user_id TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (user_id, id)
);
CREATE TABLE IF NOT EXISTS exa_cache (
  key TEXT PRIMARY KEY, kind TEXT NOT NULL, response TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS exa_ledger (
  id TEXT PRIMARY KEY, user_id TEXT, at TEXT NOT NULL, kind TEXT NOT NULL, query TEXT,
  cost_usd REAL NOT NULL DEFAULT 0, estimated INTEGER NOT NULL DEFAULT 0, cached INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'ok'
);
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, intent TEXT NOT NULL, request TEXT NOT NULL,
  constraints TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL, progress TEXT, proposal_id TEXT,
  missing_fields TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_steps (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, task_id TEXT NOT NULL, role TEXT NOT NULL, seq INTEGER NOT NULL,
  status TEXT NOT NULL, summary TEXT, duration_ms INTEGER, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, task_id TEXT, url TEXT NOT NULL, title TEXT,
  domain TEXT, excerpt TEXT, image TEXT, published_at TEXT, fetched_at TEXT NOT NULL,
  expires_at TEXT, applicable_location TEXT, retrieval_status TEXT NOT NULL DEFAULT 'ok',
  verification TEXT NOT NULL DEFAULT 'unverified'
);
CREATE TABLE IF NOT EXISTS proposals (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, task_id TEXT, kind TEXT NOT NULL, version INTEGER NOT NULL,
  status TEXT NOT NULL, payload TEXT NOT NULL, payload_hash TEXT NOT NULL, expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS actions (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, proposal_id TEXT NOT NULL, type TEXT NOT NULL,
  status TEXT NOT NULL, idempotency_key TEXT NOT NULL, request_hash TEXT NOT NULL,
  result TEXT, created_at TEXT NOT NULL,
  UNIQUE(user_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS price_watches (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, data TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active',
  version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_observations (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, watch_id TEXT NOT NULL, at TEXT NOT NULL,
  price_minor INTEGER, currency TEXT, title TEXT, url TEXT, store TEXT
);
CREATE TABLE IF NOT EXISTS media_assets (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS shopping_user ON shopping_items(user_id, prio);
CREATE INDEX IF NOT EXISTS cal_user ON calendar_events(user_id, start_at);
CREATE INDEX IF NOT EXISTS loc_user ON locations(user_id, at);
CREATE INDEX IF NOT EXISTS ledger_at ON exa_ledger(at);
CREATE INDEX IF NOT EXISTS tasks_user ON tasks(user_id, created_at);
"""


def now():
    return datetime.now(timezone.utc)


def iso(dt=None):
    return (dt or now()).astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_iso(s):
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def new_id(prefix=""):
    return prefix + uuid.uuid4().hex[:16]


def dumps(v):
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))


def loads(s, default=None):
    if s is None:
        return default
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return default


def connect(path=None):
    path = path or settings.db_path
    conn = getattr(_local, "conn", None)
    if conn is not None and getattr(_local, "path", None) == path:
        return conn
    if path != ":memory:":
        os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=15, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    if path != ":memory:":
        conn.execute("PRAGMA journal_mode=WAL")
    with _init_lock:
        if path not in _initialised_paths:
            conn.executescript(SCHEMA)
            _initialised_paths.add(path)
    _local.conn = conn
    _local.path = path
    return conn


def reset_connection():
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
    _local.conn = None
    _local.path = None
    _initialised_paths.clear()


def q(sql, params=()):
    return [dict(r) for r in connect().execute(sql, params).fetchall()]


def q1(sql, params=()):
    r = connect().execute(sql, params).fetchone()
    return dict(r) if r else None


def run(sql, params=()):
    return connect().execute(sql, params)


class tx:
    """Explicit transaction: `with tx(): ...` (connection is in autocommit mode)."""

    def __enter__(self):
        connect().execute("BEGIN IMMEDIATE")
        return self

    def __exit__(self, exc_type, exc, tb):
        connect().execute("ROLLBACK" if exc_type else "COMMIT")
        return False


# ---------------- small key/value store for per-user documents ---------------
def get_state(user_id, key, default=None):
    row = q1("SELECT value FROM user_state WHERE user_id=? AND key=?", (user_id, key))
    return loads(row["value"], default) if row else default


def set_state(user_id, key, value):
    run(
        "INSERT INTO user_state(user_id,key,value,updated_at) VALUES(?,?,?,?) "
        "ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (user_id, key, dumps(value), iso()),
    )
    return value
