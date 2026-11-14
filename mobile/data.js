/* =========================================================
   Figment — data + API layer
   ---------------------------------------------------------
   Every screen talks to window.FigmentAPI only. Right now it
   answers from the mock data below (with a short fake delay)
   so the prototype works offline.

   To go live, set USE_BACKEND = true and implement the
   endpoints listed next to each method on your server
   (e.g. a small proxy that calls Exa's /search and /contents
   APIs, keeps the Exa key server-side, and returns the same
   shapes). Each result keeps a `sources` array
   [{ title, url }] so the UI can always show where info came from.

   Camera / video analysis is designed to run ON DEVICE; only
   the derived item lists ever reach this layer.
   ========================================================= */
(function () {
    'use strict';

    var USE_BACKEND = false;
    var API_BASE = '/api';

    function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
    function src(title, url) { return { title: title, url: url }; }
    function post(path, body) {
        return fetch(API_BASE + path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body || {})
        }).then(function (r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        });
    }
    function clone(o) { return JSON.parse(JSON.stringify(o)); }

    /* ---------------- Seed state (persisted in localStorage by app.js) ---------------- */
    var seed = {
        user: { name: 'Alex', city: 'Helsinki', home: 'Kallio, Helsinki' },

        memoryConsent: null,           // null = not asked yet, true / false
        memories: [
            { id: 'm1', text: 'Loves live jazz, especially small venues', tag: 'hobby', date: '2 Nov' },
            { id: 'm2', text: 'Started bouldering in October', tag: 'hobby', date: '28 Oct' },
            { id: 'm3', text: 'Oat milk, not dairy', tag: 'food', date: '20 Oct' },
            { id: 'm4', text: 'Wants to visit Lapland this winter', tag: 'travel', date: '12 Oct' }
        ],

        devices: [
            { id: 'fridge',  name: 'Fridge camera',        kind: 'camera', on: true, last: '08:12', local: true },
            { id: 'storage', name: 'Storage cabinet camera', kind: 'camera', on: true, last: '08:12', local: true },
            { id: 'basket',  name: 'Laundry basket camera', kind: 'camera', on: true, last: '09:40', local: true },
            { id: 'door',    name: 'Front door camera',     kind: 'camera', on: true, last: 'live',  local: true },
            { id: 'watch',   name: 'Smart watch',           kind: 'health', on: true, last: '2 min ago', local: false }
        ],

        contacts: [
            { id: 'c1', name: 'Mum',   via: 'WhatsApp · +358 40 ••• 112', on: true },
            { id: 'c2', name: 'Sami (brother)', via: 'Telegram · @sami', on: true },
            { id: 'c3', name: 'Emergency services 112', via: 'Call + SMS with location', on: false, police: true }
        ],

        social: [
            { id: 's1', name: 'Instagram', handle: '@alex.k', on: true },
            { id: 's2', name: 'WhatsApp',  handle: '+358 40 ••• 908', on: true },
            { id: 's3', name: 'Telegram',  handle: 'not linked', on: false }
        ],

        checkin: { every: 24, grace: 2, last: null, streak: 11, nextHour: 21 },

        shopping: [
            { id: 'i1', name: 'Oat milk 1 L',      qty: 2, prio: 1, from: 'fridge',  note: 'Last carton almost empty' },
            { id: 'i2', name: 'Eggs (10)',         qty: 1, prio: 1, from: 'fridge',  note: 'None left' },
            { id: 'i3', name: 'Rye bread',         qty: 1, prio: 2, from: 'storage', note: 'Bought weekly' },
            { id: 'i4', name: 'Coffee beans 500 g',qty: 1, prio: 2, from: 'storage', note: '~3 days left' },
            { id: 'i5', name: 'Toilet paper (8)',  qty: 1, prio: 2, from: 'storage', note: '2 rolls left' },
            { id: 'i6', name: 'Frozen blueberries',qty: 1, prio: 3, from: 'you',     note: 'Added by you' },
            { id: 'i7', name: 'Dish soap',         qty: 1, prio: 3, from: 'storage', note: 'Half bottle' }
        ],
        groceryTrip: { day: 'today', start: 17.5, end: 18.25, booked: false },

        wardrobe: [
            { cat: 'Underwear',  clean: 2, total: 9,  perDay: 1 },
            { cat: 'Socks',      clean: 3, total: 10, perDay: 1 },
            { cat: 'T-shirts',   clean: 3, total: 8,  perDay: 1 },
            { cat: 'Jeans / trousers', clean: 2, total: 4, perDay: 0.3 },
            { cat: 'Towels',     clean: 1, total: 4,  perDay: 0.25 },
            { cat: 'Gym wear',   clean: 0, total: 3,  perDay: 0.4 }
        ],
        basket: [
            { name: 'Dark T-shirts', n: 4, group: 'darks' },
            { name: 'Jeans', n: 2, group: 'darks' },
            { name: 'Socks (pairs)', n: 6, group: 'darks' },
            { name: 'Underwear', n: 6, group: 'whites' },
            { name: 'White T-shirt', n: 1, group: 'whites' },
            { name: 'Towels', n: 3, group: 'whites' },
            { name: 'Gym wear', n: 3, group: 'sport' }
        ],
        laundryBookings: [],

        healthLog: { hr: [64, 66, 63, 65, 71, 76, 79], sleep: [7.4, 7.1, 6.8, 7.2, 5.9, 5.5, 5.2], steps: [8200, 7600, 9100, 6400, 4300, 3900, 3200] },
        mood: null,

        doorEvents: [
            { t: '14:02', title: 'Unknown person lingered 3 min 40 s', kind: 'bad', detail: 'Looked through the peephole twice, no knock' },
            { t: '11:31', title: 'Courier — parcel left', kind: 'ok', detail: 'Matched Posti uniform, 22 s' },
            { t: '09:05', title: 'Neighbour (known face)', kind: 'ok', detail: 'Walked past' },
            { t: 'Yest. 23:48', title: 'Motion, no person', kind: 'warn', detail: 'Hallway light timer' }
        ],

        today: {
            date: null, // filled in by app.js
            done: {}    // deco id -> true
        },

        chat: [
            { from: 'bot', text: 'Morning! ☕ Your coffee beans are running low btw, I popped them on the list.' },
            { from: 'bot', kind: 'find', text: 'Also, saw this and thought of you: a tiny jazz trio is doing a late set at a Kallio bar on Friday. No cover charge 👀',
              sources: [src('Helsinki events this week', 'https://www.myhelsinki.fi/'), src('Venue post on Instagram', 'https://www.instagram.com/')] }
        ],

        agentPosts: [
            { text: 'Found a bouldering gym doing beginner technique nights on Tuesdays, thought of you 🧗', when: '2 h ago',
              sources: [src('Gym schedule', 'https://www.boulderkeskus.com/')] },
            { text: 'Northern lights forecast looks strong for Lapland next weekend 🌌', when: 'yesterday',
              sources: [src('Aurora forecast', 'https://www.ilmatieteenlaitos.fi/revontulet-ja-avaruussaa'), src('Traveller post', 'https://www.reddit.com/r/Finland/')] }
        ]
    };

    /* ---------------- Mock: deals for the shopping list ---------------- */
    var STORES = [
        { id: 'prisma', name: 'Prisma Kalasatama', mall: 'REDI mall', dist: 1.4, url: 'https://www.s-kaupat.fi/' },
        { id: 'kcm',    name: 'K-Citymarket Itäkeskus', mall: 'Itis mall', dist: 6.2, url: 'https://www.k-ruoka.fi/' },
        { id: 'lidl',   name: 'Lidl Sörnäinen', mall: null, dist: 0.9, url: 'https://www.lidl.fi/' },
        { id: 'alepa',  name: 'Alepa Kallio', mall: null, dist: 0.3, url: 'https://www.s-kaupat.fi/' },
        { id: 'kmkt',   name: 'K-Market Redi', mall: 'REDI mall', dist: 1.4, url: 'https://www.k-ruoka.fi/' }
    ];
    // base price per item id per store (€)
    var PRICE = {
        i1: { prisma: 1.79, kcm: 1.69, lidl: 1.49, alepa: 1.99, kmkt: 1.85 },
        i2: { prisma: 2.89, kcm: 2.79, lidl: 2.49, alepa: 3.19, kmkt: 2.99 },
        i3: { prisma: 2.15, kcm: 1.99, lidl: 1.79, alepa: 2.39, kmkt: 2.25 },
        i4: { prisma: 7.95, kcm: 6.99, lidl: 7.49, alepa: 8.89, kmkt: 6.49 },
        i5: { prisma: 4.99, kcm: 4.49, lidl: 3.99, alepa: 5.49, kmkt: 4.79 },
        i6: { prisma: 3.29, kcm: 2.99, lidl: 2.79, alepa: 3.59, kmkt: 3.49 },
        i7: { prisma: 1.99, kcm: 1.89, lidl: 1.29, alepa: 2.29, kmkt: 2.09 }
    };
    function priceFor(item, storeId) {
        var p = PRICE[item.id];
        if (p) return p[storeId];
        // unknown, user-added item: deterministic pseudo price
        var h = 0; for (var i = 0; i < item.name.length; i++) h = (h * 31 + item.name.charCodeAt(i)) % 997;
        var base = 1.5 + (h % 60) / 10;
        var f = { prisma: 1.0, kcm: 0.96, lidl: 0.9, alepa: 1.12, kmkt: 1.03 }[storeId];
        return Math.round(base * f * 100) / 100;
    }
    function storeById(id) { return STORES.filter(function (s) { return s.id === id; })[0]; }

    function mockDeals(items, strategy, opts) {
        opts = opts || {};
        var lines, plan, note;
        function total(ls) { return ls.reduce(function (a, l) { return a + l.price * l.qty; }, 0); }
        function singleStoreTotals(storeIds) {
            return storeIds.map(function (sid) {
                return { sid: sid, lines: items.map(function (it) { return { item: it, qty: it.qty, store: sid, price: priceFor(it, sid) }; }) };
            }).map(function (o) { o.total = total(o.lines); return o; })
              .sort(function (a, b) { return a.total - b.total; });
        }

        if (strategy === 'multi') {
            lines = items.map(function (it) {
                var best = STORES.map(function (s) { return { s: s.id, p: priceFor(it, s.id) }; })
                    .sort(function (a, b) { return a.p - b.p; })[0];
                return { item: it, qty: it.qty, store: best.s, price: best.p };
            });
            note = 'Lowest price per item across 5 nearby stores. More stops, lowest total.';
        } else if (strategy === 'single') {
            var ranked = singleStoreTotals(STORES.map(function (s) { return s.id; }));
            lines = ranked[0].lines;
            note = 'Everything from one store. Runner-up: ' + storeById(ranked[1].sid).name + ' (€' + ranked[1].total.toFixed(2) + ').';
        } else if (strategy === 'mall') {
            // REDI mall has two stores, pick the cheapest of the two per item
            var mallStores = STORES.filter(function (s) { return s.mall === 'REDI mall'; });
            lines = items.map(function (it) {
                var best = mallStores.map(function (s) { return { s: s.id, p: priceFor(it, s.id) }; })
                    .sort(function (a, b) { return a.p - b.p; })[0];
                return { item: it, qty: it.qty, store: best.s, price: best.p };
            });
            note = 'One trip to REDI mall (Kalasatama metro). Mixes Prisma and K-Market inside.';
        } else { // nearest
            lines = items.map(function (it) { return { item: it, qty: it.qty, store: 'alepa', price: priceFor(it, 'alepa') }; });
            note = 'Closest store (300 m). Costs a bit more but the round trip is 6 minutes.';
        }

        var byStore = {};
        lines.forEach(function (l) { (byStore[l.store] = byStore[l.store] || []).push(l); });
        plan = Object.keys(byStore).map(function (sid) {
            var s = storeById(sid);
            return { store: s, lines: byStore[sid], total: total(byStore[sid]) };
        });
        var worst = singleStoreTotals(['alepa'])[0].total;
        var t = total(lines);
        return {
            strategy: strategy,
            total: t,
            saved: Math.max(0, worst - t),
            note: note,
            plan: plan,
            sources: plan.map(function (p) { return src(p.store.name + ' weekly prices', p.store.url); })
                .concat([src('Price comparison feed', 'https://www.ruokahinta.fi/')])
        };
    }

    /* ---------------- Mock: events, travel, products ---------------- */
    var EVENTS = [
        { title: 'Late-night jazz trio at Kallio bar', when: 'Fri 20 Nov · 22:00', where: 'Kallio, 600 m away', price: 'Free', tags: ['jazz', 'music', 'nightlife'],
          why: 'You told me you love small jazz venues.', art: 'jazz',
          posts: [{ who: '@helsinkijazzclub', text: 'Last month\'s set was packed. Come early for a seat by the piano.' }],
          sources: [src('MyHelsinki — events', 'https://www.myhelsinki.fi/'), src('Instagram post', 'https://www.instagram.com/')] },
        { title: 'Beginner bouldering technique night', when: 'Tue 17 Nov · 18:00', where: 'Kalasatama, 1.5 km', price: '€12 incl. shoes', tags: ['bouldering', 'sport', 'climbing'],
          why: 'You started bouldering in October. Good next step.', art: 'climb',
          posts: [{ who: 'r/Helsinki', text: 'The coaches are super friendly, great place to meet people when you\'re new.' }],
          sources: [src('Gym schedule', 'https://www.boulderkeskus.com/'), src('Reddit thread', 'https://www.reddit.com/r/Helsinki/')] },
        { title: 'Christmas market at Senate Square', when: 'Daily until 22 Dec · 11–19', where: 'City centre, 2.3 km', price: 'Free entry', tags: ['christmas', 'market', 'food'],
          why: 'Seasonal. Glögi and the carousel are back.', art: 'market',
          posts: [{ who: '@visithelsinki', text: 'The carousel is back! 🎠 Weekday mornings are quietest.' }],
          sources: [src('Tuomaan Markkinat', 'https://tuomaanmarkkinat.fi/'), src('Visit Helsinki post', 'https://www.instagram.com/')] },
        { title: 'Design market: Finnish makers', when: 'Sat 21 Nov · 10–17', where: 'Kaapelitehdas, 4 km', price: '€5', tags: ['design', 'market', 'gifts'],
          why: 'Good for unique Christmas gifts.', art: 'design',
          posts: [{ who: '@kaapelitehdas', text: '120+ independent makers this year.' }],
          sources: [src('Kaapelitehdas events', 'https://www.kaapelitehdas.fi/')] }
    ];
    var TRAVEL = [
        { title: 'Rovaniemi: aurora weekend', when: '27–29 Nov · 2 nights', where: 'HEL → RVN, 1 h 20 min flight', price: 'from €248 total', kind: 'trip', art: 'aurora',
          why: 'On your wish-list: Lapland this winter.',
          details: [
              { k: 'Flight', v: 'Fri 17:05 → 18:25 · return Sun 19:40 · €139' },
              { k: 'Stay', v: 'Glass-roof cabin, 4.7★ (812 reviews) · €54/night' },
              { k: 'Extras', v: 'Aurora forecast KP 4–5 that weekend' }
          ],
          posts: [{ who: '@laplandlovers', text: 'Saw green ribbons from the cabin bed 🤯 book the north-facing ones.' }],
          sources: [src('Flight prices', 'https://www.finnair.com/'), src('Cabin listing', 'https://www.booking.com/'), src('Aurora forecast (FMI)', 'https://www.ilmatieteenlaitos.fi/revontulet-ja-avaruussaa')] },
        { title: 'Tallinn day trip by ferry', when: 'Any Sat · 10:30 → 19:30', where: 'West Harbour, 2 h crossing', price: 'from €38 return', kind: 'trip', art: 'ferry',
          why: 'Cheap and easy. The Old Town Christmas market opens 21 Nov.',
          details: [
              { k: 'Ferry', v: 'Tallink Megastar · deck seat · €38' },
              { k: 'Do', v: 'Christmas market, Telliskivi creative city, Balti Jaam market' }
          ],
          posts: [{ who: 'r/Tallinn', text: 'Telliskivi on a Saturday is the best vibe. Get lunch at the food hall.' }],
          sources: [src('Ferry timetable', 'https://www.tallink.com/'), src('Tallinn Christmas market', 'https://www.visittallinn.ee/')] }
    ];
    var PRODUCTS = [
        { id: 'p1', title: 'Waterproof winter boots, lined', price: 129, store: 'Partioaitta', attrs: ['waterproof', 'lined', 'black', 'grip sole'], art: 'boot1', url: 'https://www.partioaitta.fi/' },
        { id: 'p2', title: 'Leather Chelsea boots', price: 159, store: 'Zalando', attrs: ['leather', 'black', 'slim'], art: 'boot2', url: 'https://www.zalando.fi/' },
        { id: 'p3', title: 'Insulated hiking boots −30 °C', price: 175, store: 'XXL', attrs: ['waterproof', 'lined', 'grip sole', 'chunky'], art: 'boot3', url: 'https://www.xxl.fi/' },
        { id: 'p4', title: 'Vegan winter sneakers', price: 99, store: 'Stockmann', attrs: ['vegan', 'lined', 'white', 'slim'], art: 'boot4', url: 'https://www.stockmann.com/' },
        { id: 'p5', title: 'Rubber snow boots, felt liner', price: 89, store: 'Prisma', attrs: ['waterproof', 'lined', 'black', 'chunky'], art: 'boot5', url: 'https://www.prisma.fi/' },
        { id: 'p6', title: 'Minimal waterproof boots, slim', price: 139, store: 'Halens', attrs: ['waterproof', 'lined', 'black', 'slim', 'grip sole'], art: 'boot6', url: 'https://www.halens.fi/' }
    ];

    function extractKeys(q) {
        var keys = [];
        var dict = ['waterproof', 'lined', 'black', 'white', 'slim', 'chunky', 'leather', 'vegan', 'grip sole', 'cheap', 'warm'];
        var low = q.toLowerCase();
        dict.forEach(function (k) { if (low.indexOf(k.split(' ')[0]) !== -1) keys.push(k); });
        if (/warm|winter|cold/.test(low) && keys.indexOf('lined') === -1) keys.push('lined');
        if (/snow|rain|wet|slush/.test(low) && keys.indexOf('waterproof') === -1) keys.push('waterproof');
        var m = low.match(/under\s*€?\s*(\d+)/) || low.match(/<\s*€?\s*(\d+)/);
        if (m) keys.push('under €' + m[1]);
        if (!keys.length) keys = ['waterproof', 'lined'];
        return keys;
    }
    function scoreProducts(keys, liked, disliked) {
        var maxPrice = null;
        keys.forEach(function (k) { var m = k.match(/under €(\d+)/); if (m) maxPrice = +m[1]; });
        var likedAttrs = {}, dislikedAttrs = {};
        PRODUCTS.forEach(function (p) {
            if (liked.indexOf(p.id) !== -1) p.attrs.forEach(function (a) { likedAttrs[a] = (likedAttrs[a] || 0) + 1; });
            if (disliked.indexOf(p.id) !== -1) p.attrs.forEach(function (a) { dislikedAttrs[a] = (dislikedAttrs[a] || 0) + 1; });
        });
        return PRODUCTS.map(function (p) {
            var s = 0;
            keys.forEach(function (k) { if (p.attrs.indexOf(k) !== -1) s += 2; });
            p.attrs.forEach(function (a) { s += (likedAttrs[a] || 0) * 0.8 - (dislikedAttrs[a] || 0) * 1.2; });
            if (maxPrice && p.price > maxPrice) s -= 4;
            if (disliked.indexOf(p.id) !== -1) s -= 10;
            var matched = p.attrs.filter(function (a) { return keys.indexOf(a) !== -1; });
            return Object.assign(clone(p), { score: s, matched: matched,
                sources: [src(p.store + ' product page', p.url), src('Review roundup', 'https://www.reddit.com/r/BuyItForLife/')] });
        }).sort(function (a, b) { return b.score - a.score; });
    }

    /* ---------------- Mock: health ---------------- */
    var MEDS = {
        throat: [
            { name: 'Throat lozenges, honey & lemon (24)', price: 6.90, pharmacy: 'Yliopiston Apteekki', eta: '45 min', note: 'For mild sore throat. Not for children under 6.' },
            { name: 'Anti-inflammatory throat spray 15 ml', price: 9.40, pharmacy: 'Apotek1 Kallio', eta: '1 h 10 min', note: 'Ask a pharmacist if you take other medicines.' }
        ],
        head: [
            { name: 'Paracetamol 500 mg (30)', price: 4.20, pharmacy: 'Yliopiston Apteekki', eta: '45 min', note: 'Max 6 tablets / 24 h. Not with alcohol.' },
            { name: 'Ibuprofen 400 mg (20)', price: 5.10, pharmacy: 'Apotek1 Kallio', eta: '1 h 10 min', note: 'Take with food. Avoid if you have stomach ulcers.' }
        ],
        sleep: [
            { name: 'Melatonin 1 mg (60)', price: 8.50, pharmacy: 'Yliopiston Apteekki', eta: '45 min', note: 'Take 30–60 min before bed. Short-term use.' }
        ],
        cold: [
            { name: 'Saline nasal spray 20 ml', price: 7.30, pharmacy: 'Apotek1 Kallio', eta: '1 h 10 min', note: 'Safe for daily use.' },
            { name: 'Vitamin C + zinc effervescent (20)', price: 6.10, pharmacy: 'Yliopiston Apteekki', eta: '45 min', note: 'Supplement, not a treatment.' }
        ]
    };
    var MEALS = {
        tired: [
            { title: 'Salmon, quinoa & spinach bowl', why: 'Omega-3s, iron and B vitamins for steady energy', time: '20 min' },
            { title: 'Oat porridge with blueberries & walnuts', why: 'Slow-release carbs, magnesium for better sleep', time: '8 min' }
        ],
        stressed: [
            { title: 'Warm lentil & sweet potato soup', why: 'Complex carbs and magnesium help calm the body', time: '30 min' },
            { title: 'Dark chocolate + banana snack', why: 'Small boost of tryptophan and potassium', time: '1 min' }
        ],
        unwell: [
            { title: 'Chicken & ginger broth', why: 'Hydrating, gentle on the stomach', time: '25 min' },
            { title: 'Honey-lemon hot drink', why: 'Soothes the throat, keeps you hydrated', time: '3 min' }
        ],
        great: [
            { title: 'Rye bread with eggs & avocado', why: 'Protein and fibre to keep the good streak', time: '10 min' }
        ]
    };
    var ACTIVITIES = {
        tired: ['20-min walk in daylight before 14:00', 'Screens off 45 min before bed', 'No coffee after 15:00'],
        stressed: ['10-min box-breathing (4-4-4-4)', 'Short walk along the Kallio shoreline', 'Call a friend, or chat with me 💬'],
        unwell: ['Rest, and drink water every hour', 'Skip the gym today', 'If fever > 38.5 °C for 3 days, book a doctor'],
        great: ['Bouldering session tonight?', 'Keep the 8k steps streak going']
    };

    /* ---------------- Mock: chat ---------------- */
    var DISTRESS = /\b(sad|lonely|alone|depress\w*|anxious|anxiety|hopeless|worthless|can'?t cope|cry(ing)?|panic|empty|hurt myself|self[- ]?harm|end it|give up)\b/i;
    var CRISIS = /\b(hurt myself|self[- ]?harm|end it|kill myself|suicid\w*|don'?t want to live)\b/i;

    function mockChat(text, ctx) {
        var t = text.trim();
        var low = t.toLowerCase();
        var res = { replies: [] };

        if (CRISIS.test(low)) {
            res.replies.push({ kind: 'care', crisis: true,
                text: 'Hey, I\'m really glad you told me. You matter a lot, and you don\'t have to go through this alone. Can I reach out to someone you trust right now? I\'ll only do it if you say yes.' });
            return res;
        }
        if (DISTRESS.test(low)) {
            res.replies.push({ text: 'Ah, that sounds really heavy. I\'m here, no rush. Want to tell me a bit more about what\'s going on?' });
            res.replies.push({ kind: 'care',
                text: 'If it\'d help, I can quietly let someone you trust know you could use some company. Only with your OK though.' });
            return res;
        }

        var pref = t.match(/\bi (?:really )?(?:love|like|enjoy|am into|'m into|prefer|hate|don'?t like)\s+(.+?)[.!?]*$/i);
        if (pref) {
            var thing = pref[1].replace(/\s+/g, ' ');
            res.memory = (/hate|don'?t like/i.test(t) ? 'Doesn\'t like ' : 'Likes ') + thing;
            res.replies.push({ text: 'Ooh, noted! ' + (ctx.memoryConsent ? 'I\'ll keep an eye out for ' + thing + ' stuff for you 👀' : 'Want me to remember that? Memory is off right now.') });
            return res;
        }
        if (/weekend|event|plan|bored|do tonight/.test(low)) {
            res.replies.push({ kind: 'find', text: 'Bored? Say no more 😄 There\'s a free jazz trio in Kallio on Friday, and the Christmas market at Senate Square is open daily.',
                sources: [src('MyHelsinki — events', 'https://www.myhelsinki.fi/'), src('Tuomaan Markkinat', 'https://tuomaanmarkkinat.fi/')], link: '#/explore' });
            return res;
        }
        if (/hungry|dinner|cook|recipe|eat/.test(low)) {
            res.replies.push({ text: 'You\'ve got eggs (well, after today\'s shop), rye bread and spinach. Shakshuka in 15 min? 🍳' });
            return res;
        }
        if (/tired|sleep|exhausted/.test(low)) {
            res.replies.push({ text: 'Your watch agrees, you\'ve been under 6 h of sleep for 3 nights 😴 Early night? I put some ideas in Health.', link: '#/health' });
            return res;
        }
        if (/^(hi|hey|hello|moi|morning|yo)\b/.test(low)) {
            res.replies.push({ text: 'Heyy 👋 How\'s your day going so far?' });
            return res;
        }
        if (/thank/.test(low)) {
            res.replies.push({ text: 'Anytime! That\'s what friends are for 🫶' });
            return res;
        }
        var generic = [
            'Haha fair. Tell me more?',
            'Okay, I\'m listening 👂 what happened next?',
            'Honestly same. Anything I can sort out for you today?',
            'Love that. Want me to dig up anything related?'
        ];
        res.replies.push({ text: generic[Math.floor(Math.random() * generic.length)] });
        return res;
    }

    /* ---------------- Public API ---------------- */
    window.FigmentAPI = {
        seed: function () { return clone(seed); },
        stores: STORES,

        /* POST /api/deals  { items, strategy } -> { total, saved, note, plan[], sources[] } */
        findDeals: function (items, strategy) {
            if (USE_BACKEND) return post('/deals', { items: items, strategy: strategy });
            return wait(1100).then(function () { return mockDeals(items, strategy); });
        },

        /* POST /api/explore  { query, kind: 'events'|'travel', interests[] } -> { results[] } */
        explore: function (query, kind, interests) {
            if (USE_BACKEND) return post('/explore', { query: query, kind: kind, interests: interests });
            return wait(1000).then(function () {
                var list = clone(kind === 'travel' ? TRAVEL : EVENTS);
                var q = (query || '').toLowerCase();
                interests = (interests || []).map(function (s) { return s.toLowerCase(); });
                list.forEach(function (e) {
                    e._s = 0;
                    (e.tags || []).forEach(function (t) { if (q.indexOf(t) !== -1) e._s += 3; if (interests.indexOf(t) !== -1) e._s += 2; });
                    if (q && e.title.toLowerCase().indexOf(q) !== -1) e._s += 3;
                });
                list.sort(function (a, b) { return b._s - a._s; });
                return { results: list, query: query };
            });
        },

        /* POST /api/products  { query, image?, keys[], liked[], disliked[], round } -> { keys[], results[], strategy } */
        findProducts: function (query, opts) {
            opts = opts || {};
            if (USE_BACKEND) return post('/products', Object.assign({ query: query }, opts));
            return wait(1100).then(function () {
                var keys = opts.keys && opts.keys.length ? opts.keys : extractKeys(query);
                if (opts.image && keys.indexOf('black') === -1) keys = keys.concat(['black']);
                var results = scoreProducts(keys, opts.liked || [], opts.disliked || []);
                var strat = (opts.round || 1) === 1
                    ? 'Searched: "' + keys.join(' + ') + '"' + (opts.image ? ' + visual match from your photo' : '')
                    : 'Round ' + opts.round + ': boosted what you liked, filtered what you didn\'t';
                return { keys: keys, results: results, strategy: strat };
            });
        },

        /* POST /api/medicine  { symptom } -> { results[] } */
        findMedicine: function (q) {
            if (USE_BACKEND) return post('/medicine', { symptom: q });
            return wait(900).then(function () {
                var low = q.toLowerCase(), list;
                if (/throat|cough/.test(low)) list = MEDS.throat;
                else if (/head|pain|ache|fever/.test(low)) list = MEDS.head;
                else if (/sleep|insomnia/.test(low)) list = MEDS.sleep;
                else list = MEDS.cold;
                return { results: list.map(function (m) { return Object.assign(clone(m), {
                    sources: [src(m.pharmacy + ' — product info', 'https://www.yliopistonapteekki.fi/'), src('Fimea medicine info', 'https://www.fimea.fi/')] }); }) };
            });
        },

        /* POST /api/wellbeing  { mood } -> { meals[], activities[], sources[] } */
        wellbeing: function (mood) {
            if (USE_BACKEND) return post('/wellbeing', { mood: mood });
            return wait(700).then(function () {
                return { meals: MEALS[mood] || MEALS.tired, activities: ACTIVITIES[mood] || ACTIVITIES.tired,
                    sources: [src('Finnish Food Authority — nutrition', 'https://www.ruokavirasto.fi/'), src('Sleep hygiene tips (Mehiläinen)', 'https://www.mehilainen.fi/')] };
            });
        },

        /* POST /api/chat  { text, memoryConsent, memories[] } -> { replies[], memory? } */
        chat: function (text, ctx) {
            if (USE_BACKEND) return post('/chat', Object.assign({ text: text }, ctx));
            return wait(900 + Math.random() * 600).then(function () { return mockChat(text, ctx); });
        }
    };
})();
