"""Creates the test account with the same fictional data the mobile prototype uses."""
import logging
from datetime import timedelta

from . import auth, db, mock_data
from .config import settings

log = logging.getLogger("taimi.seed")

DEVICES = [
    ("fridge", "Fridge camera", "camera", 1), ("storage", "Storage cabinet camera", "camera", 1),
    ("basket", "Laundry basket camera", "camera", 1), ("door", "Front door camera", "camera", 1),
    ("watch", "Smart watch", "health", 0),
]
CONTACTS = [("Mum", "WhatsApp · +358 40 ••• 112", 1, 0), ("Sami (brother)", "Telegram · @sami", 1, 0),
            ("Emergency services 112", "Call + SMS with location", 0, 1)]
SOCIAL = [("Instagram", "@alex.k", 1), ("WhatsApp", "+358 40 ••• 908", 1), ("Telegram", "not linked", 0)]
MEMORIES = [("Loves live jazz, especially small venues", "hobby", 12), ("Started bouldering in October", "hobby", 17),
            ("Oat milk, not dairy", "food", 25), ("Wants to visit Lapland this winter", "travel", 33)]
SHOPPING = [("i1", "Oat milk 1 L", 2, 1, "fridge", "Last carton almost empty"), ("i2", "Eggs (10)", 1, 1, "fridge", "None left"),
            ("i3", "Rye bread", 1, 2, "storage", "Bought weekly"), ("i4", "Coffee beans 500 g", 1, 2, "storage", "~3 days left"),
            ("i5", "Toilet paper (8)", 1, 2, "storage", "2 rolls left"), ("i6", "Frozen blueberries", 1, 3, "you", "Added by you"),
            ("i7", "Dish soap", 1, 3, "storage", "Half bottle")]
WARDROBE = [{"cat": "Underwear", "clean": 2, "total": 9, "perDay": 1}, {"cat": "Socks", "clean": 3, "total": 10, "perDay": 1},
            {"cat": "T-shirts", "clean": 3, "total": 8, "perDay": 1}, {"cat": "Jeans / trousers", "clean": 2, "total": 4, "perDay": 0.3},
            {"cat": "Towels", "clean": 1, "total": 4, "perDay": 0.25}, {"cat": "Gym wear", "clean": 0, "total": 3, "perDay": 0.4}]
HEALTH = {"hr": [64, 66, 63, 65, 71, 76, 79], "sleep": [7.4, 7.1, 6.8, 7.2, 5.9, 5.5, 5.2], "steps": [8200, 7600, 9100, 6400, 4300, 3900, 3200]}
TRAIL = [(8.17, "Home · Kallio", 60.1841, 24.9497), (9.75, "University main building", 60.1699, 24.9484),
         (12.33, "Café Regatta", 60.1826, 24.9122), (15.67, "Home · Kallio", 60.1841, 24.9497)]


