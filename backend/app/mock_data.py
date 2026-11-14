"""Demo fixtures, ported from mobile/data.js so demo answers match the
prototype exactly. Used when Exa is unavailable (no key, budget cap, mock mode)
and always labelled `mode: "demo"` in responses. Also holds the mocked camera
frames that stand in for on-device video analysis."""
import copy
import re


def src(title, url):
    return {"title": title, "url": url}


STORES = [
    {"id": "prisma", "name": "Prisma Kalasatama", "mall": "REDI mall", "dist": 1.4, "url": "https://www.s-kaupat.fi/", "domain": "s-kaupat.fi", "lat": 60.1873, "lng": 24.9776},
    {"id": "kcm", "name": "K-Citymarket Itäkeskus", "mall": "Itis mall", "dist": 6.2, "url": "https://www.k-ruoka.fi/", "domain": "k-ruoka.fi", "lat": 60.2107, "lng": 25.0820},
    {"id": "lidl", "name": "Lidl Sörnäinen", "mall": None, "dist": 0.9, "url": "https://www.lidl.fi/", "domain": "lidl.fi", "lat": 60.1866, "lng": 24.9628},
    {"id": "alepa", "name": "Alepa Kallio", "mall": None, "dist": 0.3, "url": "https://www.s-kaupat.fi/", "domain": "s-kaupat.fi", "lat": 60.1838, "lng": 24.9504},
    {"id": "kmkt", "name": "K-Market Redi", "mall": "REDI mall", "dist": 1.4, "url": "https://www.k-ruoka.fi/", "domain": "k-ruoka.fi", "lat": 60.1873, "lng": 24.9776},
    {"id": "ksm-kamppi", "name": "K-Supermarket Kamppi", "mall": "Kamppi centre", "dist": 2.3, "url": "https://www.k-ruoka.fi/", "domain": "k-ruoka.fi", "lat": 60.1690, "lng": 24.9320},
]

PRICE = {
    "i1": {"prisma": 1.79, "kcm": 1.69, "lidl": 1.49, "alepa": 1.99, "kmkt": 1.85},
    "i2": {"prisma": 2.89, "kcm": 2.79, "lidl": 2.49, "alepa": 3.19, "kmkt": 2.99},
    "i3": {"prisma": 2.15, "kcm": 1.99, "lidl": 1.79, "alepa": 2.39, "kmkt": 2.25},
    "i4": {"prisma": 7.95, "kcm": 6.99, "lidl": 7.49, "alepa": 8.89, "kmkt": 6.49},
    "i5": {"prisma": 4.99, "kcm": 4.49, "lidl": 3.99, "alepa": 5.49, "kmkt": 4.79},
    "i6": {"prisma": 3.29, "kcm": 2.99, "lidl": 2.79, "alepa": 3.59, "kmkt": 3.49},
    "i7": {"prisma": 1.99, "kcm": 1.89, "lidl": 1.29, "alepa": 2.29, "kmkt": 2.09},
}
PRICE_BY_NAME = {"oat milk": "i1", "eggs": "i2", "rye bread": "i3", "coffee beans": "i4", "toilet paper": "i5",
                 "frozen blueberries": "i6", "dish soap": "i7"}
for _p in PRICE.values():   # K-Supermarket Kamppi: K-Group prices, a touch over K-Market
    _p["ksm-kamppi"] = round(_p["kmkt"] * 1.02, 2)
STORE_FACTOR = {"prisma": 1.0, "kcm": 0.96, "lidl": 0.9, "alepa": 1.12, "kmkt": 1.03, "ksm-kamppi": 1.01}


def demo_price(item, store_id):
    pid = item.get("id")
    if pid not in PRICE:
        low = (item.get("name") or "").lower()
        pid = next((v for k, v in PRICE_BY_NAME.items() if low.startswith(k)), None)
    if pid in PRICE:
        return PRICE[pid][store_id]
    h = 0
    for ch in item.get("name") or "":
        h = (h * 31 + ord(ch)) % 997
    base = 1.5 + (h % 60) / 10
    return round(base * STORE_FACTOR[store_id] * 100) / 100