def seed_user_data(uid):
    now = db.now()
    for key, name, kind, local in DEVICES:
        db.run("INSERT OR IGNORE INTO devices(id,user_id,device_key,name,kind,enabled,last_seen,local_only) VALUES(?,?,?,?,?,?,?,?)",
               (db.new_id("d_"), uid, key, name, kind, 1, db.iso(now - timedelta(minutes=30)), local))
    for i, (name, via, on, police) in enumerate(CONTACTS):
        db.run("INSERT INTO contacts(id,user_id,name,via,enabled,police,sort,verified_at) VALUES(?,?,?,?,?,?,?,?)",
               (db.new_id("c_"), uid, name, via, on, police, i if not police else 999, db.iso()))
    for name, handle, linked in SOCIAL:
        db.run("INSERT INTO social_accounts(id,user_id,name,handle,linked) VALUES(?,?,?,?,?)", (db.new_id("s_"), uid, name, handle, linked))
    for text, tag, days in MEMORIES:
        db.run("INSERT INTO memories(id,user_id,text,tag,source,created_at) VALUES(?,?,?,?,?,?)",
               (db.new_id("m_"), uid, text, tag, "seed", db.iso(now - timedelta(days=days))))
    regular_ids = {}
    for r in mock_data.REGULARS:
        rid = db.new_id("r_")
        regular_ids[r["name"]] = rid
        db.run("INSERT INTO regular_items(id,user_id,label,name,device_key,min_level,prio) VALUES(?,?,?,?,?,?,?)",
               (rid, uid, r["label"], r["name"], r["device"], r["min_level"], r["prio"]))
    for sid, name, qty, prio, origin, note in SHOPPING:
        db.run("INSERT INTO shopping_items(id,user_id,name,qty,prio,origin,note,regular_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
               (uid[-6:] + sid, uid, name, qty, prio, origin, note, regular_ids.get(name), db.iso()))
    db.set_state(uid, "stores", mock_data.STORES)
    db.set_state(uid, "wardrobe", WARDROBE)
    db.set_state(uid, "checkin_config", {"every": 24, "grace": 2, "nextHour": 21, "streak": 11})
    db.set_state(uid, "door_settings", {"loiterSeconds": 60, "alerts": True})
    db.set_state(uid, "today", {"date": None, "done": {}})
    for i in range(7):
        day = (now - timedelta(days=6 - i)).date().isoformat()
        db.run("INSERT OR REPLACE INTO vitals(user_id,day,hr,sleep,steps) VALUES(?,?,?,?,?)",
               (uid, day, HEALTH["hr"][i], HEALTH["sleep"][i], HEALTH["steps"][i]))
    # basket observation + door events from the mocked camera frames
    from .services import laundry, safety  # local import to avoid cycles
    laundry.record_basket(uid, mock_data.CAMERA_FRAMES["basket"][0])
    for frame in mock_data.CAMERA_FRAMES["door"]:
        safety.ingest_door_frame({"id": uid}, frame, seeded=True)
    db.run("INSERT INTO agent_posts(id,user_id,text,sources,channel,topic,created_at) VALUES(?,?,?,?,?,?,?)",
           (db.new_id("ap_"), uid, "Found a bouldering gym doing beginner technique nights on Tuesdays, thought of you 🧗",
            db.dumps([{"title": "Gym schedule", "url": "https://www.boulderkeskus.com/"}]), "instagram", "bouldering",
            db.iso(now - timedelta(hours=2))))
    db.run("INSERT INTO agent_posts(id,user_id,text,sources,channel,topic,created_at) VALUES(?,?,?,?,?,?,?)",
           (db.new_id("ap_"), uid, "Northern lights forecast looks strong for Lapland next weekend 🌌",
            db.dumps([{"title": "Aurora forecast", "url": "https://www.ilmatieteenlaitos.fi/revontulet-ja-avaruussaa"}]),
            "instagram", "lapland", db.iso(now - timedelta(days=1))))
    for msg in [{"text": "Morning! ☕ Your coffee beans are running low btw, I popped them on the list."}]:
        db.run("INSERT INTO chat_messages(id,user_id,role,payload,created_at) VALUES(?,?,?,?,?)",
               (db.new_id("cm_"), uid, "bot", db.dumps(msg), db.iso(now - timedelta(hours=3))))


def seed_location_trail(user):
    from .services.calendar import at_local
    for h, label, lat, lng in TRAIL:
        at = at_local(user, 0, h)
        if at <= db.now():
            db.run("INSERT INTO locations(id,user_id,at,lat,lng,accuracy_m,label) VALUES(?,?,?,?,?,?,?)",
                   (db.new_id("l_"), user["id"], db.iso(at), lat, lng, 10, label))


def ensure_test_account():
    row = db.q1("SELECT id FROM users WHERE email=?", (settings.test_email,))
    if row:
        return row["id"]
    uid = auth.create_user(settings.test_email, settings.test_password, "Alex", home="Kallio, Helsinki", city="Helsinki",
                           country="FI", timezone="Europe/Helsinki", currency="EUR", lat=60.1841, lng=24.9497, site_region="FI")
    db.set_state(uid, "demo_account", True)
    for scope in ("memory", "location_trail", "camera_derived_inventory", "health_device", "social_sharing"):
        db.run("INSERT INTO consents(id,user_id,scope,granted_at) VALUES(?,?,?,?)", (db.new_id("cs_"), uid, scope, db.iso()))
    seed_user_data(uid)
    user = db.q1("SELECT * FROM users WHERE id=?", (uid,))
    seed_location_trail(user)
    log.info("Created test account %s", settings.test_email)
    return uid