EVENTS = [
    {"title": "Late-night jazz trio at Kallio bar", "when": "Fri 20 Nov · 22:00", "where": "Kallio, 600 m away", "price": "Free",
     "tags": ["jazz", "music", "nightlife"], "why": "You told me you love small jazz venues.", "art": "jazz",
     "posts": [{"who": "@helsinkijazzclub", "text": "Last month's set was packed. Come early for a seat by the piano."}],
     "sources": [src("MyHelsinki — events", "https://www.myhelsinki.fi/"), src("Instagram post", "https://www.instagram.com/")]},
    {"title": "Beginner bouldering technique night", "when": "Tue 17 Nov · 18:00", "where": "Kalasatama, 1.5 km", "price": "€12 incl. shoes",
     "tags": ["bouldering", "sport", "climbing"], "why": "You started bouldering in October. Good next step.", "art": "climb",
     "posts": [{"who": "r/Helsinki", "text": "The coaches are super friendly, great place to meet people when you're new."}],
     "sources": [src("Gym schedule", "https://www.boulderkeskus.com/"), src("Reddit thread", "https://www.reddit.com/r/Helsinki/")]},
    {"title": "Christmas market at Senate Square", "when": "Daily until 22 Dec · 11–19", "where": "City centre, 2.3 km", "price": "Free entry",
     "tags": ["christmas", "market", "food"], "why": "Seasonal. Glögi and the carousel are back.", "art": "market",
     "posts": [{"who": "@visithelsinki", "text": "The carousel is back! Weekday mornings are quietest."}],
     "sources": [src("Tuomaan Markkinat", "https://tuomaanmarkkinat.fi/"), src("Visit Helsinki post", "https://www.instagram.com/")]},
    {"title": "Design market: Finnish makers", "when": "Sat 21 Nov · 10–17", "where": "Kaapelitehdas, 4 km", "price": "€5",
     "tags": ["design", "market", "gifts"], "why": "Good for unique Christmas gifts.", "art": "design",
     "posts": [{"who": "@kaapelitehdas", "text": "120+ independent makers this year."}],
     "sources": [src("Kaapelitehdas events", "https://www.kaapelitehdas.fi/")]},
]

TRAVEL = [
    {"title": "Rovaniemi: aurora weekend", "when": "27–29 Nov · 2 nights", "where": "HEL → RVN, 1 h 20 min flight", "price": "from €248 total",
     "kind": "trip", "art": "aurora", "why": "On your wish-list: Lapland this winter.", "tags": ["lapland", "aurora", "winter"],
     "details": [{"k": "Flight", "v": "Fri 17:05 → 18:25 · return Sun 19:40 · €139"},
                 {"k": "Stay", "v": "Glass-roof cabin, 4.7★ (812 reviews) · €54/night"},
                 {"k": "Extras", "v": "Aurora forecast KP 4–5 that weekend"}],
     "posts": [{"who": "@laplandlovers", "text": "Saw green ribbons from the cabin bed, book the north-facing ones."}],
     "sources": [src("Flight prices", "https://www.finnair.com/"), src("Cabin listing", "https://www.booking.com/"),
                 src("Aurora forecast (FMI)", "https://www.ilmatieteenlaitos.fi/revontulet-ja-avaruussaa")]},
    {"title": "Tallinn day trip by ferry", "when": "Any Sat · 10:30 → 19:30", "where": "West Harbour, 2 h crossing", "price": "from €38 return",
     "kind": "trip", "art": "ferry", "why": "Cheap and easy. The Old Town Christmas market opens 21 Nov.", "tags": ["tallinn", "ferry", "christmas"],
     "details": [{"k": "Ferry", "v": "Tallink Megastar · deck seat · €38"},
                 {"k": "Do", "v": "Christmas market, Telliskivi creative city, Balti Jaam market"}],
     "posts": [{"who": "r/Tallinn", "text": "Telliskivi on a Saturday is the best vibe. Get lunch at the food hall."}],
     "sources": [src("Ferry timetable", "https://www.tallink.com/"), src("Tallinn Christmas market", "https://www.visittallinn.ee/")]},
]

PRODUCTS = [
    {"id": "p1", "title": "Waterproof winter boots, lined", "price": 129, "store": "Partioaitta", "attrs": ["waterproof", "lined", "black", "grip sole"], "art": "boot1", "url": "https://www.partioaitta.fi/"},
    {"id": "p2", "title": "Leather Chelsea boots", "price": 159, "store": "Zalando", "attrs": ["leather", "black", "slim"], "art": "boot2", "url": "https://www.zalando.fi/"},
    {"id": "p3", "title": "Insulated hiking boots −30 °C", "price": 175, "store": "XXL", "attrs": ["waterproof", "lined", "grip sole", "chunky"], "art": "boot3", "url": "https://www.xxl.fi/"},
    {"id": "p4", "title": "Vegan winter sneakers", "price": 99, "store": "Stockmann", "attrs": ["vegan", "lined", "white", "slim"], "art": "boot4", "url": "https://www.stockmann.com/"},
    {"id": "p5", "title": "Rubber snow boots, felt liner", "price": 89, "store": "Prisma", "attrs": ["waterproof", "lined", "black", "chunky"], "art": "boot5", "url": "https://www.prisma.fi/"},
    {"id": "p6", "title": "Minimal waterproof boots, slim", "price": 139, "store": "Halens", "attrs": ["waterproof", "lined", "black", "slim", "grip sole"], "art": "boot6", "url": "https://www.halens.fi/"},
]

MEDS = {
    "throat": [
        {"name": "Throat lozenges, honey & lemon (24)", "price": 6.90, "pharmacy": "Yliopiston Apteekki", "eta": "45 min", "note": "For mild sore throat. Not for children under 6."},
        {"name": "Anti-inflammatory throat spray 15 ml", "price": 9.40, "pharmacy": "Apotek1 Kallio", "eta": "1 h 10 min", "note": "Ask a pharmacist if you take other medicines."},
    ],
    "head": [
        {"name": "Paracetamol 500 mg (30)", "price": 4.20, "pharmacy": "Yliopiston Apteekki", "eta": "45 min", "note": "Max 6 tablets / 24 h. Not with alcohol."},
        {"name": "Ibuprofen 400 mg (20)", "price": 5.10, "pharmacy": "Apotek1 Kallio", "eta": "1 h 10 min", "note": "Take with food. Avoid if you have stomach ulcers."},
    ],
    "sleep": [
        {"name": "Melatonin 1 mg (60)", "price": 8.50, "pharmacy": "Yliopiston Apteekki", "eta": "45 min", "note": "Take 30–60 min before bed. Short-term use."},
    ],
    "cold": [
        {"name": "Saline nasal spray 20 ml", "price": 7.30, "pharmacy": "Apotek1 Kallio", "eta": "1 h 10 min", "note": "Safe for daily use."},
        {"name": "Vitamin C + zinc effervescent (20)", "price": 6.10, "pharmacy": "Yliopiston Apteekki", "eta": "45 min", "note": "Supplement, not a treatment."},
    ],
}

MEALS = {
    "tired": [{"title": "Salmon, quinoa & spinach bowl", "why": "Omega-3s, iron and B vitamins for steady energy", "time": "20 min"},
              {"title": "Oat porridge with blueberries & walnuts", "why": "Slow-release carbs, magnesium for better sleep", "time": "8 min"}],
    "stressed": [{"title": "Warm lentil & sweet potato soup", "why": "Complex carbs and magnesium help calm the body", "time": "30 min"},
                 {"title": "Dark chocolate + banana snack", "why": "Small boost of tryptophan and potassium", "time": "1 min"}],
    "unwell": [{"title": "Chicken & ginger broth", "why": "Hydrating, gentle on the stomach", "time": "25 min"},
               {"title": "Honey-lemon hot drink", "why": "Soothes the throat, keeps you hydrated", "time": "3 min"}],
    "great": [{"title": "Rye bread with eggs & avocado", "why": "Protein and fibre to keep the good streak", "time": "10 min"}],
}
ACTIVITIES = {
    "tired": ["20-min walk in daylight before 14:00", "Screens off 45 min before bed", "No coffee after 15:00"],
    "stressed": ["10-min box-breathing (4-4-4-4)", "Short walk outside", "Call a friend, or chat with me"],
    "unwell": ["Rest, and drink water every hour", "Skip the gym today", "If fever > 38.5 °C for 3 days, book a doctor"],
    "great": ["Bouldering session tonight?", "Keep the 8k steps streak going"],
}
WELLBEING_SOURCES = [src("Finnish Food Authority — nutrition", "https://www.ruokavirasto.fi/"),
                     src("Sleep hygiene tips (Mehiläinen)", "https://www.mehilainen.fi/")]

# ------------------------------------------------------------------------------
# Mocked camera feeds. Real devices run detection on-device and only send the
# derived detections below; nothing image-like ever reaches the server.
# Each frame = what the on-device model saw at a moment in time.
# level: 0 = gone, 1 = full.
CAMERA_FRAMES = {
    "fridge": [
        {"id": "fridge-0800", "at": "08:00", "caption": "Morning: one oat milk carton, eggs box nearly empty, butter pack",
         "detections": [{"label": "oat_milk", "level": 0.6}, {"label": "eggs", "level": 0.1}, {"label": "butter", "level": 0.8},
                        {"label": "spinach", "level": 0.5}]},
        {"id": "fridge-1900", "at": "19:00", "caption": "Evening: oat milk gone, no eggs, butter opened",
         "detections": [{"label": "oat_milk", "level": 0.0}, {"label": "eggs", "level": 0.0}, {"label": "butter", "level": 0.2},
                        {"label": "spinach", "level": 0.4}]},
    ],
    "storage": [
        {"id": "storage-0800", "at": "08:00", "caption": "Shelf: coffee half bag, 4 toilet rolls, dish soap half",
         "detections": [{"label": "coffee_beans", "level": 0.5}, {"label": "toilet_paper", "level": 0.5}, {"label": "dish_soap", "level": 0.5},
                        {"label": "rye_bread", "level": 0.6}]},
        {"id": "storage-2000", "at": "20:00", "caption": "Shelf: coffee nearly out, 2 rolls left, bread finished",
         "detections": [{"label": "coffee_beans", "level": 0.1}, {"label": "toilet_paper", "level": 0.2}, {"label": "dish_soap", "level": 0.45},
                        {"label": "rye_bread", "level": 0.0}]},
    ],
    "basket": [
        {"id": "basket-0940", "at": "09:40", "caption": "Basket ~80% full",
         "detections": [{"label": "dark_tshirt", "n": 4}, {"label": "jeans", "n": 2}, {"label": "socks", "n": 6},
                        {"label": "underwear", "n": 6}, {"label": "white_tshirt", "n": 1}, {"label": "towel", "n": 3}, {"label": "gym_wear", "n": 3}]},
        {"id": "basket-2130", "at": "21:30", "caption": "Basket overflowing",
         "detections": [{"label": "dark_tshirt", "n": 5}, {"label": "jeans", "n": 2}, {"label": "socks", "n": 7},
                        {"label": "underwear", "n": 7}, {"label": "white_tshirt", "n": 1}, {"label": "towel", "n": 3}, {"label": "gym_wear", "n": 3}]},
    ],
    "door": [
        {"id": "door-0905", "at": "09:05", "detections": [{"person": "known", "name": "Neighbour", "dwell_s": 6, "knocked": False}]},
        {"id": "door-1131", "at": "11:31", "detections": [{"person": "courier", "dwell_s": 22, "knocked": True}]},
        {"id": "door-1402", "at": "14:02", "detections": [{"person": "unknown", "dwell_s": 220, "knocked": False, "peephole_looks": 2}]},
    ],
}

# Regular items the organiser keeps stocked: label from the on-device model -> shopping item.
REGULARS = [
    {"label": "oat_milk", "name": "Oat milk 1 L", "device": "fridge", "min_level": 0.3, "prio": 1},
    {"label": "eggs", "name": "Eggs (10)", "device": "fridge", "min_level": 0.25, "prio": 1},
    {"label": "butter", "name": "Butter 500 g", "device": "fridge", "min_level": 0.25, "prio": 2},
    {"label": "spinach", "name": "Baby spinach", "device": "fridge", "min_level": 0.15, "prio": 3},
    {"label": "coffee_beans", "name": "Coffee beans 500 g", "device": "storage", "min_level": 0.25, "prio": 2},
    {"label": "toilet_paper", "name": "Toilet paper (8)", "device": "storage", "min_level": 0.3, "prio": 2},
    {"label": "dish_soap", "name": "Dish soap", "device": "storage", "min_level": 0.3, "prio": 3},
    {"label": "rye_bread", "name": "Rye bread", "device": "storage", "min_level": 0.2, "prio": 2},
]

BASKET_LABELS = {
    "dark_tshirt": ("Dark T-shirts", "darks", "T-shirts"), "jeans": ("Jeans", "darks", "Jeans / trousers"),
    "socks": ("Socks (pairs)", "darks", "Socks"), "underwear": ("Underwear", "whites", "Underwear"),
    "white_tshirt": ("White T-shirt", "whites", "T-shirts"), "towel": ("Towels", "whites", "Towels"),
    "gym_wear": ("Gym wear", "sport", "Gym wear"), "colour_tshirt": ("Colour T-shirts", "colours", "T-shirts"),
    "knitwear": ("Knitwear", "delicates", None), "joggers": ("Joggers", "darks", "Jeans / trousers"),
    "unknown_item": ("Unrecognised item", "colours", None),
}


def clone(o):
    return copy.deepcopy(o)


def extract_keys(q):
    keys = []
    low = (q or "").lower()
    for k in ["waterproof", "lined", "black", "white", "slim", "chunky", "leather", "vegan", "grip sole", "cheap", "warm"]:
        if k.split(" ")[0] in low:
            keys.append(k)
    if re.search(r"warm|winter|cold", low) and "lined" not in keys:
        keys.append("lined")
    if re.search(r"snow|rain|wet|slush", low) and "waterproof" not in keys:
        keys.append("waterproof")
    m = re.search(r"under\s*[€$£]?\s*(\d+)", low) or re.search(r"<\s*[€$£]?\s*(\d+)", low)
    if m:
        keys.append("under €" + m.group(1))
    return keys
