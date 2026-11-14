/* =========================================================
   Figment — app logic (routing, screens, interactions)
   ========================================================= */
(function () {
    'use strict';

    var API = window.FigmentAPI;
    var KEY = 'figment-state-v1';
    var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    /* ---------------- State ---------------- */
    function load() {
        try {
            var raw = localStorage.getItem(KEY);
            if (raw) return Object.assign(API.seed(), JSON.parse(raw));
        } catch (e) { /* ignore */ }
        return API.seed();
    }
    var S = load();
    function save() { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) { /* ignore */ } }

    var now = new Date();
    var todayKey = now.toISOString().slice(0, 10);
    if (S.today.date !== todayKey) { S.today = { date: todayKey, done: {} }; save(); }

    // in-memory UI state (not persisted)
    var UI = {
        dealStrategy: 'multi', deals: null, dealsLoading: false,
        tripEdit: false,
        laundrySel: null,
        exploreTab: 'events', exploreQuery: { events: 'this weekend in Helsinki', travel: 'Lapland this winter' },
        exploreResults: {}, exploreLoading: false, interests: null,
        product: { query: 'Warm waterproof winter boots, black, under €150', keys: null, results: null, liked: [], disliked: [], round: 1, image: null, strategy: '', loading: false },
        mood: null, wellbeing: null,
        meds: null, medsLoading: false, medsQuery: '',
        apptSel: null, apptBooked: null, ride: null,
        sosType: null, sosPolice: false, sosSent: null,
        doorReviewed: false
    };

    /* ---------------- Helpers ---------------- */
    function $(s, r) { return (r || document).querySelector(s); }
    function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
    function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
    function euro(n) { return '€' + n.toFixed(2); }
    function fmtH(h) { var hh = Math.floor(h), mm = Math.round((h - hh) * 60); return (hh < 10 ? '0' : '') + hh + ':' + (mm < 10 ? '0' : '') + mm; }
    function hhmm(d) { return fmtH(d.getHours() + d.getMinutes() / 60); }
    function uid() { return 'x' + Math.random().toString(36).slice(2, 8); }
    var DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    function dayShort(offset) { var d = new Date(now); d.setDate(d.getDate() + offset); return DAYS[d.getDay()].slice(0, 3) + ' ' + d.getDate(); }

    var I = {
        check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
        plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
        x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
        lock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 018 0v4"/></svg>',
        cam: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z"/><circle cx="12" cy="13" r="4"/></svg>',
        watch: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12" rx="3"/><path d="M9 6l1-4h4l1 4M9 18l1 4h4l1-4M10 12h1.5l1-2 1 4 .8-2H15"/></svg>',
        bag: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z"/><path d="M3 6h18M16 10a4 4 0 01-8 0"/></svg>',
        print: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9V2h12v7M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>',
        cal: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>',
        up: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M7 22V11M2 13v7a2 2 0 002 2h13.4a2 2 0 002-1.7l1.4-9A2 2 0 0018.8 9H14V4a3 3 0 00-3-3l-4 10"/></svg>',
        down: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M17 2v11M22 11V4a2 2 0 00-2-2H6.6a2 2 0 00-2 1.7l-1.4 9A2 2 0 005.2 15H10v5a3 3 0 003 3l4-10"/></svg>',
        fp: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M12 11c0 3.5-1 6.5-3 9M8 8.5A5 5 0 0117 11c0 1.5-.1 3-.4 4.4M6.3 14.5c.5-1.1.7-2.3.7-3.5a5 5 0 01.4-2M15.5 19.5c.3-.8.6-1.7.8-2.6M3.5 9a9 9 0 0116.9 0M12 15c-.3 2-1 3.8-2 5.5M3 12.5c.1-.5.2-1 .4-1.5"/></svg>',
        face: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8V5a2 2 0 012-2h3M16 3h3a2 2 0 012 2v3M21 16v3a2 2 0 01-2 2h-3M8 21H5a2 2 0 01-2-2v-3"/><path d="M9 9v1M15 9v1M12 9v4h-1M9 16c1.7 1.3 4.3 1.3 6 0"/></svg>',
        upload: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>',
        car: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 17h14M3 17v-4l2-5a2 2 0 012-1h10a2 2 0 012 1l2 5v4"/><circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/></svg>',
        send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4z"/></svg>',
        refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.5 9a9 9 0 0114.8-3.4L23 10M1 14l4.7 4.4A9 9 0 0020.5 15"/></svg>',
        search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>',
        pin: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13S3 17 3 10a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/></svg>'
    };
    var loaderSvg = '<svg class="loader" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/></svg>';

    function sourcesHtml(list, label) {
        if (!list || !list.length) return '';
        return '<div class="sources"><span class="via">' + (label || 'Sources') + '</span>' + list.map(function (s) {
            return '<a class="src" href="' + esc(s.url) + '" target="_blank" rel="noopener noreferrer" title="' + esc(s.url) + '"><span class="exa-mark">E</span><span>' + esc(s.title) + '</span></a>';
        }).join('') + '</div>';
    }
    function localBadge() { return '<span class="badge">' + I.lock + 'On-device</span>'; }
    function loadingHtml(text) { return '<div class="loading">' + loaderSvg + '<span>' + esc(text) + '</span></div>'; }

    /* ---------------- Toast ---------------- */
    var toastT;
    function toast(msg) {
        var t = $('#toast');
        t.textContent = msg;
        t.classList.add('show');
        clearTimeout(toastT);
        toastT = setTimeout(function () { t.classList.remove('show'); }, 2600);
    }

    /* ---------------- Sheet ---------------- */
    var sheetOnClose = null;
    function openSheet(html, onMount, onClose) {
        $('#sheet-body').innerHTML = html;
        $('#sheet').classList.add('open');
        $('#sheet-backdrop').classList.add('open');
        sheetOnClose = onClose || null;
        if (onMount) onMount($('#sheet-body'));
        var f = $('#sheet-body button, #sheet-body input');
        if (f) setTimeout(function () { f.focus({ preventScroll: true }); }, 350);
    }
    function closeSheet() {
        $('#sheet').classList.remove('open');
        $('#sheet-backdrop').classList.remove('open');
        var cb = sheetOnClose; sheetOnClose = null;
        if (cb) cb();
    }
    $('#sheet-backdrop').addEventListener('click', closeSheet);
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { if ($('#sheet').classList.contains('open')) closeSheet(); else if ($('#menu').classList.contains('open')) toggleMenu(false); }
    });

    /* Biometric confirmation (simulated Touch ID / Face ID) */
    function authenticate(reason) {
        return new Promise(function (resolve, reject) {
            var done = false;
            openSheet(
                '<h2 id="sheet-title">Confirm it\'s you</h2><p class="lede">' + esc(reason) + '</p>' +
                '<div class="auth-visual"><div class="auth-ring" id="auth-ring">' + I.fp + '</div><div class="small bold" id="auth-msg">Touch the sensor or look at your phone</div></div>' +
                '<div class="sheet-actions"><button class="pill brand" data-m="fp" type="button">' + I.fp + 'Fingerprint</button><button class="pill dark" data-m="face" type="button">' + I.face + 'Face ID</button></div>' +
                '<div class="sheet-actions" style="margin-top:8px"><button class="pill outline" data-m="cancel" type="button">Cancel</button></div>',
                function (root) {
                    $$('[data-m]', root).forEach(function (b) {
                        b.addEventListener('click', function () {
                            if (b.dataset.m === 'cancel') { closeSheet(); return; }
                            var ring = $('#auth-ring', root);
                            ring.innerHTML = b.dataset.m === 'face' ? I.face : I.fp;
                            ring.classList.add('scanning');
                            $('#auth-msg', root).textContent = 'Scanning…';
                            $$('[data-m]', root).forEach(function (x) { x.disabled = true; });
                            setTimeout(function () {
                                ring.classList.remove('scanning'); ring.classList.add('ok'); ring.innerHTML = I.check;
                                $('#auth-msg', root).textContent = 'Verified';
                                setTimeout(function () { done = true; closeSheet(); resolve(); }, 450);
                            }, 900);
                        });
                    });
                },
                function () { if (!done) reject(new Error('cancelled')); }
            );
        });
    }

    /* ---------------- Menu ---------------- */
    function toggleMenu(open) {
        var m = $('#menu'), b = $('#menu-btn');
        open = open == null ? !m.classList.contains('open') : open;
        m.classList.toggle('open', open);
        b.setAttribute('aria-expanded', String(open));
        b.textContent = open ? 'Close' : 'Menu';
    }
    $('#menu-btn').addEventListener('click', function () { toggleMenu(); });
    $$('#menu a').forEach(function (a) { a.addEventListener('click', function () { toggleMenu(false); }); });

    /* =========================================================
       ROUTER
       ========================================================= */
    var TOP = ['home', 'today', 'chat', 'me'];
    var current = null;

    function route() {
        var name = (location.hash || '#/home').replace(/^#\/?/, '') || 'home';
        var screen = $$('.screen').filter(function (s) { return s.dataset.route.split(' ').indexOf(name) !== -1; })[0];
        if (!screen) { location.hash = '#/home'; return; }
        var prev = current;
        current = name;

        document.body.className = document.body.className.replace(/\broute-\S+/g, '').trim();
        document.body.classList.add('route-' + name);
        if (window.scrollY > 10) document.body.classList.add('scrolled');

        var wasActive = screen.classList.contains('active');
        $$('.screen').forEach(function (s) { s.classList.toggle('active', s === screen); });

        // nav highlight
        $$('.nav-icon-btn').forEach(function (b) {
            var on = b.dataset.nav === name;
            if (on && !b.classList.contains('is-active')) {
                b.classList.add('just-activated');
                setTimeout(function () { b.classList.remove('just-activated'); }, 650);
            }
            b.classList.toggle('is-active', on);
            if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
        });

        // back button for feature screens
        var isTop = TOP.indexOf(name) !== -1;
        $('#back-btn').hidden = isTop;
        $('#brand').hidden = !isTop;

        // home <-> today share one screen and animate between states
        if (name === 'today') setDecorating(true, wasActive && (prev === 'home'));
        else if (name === 'home') setDecorating(false, wasActive);
        else { document.body.classList.remove('decorating', 'decor-open'); }

        window.scrollTo({ top: 0, behavior: (wasActive && !reduce) ? 'smooth' : 'auto' });

        (RENDER[name] || function () {})();
    }
    var stack = [location.hash || '#/home'];
    window.addEventListener('hashchange', function () {
        var h = location.hash || '#/home';
        if (stack.length > 1 && stack[stack.length - 2] === h) stack.pop(); else stack.push(h);
        route();
    });
    $('#back-btn').addEventListener('click', function () {
        if (stack.length > 1) history.back(); else location.hash = '#/home';
    });
    window.addEventListener('scroll', function () { document.body.classList.toggle('scrolled', window.scrollY > 10); }, { passive: true });

    var decoTimer;
    function setDecorating(on, animate) {
        clearTimeout(decoTimer);
        var b = document.body;
        if (on) {
            b.classList.add('decorating');
            if (animate) decoTimer = setTimeout(function () { b.classList.add('decor-open'); }, reduce ? 50 : 1600);
            else b.classList.add('decor-open');
        } else {
            b.classList.remove('decor-open', 'decorating');
        }
    }
    $('#decorate-btn').addEventListener('click', function () { location.hash = '#/today'; });

    var RENDER = {
        home: renderHome, today: renderToday,
        shopping: renderShopping, laundry: renderLaundry, explore: renderExplore,
        chat: renderChat, health: renderHealth, safety: renderSafety, me: renderMe
    };

    /* =========================================================
       HOME
       ========================================================= */
    function setAlert(id, val) {
        var el = $('#alert-' + id);
        if (!el) return;
        el.hidden = !val; el.textContent = val || '';
    }
    function renderHome() {
        renderToday(); // keeps the tree + cards in sync
        setAlert('shopping', S.shopping.filter(function (i) { return i.prio === 1 && !i.bought; }).length || '');
        setAlert('laundry', minRunway() <= 2 ? '!' : '');
        setAlert('chat', S.chatSeen ? '' : '1');
        setAlert('health', '!');
        setAlert('safety', UI.doorReviewed ? '' : '1');
    }

    /* =========================================================
       TODAY — the v5 blank cards now carry the day's plan;
       finishing a task hangs its decoration on the tree.
       ========================================================= */
    var TASKS = [
        { deco: 'deco-star', tint: 'green', rot: [-1, 0.8], delay: 0, cls: '',
          kicker: 'Safety', title: 'Daily check-in', sub: function () { return 'due by ' + S.checkin.nextHour + ':00'; }, label: 'Check in', doneLabel: 'Safe', href: '#/safety', auth: 'Confirm your daily check-in so your people know you\'re okay.' },
        { deco: 'deco-red-ball', tint: 'peach', rot: [1.2, -0.6], delay: .5, cls: 'mt-8',
          kicker: 'Organiser', title: 'Grocery run', sub: function () { return fmtH(S.groceryTrip.start) + ' · REDI mall'; }, label: 'Done', doneLabel: 'Shopped', href: '#/shopping' },
        { deco: 'deco-garland', tint: 'lavender', rot: [-0.8, 1], delay: .2, cls: '-mt-4',
          kicker: 'Organiser', title: 'Book laundry slot', sub: function () { return 'clean clothes: ' + minRunway() + ' days left'; }, label: 'Done', doneLabel: 'Booked', href: '#/laundry' },
        { deco: 'deco-bell', tint: 'green', rot: [0.8, -1.2], delay: .8, cls: 'mt-4',
          kicker: 'Companion', title: 'Catch up with Ginger', sub: function () { return 'how was your day?'; }, label: 'Chatted', doneLabel: 'Chatted', href: '#/chat' },
        { deco: 'deco-cane', tint: 'peach', rot: [-1.2, 0.6], delay: .3, cls: '',
          kicker: 'Health', title: '20-min daylight walk', sub: function () { return 'sleep\'s been short'; }, label: 'Done', doneLabel: 'Walked', href: '#/health' },
        { deco: 'deco-orange-ball', tint: 'lavender', rot: [1, -1], delay: 1, cls: 'mt-12',
          kicker: 'Treat yourself', title: 'Jazz trio, Fri 22:00', sub: function () { return 'free · 600 m away'; }, label: 'Save', doneLabel: 'Saved', href: '#/explore' }
    ];

    function renderToday() {
        var d = now;
        $('#today-date').textContent = DAYS[d.getDay()] + ', ' + d.getDate() + ' ' + MONTHS[d.getMonth()];
        var n = TASKS.filter(function (t) { return S.today.done[t.deco]; }).length;
        $('#today-progress').innerHTML = n + ' / ' + TASKS.length + ' <small>decorations hung</small>';
        $('#tree-done').hidden = n < TASKS.length;

        var wrap = $('#today-cards');
        wrap.innerHTML = TASKS.map(function (t, i) {
            var done = !!S.today.done[t.deco];
            return '<div class="tool-card plain-card tint-' + t.tint + ' ' + t.cls + '" style="--rot-start:' + t.rot[0] + 'deg;--rot-end:' + t.rot[1] + 'deg;animation-delay:' + t.delay + 's;--i:' + i + ';">' +
                '<a class="task-body" href="' + t.href + '"><span class="task-kicker">' + esc(t.kicker) + '</span><span class="task-title">' + esc(t.title) + '</span><span class="task-sub">' + esc(t.sub()) + '</span></a>' +
                '<button class="deco-btn' + (done ? ' done' : '') + '" type="button" data-i="' + i + '"' + (done ? ' disabled' : '') + ' aria-label="' + esc(t.title) + ': mark done and hang a decoration">' +
                I.plus.replace('<svg', '<svg class="icon-plus"') + I.check.replace('<svg', '<svg class="icon-check"') +
                '<span class="deco-btn-label">' + esc(done ? t.doneLabel : t.label) + '</span></button></div>';
        }).join('');

        TASKS.forEach(function (t) {
            var el = document.getElementById(t.deco);
            if (S.today.done[t.deco] && !el.classList.contains('hung')) el.classList.add('hung', 'instant');
            if (!S.today.done[t.deco]) el.classList.remove('hung', 'instant');
        });

        $$('.deco-btn', wrap).forEach(function (b) {
            b.addEventListener('click', function () {
                var t = TASKS[+b.dataset.i];
                if (S.today.done[t.deco]) return;
                var p = t.auth ? authenticate(t.auth).then(function () { doCheckin(); }) : Promise.resolve();
                p.then(function () { completeTask(t, b); }).catch(function () {});
            });
        });
    }

    function completeTask(t, btn) {
        S.today.done[t.deco] = true; save();
        btn.classList.add('done'); btn.disabled = true;
        $('.deco-btn-label', btn).textContent = t.doneLabel;
        var el = document.getElementById(t.deco);
        el.classList.remove('instant');
        var needsScroll = window.scrollY > 24;
        if (needsScroll) window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' });
        setTimeout(function () { el.classList.add('hung'); }, needsScroll && !reduce ? 550 : 0);
        var n = TASKS.filter(function (x) { return S.today.done[x.deco]; }).length;
        $('#today-progress').innerHTML = n + ' / ' + TASKS.length + ' <small>decorations hung</small>';
        $('#tree-done').hidden = n < TASKS.length;
        if (n === TASKS.length) setTimeout(function () { toast('Your tree is complete! 🎄'); }, 900);
    }
    function markTaskByDeco(deco) { S.today.done[deco] = true; save(); }

    /* =========================================================
       SHOPPING
       ========================================================= */
    var FROM = { fridge: 'Fridge cam', storage: 'Cabinet cam', you: 'Added by you', health: 'From Health' };
    var PRIO = { 1: 'Urgent', 2: 'This week', 3: 'Nice to have' };
    var PRIO_SHORT = { 1: 'Now', 2: 'Week', 3: 'Later' };

    function renderShopping() {
        renderScan(); renderShopList(); renderDealPanel(); renderDeals(); renderTrip();
    }

    function renderScan(scanning) {
        var cams = S.devices.filter(function (d) { return d.id === 'fridge' || d.id === 'storage'; });
        var fromCam = S.shopping.filter(function (i) { return i.from === 'fridge' || i.from === 'storage'; });
        $('#scan-panel').innerHTML =
            '<div class="panel-head"><div><div class="panel-title">Camera scan</div><div class="panel-sub">' + fromCam.length + ' items running low</div></div>' + localBadge() + '</div>' +
            '<ul class="list">' + cams.map(function (c) {
                var n = S.shopping.filter(function (i) { return i.from === c.id; }).length;
                return '<li><span class="icon-btn">' + I.cam + '</span><div class="grow"><div class="item-title">' + esc(c.name) + '</div><div class="item-sub">Last scan ' + esc(c.last) + ' · ' + n + ' low</div></div>' +
                    (c.on ? '<span class="badge green">Live</span>' : '<span class="badge">Off</span>') + '</li>';
            }).join('') + '</ul>' +
            '<div class="pill-row" style="margin-top:14px">' +
            (scanning ? '<span class="loading" style="padding:0">' + loaderSvg + 'Scanning shelves on-device…</span>'
                      : '<button class="pill" id="rescan" type="button">' + I.refresh + 'Rescan now</button>') + '</div>';
        var r = $('#rescan');
        if (r) r.addEventListener('click', function () {
            renderScan(true);
            setTimeout(function () {
                var t = hhmm(new Date());
                cams.forEach(function (c) { var d = S.devices.filter(function (x) { return x.id === c.id; })[0]; d.last = t; });
                var added = false;
                if (!S.shopping.some(function (i) { return i.name === 'Butter 500 g'; })) {
                    S.shopping.push({ id: uid(), name: 'Butter 500 g', qty: 1, prio: 2, from: 'fridge', note: 'Spotted: last pack opened' });
                    added = true;
                }
                save(); UI.deals = null;
                renderShopping();
                toast(added ? 'Scan done: 1 new item (butter)' : 'Scan done: nothing new');
            }, 1500);
        });
    }

    function renderShopList() {
        var open = S.shopping.filter(function (i) { return !i.bought; }).length;
        $('#list-count').textContent = open + ' to buy';
        var html = '';
        [1, 2, 3].forEach(function (p) {
            var items = S.shopping.filter(function (i) { return i.prio === p; });
            if (!items.length) return;
            html += '<div class="label-caps" style="margin:' + (html ? '18px' : '0') + ' 0 8px">' + PRIO[p] + '</div><ul class="list">' +
                items.map(function (i) {
                    return '<li class="' + (i.bought ? 'item-done' : '') + '" data-id="' + i.id + '">' +
                        '<button class="check' + (i.bought ? ' on' : '') + '" data-act="buy" type="button" aria-label="Mark ' + esc(i.name) + ' as bought">' + I.check + '</button>' +
                        '<div class="grow"><div class="item-title">' + (i.qty > 1 ? i.qty + ' × ' : '') + esc(i.name) + '</div><div class="item-sub">' + esc(FROM[i.from] || i.from) + (i.note && i.note !== FROM[i.from] ? ' · ' + esc(i.note) : '') + '</div></div>' +
                        '<button class="prio prio-' + i.prio + '" data-act="prio" type="button" title="Priority: ' + PRIO[i.prio] + ' (tap to change)">' + PRIO_SHORT[i.prio] + '</button>' +
                        '<button class="icon-btn" data-act="del" type="button" aria-label="Remove ' + esc(i.name) + '" style="width:28px;height:28px">' + I.x + '</button></li>';
                }).join('') + '</ul>';
        });
        html += '<hr class="divider"><form class="search-row" id="add-item" style="flex-wrap:wrap"><input class="field" name="n" placeholder="Add an item…" aria-label="New item" style="flex-basis:100%"><select class="field" name="p" aria-label="Priority"><option value="1">Urgent</option><option value="2" selected>This week</option><option value="3">Nice to have</option></select><button class="pill brand" type="submit" aria-label="Add">' + I.plus + '</button></form>';
        $('#shop-list').innerHTML = html;

        $$('#shop-list [data-act]').forEach(function (b) {
            b.addEventListener('click', function () {
                var id = b.closest('li').dataset.id;
                var it = S.shopping.filter(function (x) { return x.id === id; })[0];
                if (b.dataset.act === 'buy') it.bought = !it.bought;
                if (b.dataset.act === 'prio') it.prio = it.prio % 3 + 1;
                if (b.dataset.act === 'del') S.shopping = S.shopping.filter(function (x) { return x.id !== id; });
                save(); UI.deals = null; renderShopList(); renderDeals();
            });
        });
        $('#add-item').addEventListener('submit', function (e) {
            e.preventDefault();
            var n = this.n.value.trim(); if (!n) return;
            S.shopping.push({ id: uid(), name: n, qty: 1, prio: +this.p.value, from: 'you', note: 'Added by you' });
            save(); UI.deals = null; renderShopList(); renderDeals();
        });
    }

    var STRATS = [
        { id: 'multi', t: 'Cheapest overall', d: 'Best price per item, any store' },
        { id: 'single', t: 'One store', d: 'Cheapest single shop' },
        { id: 'mall', t: 'One mall', d: 'Everything at REDI' },
        { id: 'nearest', t: 'Closest', d: 'Least walking' }
    ];
    function renderDealPanel() {
        $('#deal-panel').innerHTML =
            '<div class="panel-title" style="margin-bottom:4px">How should I shop?</div><div class="panel-sub" style="margin-bottom:12px">' + esc(STRATS.filter(function (s) { return s.id === UI.dealStrategy; })[0].d) + '</div>' +
            '<div class="chips">' + STRATS.map(function (s) { return '<button class="chip' + (s.id === UI.dealStrategy ? ' on' : '') + '" data-s="' + s.id + '" type="button">' + s.t + '</button>'; }).join('') + '</div>' +
            '<button class="pill block" id="find-deals" type="button" style="margin-top:14px">' + I.search + 'Search live prices</button>';
        $$('#deal-panel [data-s]').forEach(function (c) { c.addEventListener('click', function () { UI.dealStrategy = c.dataset.s; UI.deals = null; renderDealPanel(); renderDeals(); }); });
        $('#find-deals').addEventListener('click', runDeals);
    }
    function runDeals() {
        var items = S.shopping.filter(function (i) { return !i.bought; });
        if (!items.length) { toast('Your list is empty 🎉'); return; }
        UI.dealsLoading = true; renderDeals();
        API.findDeals(items, UI.dealStrategy).then(function (r) { UI.deals = r; }).catch(function () { toast('Couldn\'t reach price search'); })
            .then(function () { UI.dealsLoading = false; renderDeals(); });
    }
    function renderDeals() {
        var el = $('#deal-results');
        if (UI.dealsLoading) { el.innerHTML = '<div class="panel light">' + loadingHtml('Searching 5 nearby stores with Exa…') + '<div class="skeleton" style="background-color:rgba(0,0,0,.05)"></div></div>'; return; }
        var r = UI.deals;
        if (!r) { el.innerHTML = ''; return; }
        el.innerHTML = '<div class="panel light">' +
            '<div class="row between"><div><div class="label-caps">Estimated total</div><div style="font-size:2rem;font-weight:800;letter-spacing:-.03em;line-height:1.1">' + euro(r.total) + '</div></div>' +
            (r.saved > 0.05 ? '<span class="badge green">Save ' + euro(r.saved) + '</span>' : '') + '</div>' +
            '<p class="small" style="margin-top:6px">' + esc(r.note) + '</p>' +
            r.plan.map(function (p) {
                return '<hr class="divider"><div class="row between"><div><div class="item-title">' + esc(p.store.name) + '</div><div class="item-sub">' + p.store.dist + ' km' + (p.store.mall ? ' · ' + esc(p.store.mall) : '') + '</div></div><div class="bold">' + euro(p.total) + '</div></div>' +
                    '<ul class="list" style="margin-top:8px">' + p.lines.map(function (l) {
                        return '<li style="padding:6px 0"><div class="grow small">' + (l.qty > 1 ? l.qty + ' × ' : '') + esc(l.item.name) + '</div><div class="small bold">' + euro(l.price * l.qty) + '</div></li>';
                    }).join('') + '</ul>';
            }).join('') +
            sourcesHtml(r.sources, 'Prices from') +
            '<div class="pill-row" style="margin-top:16px"><button class="pill brand" id="order-online" type="button" style="flex:1">' + I.bag + 'Order online</button><button class="pill dark" id="print-list" type="button" style="flex:1">' + I.print + 'Print list</button></div>' +
            '</div>';
        $('#order-online').addEventListener('click', orderOnline);
        $('#print-list').addEventListener('click', printList);
    }
    function orderOnline() {
        var r = UI.deals;
        var fee = r.plan.length * 3.9;
        openSheet('<h2 id="sheet-title">Order online</h2><p class="lede">I\'ll place ' + (r.plan.length > 1 ? r.plan.length + ' orders, one per store,' : 'one order') + ' and deliver to ' + esc(S.user.home) + '.</p>' +
            '<div class="panel light" style="margin-top:14px"><ul class="list">' + r.plan.map(function (p) {
                return '<li><div class="grow"><div class="item-title">' + esc(p.store.name) + '</div><div class="item-sub">' + p.lines.length + ' items · delivery tomorrow 10–12</div></div><div class="bold">' + euro(p.total) + '</div></li>';
            }).join('') + '<li><div class="grow item-sub">Delivery fees</div><div class="small bold">' + euro(fee) + '</div></li>' +
            '<li><div class="grow item-title">Total</div><div class="bold">' + euro(r.total + fee) + '</div></li></ul></div>' +
            '<p class="tiny muted">Payment happens in each store\'s own checkout. Figment never stores your card.</p>' +
            '<div class="sheet-actions"><button class="pill outline" data-x type="button">Cancel</button><button class="pill brand" data-ok type="button">Place order</button></div>',
            function (root) {
                $('[data-x]', root).addEventListener('click', closeSheet);
                $('[data-ok]', root).addEventListener('click', function () {
                    closeSheet();
                    S.shopping.forEach(function (i) { if (!i.bought) i.bought = 'ordered'; });
                    markTaskByDeco('deco-red-ball');
                    save(); UI.deals = null; renderShopping();
                    toast('Ordered! Delivery tomorrow 10–12 (demo)');
                });
            });
    }
    function printList() {
        var r = UI.deals;
        var rows = [];
        r.plan.forEach(function (p) { p.lines.forEach(function (l) { rows.push('<tr><td>☐</td><td>' + (l.qty > 1 ? l.qty + ' × ' : '') + esc(l.item.name) + '</td><td>' + esc(p.store.name) + '</td><td>' + euro(l.price * l.qty) + '</td></tr>'); }); });
        $('#print-area').innerHTML = '<h1>Shopping list</h1><div>' + esc(DAYS[now.getDay()] + ' ' + now.getDate() + ' ' + MONTHS[now.getMonth()]) + ' · trip at ' + fmtH(S.groceryTrip.start) + ' · est. ' + euro(r.total) + '</div>' +
            '<table><thead><tr><th></th><th>Item</th><th>Store</th><th>Price</th></tr></thead><tbody>' + rows.join('') + '</tbody></table>' +
            '<p style="margin-top:12pt;font-size:9pt">Prices via Exa: ' + r.sources.map(function (s) { return esc(s.url); }).join(', ') + '</p>';
        window.print();
    }

    /* grocery trip calendar */
    var CAL = {
        today: [{ s: 12.0, e: 13.0, t: 'Lunch' }, { s: 14, e: 16, t: 'Study group' }, { s: 16.5, e: 17.25, t: 'Call with Sami' }, { s: 18.5, e: 20, t: 'Bouldering' }],
        tomorrow: [{ s: 12.5, e: 13.5, t: 'Lunch with Emma' }, { s: 16, e: 18, t: 'Lecture' }]
    };
    var TRIP_OPTS = [
        { day: 'today', start: 17.5, label: 'Today 17:30' },
        { day: 'today', start: 20.25, label: 'Today 20:15' },
        { day: 'tomorrow', start: 14, label: 'Tomorrow 14:00' },
        { day: 'tomorrow', start: 18.5, label: 'Tomorrow 18:30' }
    ];
    function conflicts(day, s, e) { return (CAL[day] || []).filter(function (ev) { return s < ev.e && e > ev.s; }); }
    function renderTrip() {
        var g = S.groceryTrip;
        var H0 = 12, H1 = 21, PX = 30;
        var hours = '', lane = '';
        for (var h = H0; h < H1; h++) hours += '<div class="cal-hour" style="height:' + PX + 'px">' + (h < 10 ? '0' : '') + h + ':00</div>';
        CAL[g.day].forEach(function (ev) {
            lane += '<div class="cal-ev busy" style="top:' + (ev.s - H0) * PX + 'px;height:' + ((ev.e - ev.s) * PX - 2) + 'px">' + esc(ev.t) + '</div>';
        });
        lane += '<div class="cal-ev sugg" style="top:' + (g.start - H0) * PX + 'px;height:' + ((g.end - g.start) * PX - 2) + 'px">' + (g.booked ? '✓ ' : '') + 'Grocery run · ' + fmtH(g.start) + '–' + fmtH(g.end) + '</div>';
        var c = conflicts(g.day, g.start, g.end);
        $('#trip-panel').innerHTML =
            '<div class="panel-head"><div><div class="panel-title">' + (g.day === 'today' ? 'Today' : 'Tomorrow') + ', ' + fmtH(g.start) + '</div><div class="panel-sub">' + (g.booked ? 'In your calendar' : 'Suggested free slot · 45 min incl. walking') + '</div></div>' +
            (g.booked ? '<span class="badge green">Booked</span>' : '<span class="badge orange">Suggested</span>') + '</div>' +
            '<div class="cal-day"><div>' + hours + '</div><div class="cal-lane" style="height:' + (H1 - H0) * PX + 'px"><div class="cal-lines" style="background-size:100% ' + PX + 'px"></div>' + lane + '</div></div>' +
            (c.length ? '<p class="small bold" style="color:var(--c-brand);margin-top:8px">Clashes with ' + esc(c.map(function (x) { return x.t; }).join(', ')) + '</p>' : '') +
            (UI.tripEdit ?
                '<hr class="divider"><div class="label-caps" style="margin-bottom:8px">Pick another time</div><div class="chips">' + TRIP_OPTS.map(function (o, i) {
                    return '<button class="chip' + (o.day === g.day && o.start === g.start ? ' on' : '') + '" data-o="' + i + '" type="button">' + o.label + '</button>';
                }).join('') + '</div>' +
                '<div class="search-row" style="margin-top:10px"><select class="field" id="trip-day" aria-label="Day"><option value="today"' + (g.day === 'today' ? ' selected' : '') + '>Today</option><option value="tomorrow"' + (g.day === 'tomorrow' ? ' selected' : '') + '>Tomorrow</option></select><input class="field" id="trip-time" type="time" value="' + fmtH(g.start) + '" min="12:00" max="20:15" step="900" aria-label="Start time"></div>'
                : '') +
            '<div class="pill-row" style="margin-top:14px">' +
            '<button class="pill outline" id="trip-edit" type="button" style="flex:1">' + (UI.tripEdit ? 'Done editing' : 'Edit time') + '</button>' +
            '<button class="pill brand" id="trip-book" type="button" style="flex:1"' + (g.booked ? ' disabled' : '') + '>' + I.cal + (g.booked ? 'Added' : 'Add to calendar') + '</button></div>';

        $('#trip-edit').addEventListener('click', function () { UI.tripEdit = !UI.tripEdit; renderTrip(); });
        $('#trip-book').addEventListener('click', function () { S.groceryTrip.booked = true; save(); renderTrip(); toast('Grocery run added to your calendar'); });
        $$('#trip-panel [data-o]').forEach(function (b) {
            b.addEventListener('click', function () { var o = TRIP_OPTS[+b.dataset.o]; setTrip(o.day, o.start); });
        });
        var td = $('#trip-day'), tt = $('#trip-time');
        function custom() { var p = tt.value.split(':'); if (p.length < 2) return; setTrip(td.value, Math.min(20.25, Math.max(12, +p[0] + (+p[1]) / 60))); }
        if (td) { td.addEventListener('change', custom); tt.addEventListener('change', custom); }
    }
    function setTrip(day, start) { S.groceryTrip = { day: day, start: start, end: start + 0.75, booked: false }; save(); renderTrip(); }

    /* =========================================================
       LAUNDRY
       ========================================================= */
    function runway(w) { return w.perDay ? Math.floor(w.clean / w.perDay) : 99; }
    function minRunway() {
        var essentials = S.wardrobe.filter(function (w) { return w.perDay >= 1; });
        return Math.min.apply(null, essentials.map(runway));
    }
    var LOADS = {
        darks: { t: 'Darks', temp: '40 °C', prog: 'Mixed · 1 h 20' },
        whites: { t: 'Whites & towels', temp: '60 °C', prog: 'Cotton · 1 h 50' },
        sport: { t: 'Gym wear', temp: '30 °C', prog: 'Synthetics · 50 min' }
    };
    var SLOT_TIMES = [8, 11, 14, 17, 20];
    // laundry-room state per [day][slot]: t = taken by a neighbour, b = you're busy, f = free for both
    var SLOT_MAP = [['t', 't', 'b', 'b', 'f'], ['f', 'b', 'b', 'f', 'f'], ['t', 'f', 'f', 'b', 'f']];
    var BEST = '1-0';

    function renderLaundry() {
        var total = S.basket.reduce(function (a, b) { return a + b.n; }, 0), cap = 30;
        var pct = Math.min(100, Math.round(total / cap * 100));
        $('#basket-panel').innerHTML =
            '<div class="panel-head"><div><div class="panel-title">Laundry basket</div><div class="panel-sub">Seen ' + esc(S.devices.filter(function (d) { return d.id === 'basket'; })[0].last) + ' · ' + total + ' items</div></div>' + localBadge() + '</div>' +
            '<div class="row between small bold" style="margin-bottom:6px"><span>' + pct + '% full</span><span>' + (pct > 75 ? 'Time to wash' : 'Plenty of room') + '</span></div>' +
            '<div class="meter"><i class="' + (pct > 75 ? 'bad' : pct > 50 ? 'warn' : '') + '" style="width:' + pct + '%"></i></div>' +
            '<div class="chips" style="margin-top:14px">' + S.basket.map(function (b) { return '<span class="chip static">' + b.n + ' × ' + esc(b.name) + '</span>'; }).join('') + '</div>';

        $('#wardrobe-panel').innerHTML = '<ul class="list">' + S.wardrobe.map(function (w) {
            var r = runway(w), cls = r <= 1 ? 'bad' : r <= 3 ? 'warn' : '';
            return '<li style="display:block"><div class="row between"><div class="item-title">' + esc(w.cat) + '</div><div class="small bold" style="' + (r <= 1 ? 'color:var(--c-brand)' : '') + '">' + (w.clean === 0 ? 'Out now' : r >= 99 ? '—' : r + (r === 1 ? ' day' : ' days')) + '</div></div>' +
                '<div class="row" style="margin-top:6px"><div class="meter grow"><i class="' + cls + '" style="width:' + Math.round(w.clean / w.total * 100) + '%"></i></div><span class="tiny bold muted" style="width:56px;text-align:right">' + w.clean + ' / ' + w.total + ' clean</span></div></li>';
        }).join('') + '</ul>';

        var groups = {};
        S.basket.forEach(function (b) { (groups[b.group] = groups[b.group] || []).push(b); });
        var mr = minRunway();
        $('#loads-panel').innerHTML =
            '<div class="panel-head"><div><div class="panel-title">' + Object.keys(groups).length + ' loads before ' + dayShort(Math.max(0, mr)) + '</div><div class="panel-sub">Underwear runs out in ' + mr + ' days</div></div><span class="badge orange">Plan</span></div>' +
            '<ul class="list">' + Object.keys(groups).map(function (g, i) {
                var L = LOADS[g];
                return '<li><span class="icon-btn" style="font-weight:800">' + (i + 1) + '</span><div class="grow"><div class="item-title">' + L.t + ' · ' + L.temp + '</div><div class="item-sub">' +
                    esc(groups[g].map(function (b) { return b.n + ' ' + b.name.toLowerCase(); }).join(', ')) + ' · ' + L.prog + '</div></div></li>';
            }).join('') + '</ul><p class="small muted" style="margin-top:10px">Tip: gym wear can go with darks at 40 °C if you only get one slot.</p>';

        renderSlots();
    }
    function renderSlots() {
        var mine = {};
        S.laundryBookings.forEach(function (b) { mine[b.key] = true; });
        var head = '<div></div>' + [0, 1, 2].map(function (d) { return '<div class="h">' + (d === 0 ? 'Today' : d === 1 ? 'Tomorrow' : dayShort(d).split(' ')[0]) + '<br><span class="muted">' + dayShort(d).split(' ')[1] + '</span></div>'; }).join('');
        var body = SLOT_TIMES.map(function (t, si) {
            return '<div class="t">' + fmtH(t) + '</div>' + [0, 1, 2].map(function (d) {
                var k = d + '-' + si, st = SLOT_MAP[d][si];
                if (mine[k]) return '<button class="slot mine" data-k="' + k + '" type="button" aria-label="Your booking">Yours</button>';
                if (st === 't') return '<span class="slot taken" aria-label="Taken">Taken</span>';
                if (st === 'b') return '<span class="slot busy" aria-label="You are busy">Busy</span>';
                var cls = UI.laundrySel === k ? 'sel' : (k === BEST ? 'best' : 'free');
                return '<button class="slot ' + cls + '" data-k="' + k + '" type="button">' + (k === BEST && UI.laundrySel !== k ? '★ Best' : 'Free') + '</button>';
            }).join('');
        }).join('');
        var sel = UI.laundrySel ? UI.laundrySel.split('-') : null;
        $('#slots-panel').innerHTML =
            '<div class="panel-sub" style="margin-bottom:12px">Shared laundry room, building B · 3 h slots, 2 machines</div>' +
            '<div class="slot-grid">' + head + body + '</div>' +
            '<div class="legend"><span><i style="background:var(--c-card-green)"></i>Both free</span><span><i style="background:rgba(0,0,0,.1)"></i>Your calendar busy</span><span><i style="background:repeating-linear-gradient(45deg,rgba(0,0,0,.15) 0 3px,transparent 3px 6px)"></i>Taken</span></div>' +
            (S.laundryBookings.length ? '<hr class="divider"><div class="label-caps" style="margin-bottom:6px">Your bookings</div><ul class="list">' + S.laundryBookings.map(function (b) {
                return '<li><span class="icon-btn">' + I.cal + '</span><div class="grow"><div class="item-title">' + esc(b.label) + '</div><div class="item-sub">Room B · reminder 15 min before</div></div><button class="pill outline" data-cancel="' + b.key + '" type="button">Cancel</button></li>';
            }).join('') + '</ul>' : '') +
            '<button class="pill brand block" id="reserve" type="button" style="margin-top:14px"' + (sel ? '' : ' disabled') + '>' +
            (sel ? 'Reserve ' + (sel[0] === '0' ? 'today' : sel[0] === '1' ? 'tomorrow' : dayShort(+sel[0])) + ' ' + fmtH(SLOT_TIMES[+sel[1]]) + '–' + fmtH(SLOT_TIMES[+sel[1]] + 3) : 'Pick a free slot') + '</button>';

        $$('#slots-panel .slot[data-k]').forEach(function (b) {
            b.addEventListener('click', function () {
                if (b.classList.contains('mine')) return;
                UI.laundrySel = UI.laundrySel === b.dataset.k ? null : b.dataset.k; renderSlots();
            });
        });
        $$('#slots-panel [data-cancel]').forEach(function (b) {
            b.addEventListener('click', function () { S.laundryBookings = S.laundryBookings.filter(function (x) { return x.key !== b.dataset.cancel; }); save(); renderSlots(); toast('Booking cancelled'); });
        });
        var rb = $('#reserve');
        if (rb) rb.addEventListener('click', function () {
            if (!sel) return;
            var label = (sel[0] === '0' ? 'Today' : sel[0] === '1' ? 'Tomorrow' : dayShort(+sel[0])) + ' ' + fmtH(SLOT_TIMES[+sel[1]]) + '–' + fmtH(SLOT_TIMES[+sel[1]] + 3);
            S.laundryBookings.push({ key: UI.laundrySel, label: label });
            UI.laundrySel = null;
            markTaskByDeco('deco-garland');
            save(); renderSlots();
            toast('Laundry room booked: ' + label);
        });
    }

    /* =========================================================
       EXPLORE — events, travel, products
       ========================================================= */
    function art(key) {
        var A = {
            jazz: '<rect width="160" height="80" fill="#353B35"/><circle cx="40" cy="40" r="22" fill="#B8A1D3"/><circle cx="40" cy="40" r="6" fill="#353B35"/><path d="M90 60 Q96 20 120 18 L124 24 Q104 28 102 60 Q100 70 92 68 Z" fill="#D6744C"/><circle cx="135" cy="20" r="3" fill="#FFFEFA"/><circle cx="70" cy="18" r="2" fill="#FFFEFA"/><path d="M60 62 h20 M64 56 v12 M76 56 v12" stroke="#8E9C7E" stroke-width="3"/>',
            climb: '<rect width="160" height="80" fill="#8E9C7E"/><path d="M0 80 L40 10 L80 80 Z" fill="#B8A1D3" opacity=".9"/><path d="M60 80 L110 0 L160 80 Z" fill="#353B35" opacity=".85"/><circle cx="96" cy="30" r="4" fill="#D6744C"/><circle cx="112" cy="46" r="5" fill="#FFFEFA"/><circle cx="100" cy="60" r="4" fill="#B8A1D3"/><circle cx="36" cy="40" r="3" fill="#FFFEFA"/>',
            market: '<rect width="160" height="80" fill="#B8A1D3"/><rect x="20" y="36" width="50" height="34" fill="#FFFEFA"/><path d="M14 36 L45 16 L76 36 Z" fill="#D6744C"/><rect x="88" y="40" width="50" height="30" fill="#353B35"/><path d="M82 40 L113 22 L144 40 Z" fill="#8E9C7E"/><circle cx="45" cy="54" r="5" fill="#D6744C"/><circle cx="113" cy="55" r="5" fill="#B8A1D3"/>',
            design: '<rect width="160" height="80" fill="#FFFEFA"/><circle cx="44" cy="40" r="24" fill="#D6744C"/><rect x="74" y="16" width="34" height="48" fill="#8E9C7E"/><path d="M118 64 L138 18 L154 64 Z" fill="#B8A1D3"/><circle cx="91" cy="40" r="7" fill="#FFFEFA"/>',
            aurora: '<rect width="160" height="80" fill="#353B35"/><path d="M0 40 Q40 10 80 34 T160 22 L160 44 Q120 56 80 46 T0 58 Z" fill="#8E9C7E" opacity=".9"/><path d="M0 30 Q50 6 90 26 T160 12" fill="none" stroke="#FFFEFA" stroke-width="1" opacity=".5"/><path d="M0 80 L30 58 L54 72 L86 52 L120 74 L160 56 L160 80 Z" fill="#FFFEFA"/><circle cx="130" cy="14" r="1.5" fill="#FFFEFA"/><circle cx="24" cy="12" r="1.2" fill="#FFFEFA"/><rect x="66" y="58" width="16" height="12" fill="#B8A1D3"/>',
            ferry: '<rect width="160" height="80" fill="#FFFEFA"/><rect y="56" width="160" height="24" fill="#8E9C7E"/><path d="M30 56 L130 56 L120 68 L40 68 Z" fill="#353B35"/><rect x="50" y="40" width="60" height="16" fill="#FFFEFA" stroke="#353B35" stroke-width="2"/><rect x="70" y="28" width="10" height="12" fill="#D6744C"/><circle cx="130" cy="20" r="10" fill="#B8A1D3"/>'
        };
        var svg = A[key];
        if (!svg && /^boot/.test(key)) {
            var cols = { boot1: ['#353B35', '#B8A1D3'], boot2: ['#6b3b22', '#353B35'], boot3: ['#8E9C7E', '#353B35'], boot4: ['#FFFEFA', '#D6744C'], boot5: ['#353B35', '#8E9C7E'], boot6: ['#353B35', '#FFFEFA'] }[key];
            var bg = { boot1: '#B8A1D3', boot2: '#FFFEFA', boot3: '#FFFEFA', boot4: '#8E9C7E', boot5: '#B8A1D3', boot6: '#D6744C' }[key];
            svg = '<rect width="160" height="160" fill="' + bg + '"/><path d="M50 30 L90 30 L92 92 Q130 96 136 116 L136 126 L44 126 L44 100 Q46 60 50 30 Z" fill="' + cols[0] + '"/><rect x="44" y="120" width="92" height="10" rx="3" fill="' + cols[1] + '"/><path d="M52 40 h36" stroke="' + cols[1] + '" stroke-width="3"/>';
            return '<svg viewBox="0 0 160 160" preserveAspectRatio="xMidYMid slice" aria-hidden="true">' + svg + '</svg>';
        }
        return '<svg viewBox="0 0 160 80" preserveAspectRatio="xMidYMid slice" aria-hidden="true">' + (svg || A.design) + '</svg>';
    }

    function renderExplore() {
        $$('#screen-explore .tab').forEach(function (t) {
            var on = t.dataset.tab === UI.exploreTab;
            t.classList.toggle('on', on); t.setAttribute('aria-selected', String(on));
        });
        if (UI.exploreTab === 'products') return renderProducts();
        var kind = UI.exploreTab;
        if (!UI.interests) UI.interests = ['jazz', 'bouldering', 'christmas'];
        var body = $('#explore-body');
        body.innerHTML =
            '<div class="panel dark">' +
            '<form class="search-row" id="ex-form"><input class="field" name="q" value="' + esc(UI.exploreQuery[kind]) + '" placeholder="' + (kind === 'travel' ? 'Where do you dream of going?' : 'What are you in the mood for?') + '" aria-label="Search"><button class="pill orange" type="submit" aria-label="Search">' + I.search + '</button></form>' +
            (kind === 'events' ? '<div class="label-caps" style="margin:14px 0 8px">From your memories</div><div class="chips">' + ['jazz', 'bouldering', 'christmas', 'design', 'food'].map(function (k) {
                return '<button class="chip' + (UI.interests.indexOf(k) !== -1 ? ' on' : '') + '" data-int="' + k + '" type="button">' + k + '</button>';
            }).join('') + '</div>' :
                '<div class="row" style="margin-top:12px;gap:8px"><span class="badge">From Helsinki</span><span class="badge">Budget ≤ €300</span><span class="badge">Weekends</span></div>') +
            '</div><div id="ex-results"></div>';
        $('#ex-form').addEventListener('submit', function (e) { e.preventDefault(); UI.exploreQuery[kind] = this.q.value; runExplore(kind); });
        $$('#explore-body [data-int]').forEach(function (c) {
            c.addEventListener('click', function () {
                var k = c.dataset.int, i = UI.interests.indexOf(k);
                if (i === -1) UI.interests.push(k); else UI.interests.splice(i, 1);
                c.classList.toggle('on'); runExplore(kind);
            });
        });
        if (!UI.exploreResults[kind]) runExplore(kind); else renderExploreResults(kind);
    }
    function runExplore(kind) {
        UI.exploreLoading = true; renderExploreResults(kind);
        API.explore(UI.exploreQuery[kind], kind, UI.interests).then(function (r) { UI.exploreResults[kind] = r.results; })
            .catch(function () { toast('Search failed, try again'); })
            .then(function () { UI.exploreLoading = false; if (UI.exploreTab === kind && current === 'explore') renderExploreResults(kind); });
    }
    function renderExploreResults(kind) {
        var el = $('#ex-results'); if (!el) return;
        if (UI.exploreLoading) { el.innerHTML = loadingHtml('Searching the live web with Exa…') + '<div class="skeleton"></div><div class="skeleton"></div>'; return; }
        var list = UI.exploreResults[kind] || [];
        el.innerHTML = '<div class="section-title" style="margin-top:1.4rem">' + list.length + ' picks <span class="kicker">tap for details</span></div>' + list.map(function (r, i) {
            return '<article class="result" data-i="' + i + '">' +
                '<div class="thumb">' + art(r.art) + '<span class="badge light thumb-tag">' + (kind === 'travel' ? 'Trip' : 'Event') + '</span></div>' +
                '<div class="result-body"><div class="result-title">' + esc(r.title) + '</div>' +
                '<div class="result-meta">' + esc(r.when) + ' · ' + esc(r.where) + ' · <b>' + esc(r.price) + '</b></div>' +
                '<div class="result-why">' + esc(r.why) + '</div>' +
                '<div class="result-more">' +
                    '<div class="gallery"><div>' + art(r.art) + '</div><div style="filter:hue-rotate(40deg)">' + art(r.art) + '</div><div style="filter:saturate(.6)">' + art(r.art) + '<span class="play"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="11" fill="rgba(41,45,44,.7)"/><path d="M10 8l6 4-6 4z" fill="#FFFEFA"/></svg></span></div></div>' +
                    (r.details ? '<ul class="list" style="margin-top:12px">' + r.details.map(function (d) { return '<li style="padding:7px 0"><span class="label-caps" style="width:54px;flex:none">' + esc(d.k) + '</span><span class="small">' + esc(d.v) + '</span></li>'; }).join('') + '</ul>' : '') +
                    (r.posts || []).map(function (p) { return '<div class="social-post"><div class="who">' + esc(p.who) + ' · social</div>' + esc(p.text) + '</div>'; }).join('') +
                '</div>' +
                sourcesHtml(r.sources) +
                '<div class="pill-row" style="margin-top:12px"><button class="pill dark" data-more type="button">Details</button><button class="pill outline" data-save type="button">' + I.cal + (kind === 'travel' ? 'Plan it' : 'Add to calendar') + '</button></div>' +
                '</div></article>';
        }).join('');
        $$('#ex-results .result').forEach(function (card) {
            $('[data-more]', card).addEventListener('click', function () {
                card.classList.toggle('open'); this.textContent = card.classList.contains('open') ? 'Less' : 'Details';
            });
            $('[data-save]', card).addEventListener('click', function () {
                var r = list[+card.dataset.i];
                if (/jazz/i.test(r.title)) markTaskByDeco('deco-orange-ball');
                this.innerHTML = I.check + 'Saved'; this.disabled = true;
                toast(kind === 'travel' ? 'Trip saved. I\'ll watch prices for you' : 'Added to your calendar');
            });
        });
    }

    function renderProducts() {
        var P = UI.product;
        var body = $('#explore-body');
        body.innerHTML =
            '<div class="panel dark">' +
            '<div class="panel-title" style="margin-bottom:10px">What are you looking for?</div>' +
            '<form id="pr-form"><textarea class="field" name="q" rows="2" aria-label="Describe the product" style="resize:none">' + esc(P.query) + '</textarea>' +
            '<div class="row" style="margin-top:10px"><label class="pill outline" style="cursor:pointer">' + I.upload + (P.image ? 'Change photo' : 'Add a photo') + '<input type="file" accept="image/*" id="pr-img" class="sr-only"></label>' +
            (P.image ? '<img src="' + P.image + '" alt="Your reference photo" style="width:34px;height:34px;border-radius:8px;object-fit:cover">' : '') +
            '<span class="grow"></span><button class="pill orange" type="submit">' + I.search + 'Find</button></div></form>' +
            (P.image ? '<p class="tiny muted" style="margin-top:8px">' + I.lock.replace('<svg', '<svg style="display:inline;width:11px;height:11px;vertical-align:-1px"') + ' Photo analysed on-device; only the detected features are searched.</p>' : '') +
            '</div><div id="pr-results"></div>';

        $('#pr-form').addEventListener('submit', function (e) {
            e.preventDefault(); P.query = this.q.value; P.keys = null; P.liked = []; P.disliked = []; P.round = 1; runProducts();
        });
        $('#pr-img').addEventListener('change', function () {
            var f = this.files && this.files[0]; if (!f) return;
            var rd = new FileReader();
            rd.onload = function () { P.image = rd.result; renderProducts(); };
            rd.readAsDataURL(f);
        });
        if (P.results || P.loading) renderProductResults(); else runProducts();
    }
    function runProducts() {
        var P = UI.product;
        P.loading = true; renderProductResults();
        API.findProducts(P.query, { keys: P.keys, liked: P.liked, disliked: P.disliked, round: P.round, image: !!P.image })
            .then(function (r) { P.keys = r.keys; P.results = r.results; P.strategy = r.strategy; })
            .catch(function () { toast('Product search failed'); })
            .then(function () { P.loading = false; if (current === 'explore' && UI.exploreTab === 'products') renderProductResults(); });
    }
    function renderProductResults() {
        var P = UI.product, el = $('#pr-results'); if (!el) return;
        if (P.loading) { el.innerHTML = loadingHtml(P.round > 1 ? 'Updating search with your feedback…' : 'Working out what matters to you…') + '<div class="skeleton"></div>'; return; }
        if (!P.results) { el.innerHTML = ''; return; }
        el.innerHTML =
            '<div class="panel light" style="margin-top:18px">' +
            '<div class="row between"><div class="panel-title">Key features I\'m matching</div><span class="badge">Round ' + P.round + '</span></div>' +
            '<div class="chips" style="margin-top:10px">' + P.keys.map(function (k, i) { return '<button class="chip on" data-key="' + i + '" type="button" aria-label="Remove ' + esc(k) + '">' + esc(k) + ' <span class="x">×</span></button>'; }).join('') +
            '<form id="key-add" style="display:inline-flex"><input class="field" name="k" placeholder="+ add" style="min-height:32px;width:90px;padding:4px 10px;border-radius:999px;font-size:.78rem" aria-label="Add a feature"></form></div>' +
            '<p class="small muted" style="margin-top:10px">' + esc(P.strategy) + '</p></div>' +
            '<div class="product-grid">' + P.results.map(function (p) {
                var liked = P.liked.indexOf(p.id) !== -1, dis = P.disliked.indexOf(p.id) !== -1;
                return '<div class="product' + (liked ? ' liked' : '') + (dis ? ' disliked' : '') + '" data-id="' + p.id + '">' +
                    '<div class="thumb">' + art(p.art) + '</div>' +
                    '<div class="product-body"><div class="result-title">' + esc(p.title) + '</div><div class="price">€' + p.price + '</div>' +
                    '<div class="item-sub">' + esc(p.store) + '</div>' +
                    (p.matched.length ? '<div class="match">✓ ' + esc(p.matched.join(', ')) + '</div>' : '') +
                    sourcesHtml(p.sources.slice(0, 1), ' ') +
                    '<div class="fb"><button type="button" data-fb="like" class="' + (liked ? 'on-like' : '') + '" aria-pressed="' + liked + '">' + I.up + 'More</button><button type="button" data-fb="dislike" class="' + (dis ? 'on-dislike' : '') + '" aria-pressed="' + dis + '">' + I.down + 'Not this</button></div>' +
                    '</div></div>';
            }).join('') + '</div>' +
            '<button class="scallop-btn wide" id="refine" type="button" style="margin-top:22px"' + (P.liked.length + P.disliked.length ? '' : ' disabled') + '><span>' +
            (P.liked.length + P.disliked.length ? 'Search again with my ' + (P.liked.length + P.disliked.length) + ' reactions' : 'React to a few, then I\'ll search again') + '</span></button>';

        $$('#pr-results [data-key]').forEach(function (c) {
            c.addEventListener('click', function () { P.keys.splice(+c.dataset.key, 1); P.round++; runProducts(); });
        });
        $('#key-add').addEventListener('submit', function (e) {
            e.preventDefault(); var k = this.k.value.trim().toLowerCase(); if (!k) return;
            P.keys.push(k); P.round++; runProducts();
        });
        $$('#pr-results .product').forEach(function (card) {
            $$('[data-fb]', card).forEach(function (b) {
                b.addEventListener('click', function () {
                    var id = card.dataset.id, like = b.dataset.fb === 'like';
                    var a = like ? P.liked : P.disliked, o = like ? P.disliked : P.liked;
                    var i = a.indexOf(id); if (i === -1) a.push(id); else a.splice(i, 1);
                    var j = o.indexOf(id); if (j !== -1) o.splice(j, 1);
                    renderProductResults();
                });
            });
        });
        $('#refine').addEventListener('click', function () { P.round++; runProducts(); });
    }
    $$('#screen-explore .tab').forEach(function (t) { t.addEventListener('click', function () { UI.exploreTab = t.dataset.tab; renderExplore(); }); });

    /* =========================================================
       CHAT
       ========================================================= */
    function renderChat() {
        S.chatSeen = true; save();
        renderConsent();
        var log = $('#chat-log');
        log.innerHTML = '';
        S.chat.forEach(function (m) { log.appendChild(bubble(m, true)); });
        setTimeout(function () { window.scrollTo({ top: document.body.scrollHeight }); }, 30);
    }
    function renderConsent() {
        var slot = $('#consent-slot');
        if (S.memoryConsent === null) {
            slot.innerHTML = '<div class="panel green tilt-l" style="margin-bottom:16px"><div class="panel-title">Can I remember stuff you tell me?</div>' +
                '<p class="small" style="margin-top:6px;opacity:.9">Things like your favourite food or hobbies, so I can find things you\'ll actually like. You can see and delete everything under Me.</p>' +
                '<div class="pill-row" style="margin-top:12px"><button class="pill" data-c="yes" type="button">Sure, remember</button><button class="pill outline" data-c="no" type="button">Not now</button></div></div>';
            $$('[data-c]', slot).forEach(function (b) {
                b.addEventListener('click', function () {
                    S.memoryConsent = b.dataset.c === 'yes'; save(); renderConsent();
                    pushBot({ text: S.memoryConsent ? 'Yay, thank you! 🫶 I\'ll only remember the nice-to-know stuff.' : 'Totally fine! I won\'t save anything. You can change this anytime in Me.' });
                });
            });
        } else {
            slot.innerHTML = '<p class="small bold" style="margin-bottom:12px;opacity:.8">Memory is ' + (S.memoryConsent ? 'on' : 'off') + ' · <a href="#/me" class="exa-link">manage</a></p>';
        }
    }
    function bubble(m, noAnim) {
        var d = document.createElement('div');
        if (m.from === 'mem') {
            d.className = 'mem-note';
            d.innerHTML = '📌 Saved to memories: "' + esc(m.text) + '"' + (m.undoId ? ' <button type="button">Undo</button>' : '');
            var u = $('button', d);
            if (u) u.addEventListener('click', function () {
                S.memories = S.memories.filter(function (x) { return x.id !== m.undoId; });
                m.text = m.text + ' (removed)'; m.undoId = null; save();
                d.innerHTML = '📌 Forgotten. I won\'t keep that.';
            });
            return d;
        }
        d.className = 'bubble ' + (m.from === 'me' ? 'me' : 'bot') + (m.kind === 'care' ? ' care' : m.kind === 'find' ? ' card' : '');
        if (noAnim) d.style.animation = 'none';
        var html = esc(m.text);
        if (m.link) html += ' <a href="' + m.link + '" class="exa-link" style="font-weight:700">Open →</a>';
        html += sourcesHtml(m.sources, 'Found via');
        if (m.kind === 'care' && !m.resolved) {
            var primary = (S.contacts.filter(function (c) { return c.on && !c.police; })[0] || { name: 'someone' }).name;
            html += '<div class="pill-row"><button class="pill" data-care="contact" type="button">Yes, message ' + esc(primary) + '</button>' +
                '<button class="pill outline" data-care="lines" type="button">Show support lines</button>' +
                '<button class="pill outline" data-care="no" type="button">Not now</button></div>';
        }
        d.innerHTML = html;
        $$('[data-care]', d).forEach(function (b) {
            b.addEventListener('click', function () {
                var act = b.dataset.care;
                if (act === 'contact') return confirmReachOut(m, d);
                m.resolved = true; save();
                $('.pill-row', d).remove();
                if (act === 'lines') pushBot({ text: 'Here if you want to talk to someone right now. MIELI Crisis Helpline: 09 2525 0111 (24/7). In an emergency, call 112. And I\'m still right here too 💛', sources: [{ title: 'MIELI Mental Health Finland', url: 'https://mieli.fi/en/' }] });
                else pushBot({ text: 'Okay, no pressure at all. I\'m here whenever. Want to just talk about something random for a bit?' });
            });
        });
        return d;
    }
    function confirmReachOut(m, d) {
        var c = S.contacts.filter(function (x) { return x.on && !x.police; })[0];
        if (!c) { toast('Add an emergency contact in Me first'); return; }
        var msg = 'Hi ' + c.name + ', it\'s Figment, ' + S.user.name + '\'s assistant. ' + S.user.name + ' asked me to let you know they could use some company today. Maybe give them a call? 💛';
        openSheet('<h2 id="sheet-title">Message ' + esc(c.name) + '?</h2><p class="lede">Only sent because you said yes. Here\'s exactly what they\'ll get:</p>' +
            '<div class="panel light" style="margin-top:12px"><div class="label-caps">' + esc(c.via) + '</div><p style="margin-top:6px">' + esc(msg) + '</p></div>' +
            '<div class="sheet-actions"><button class="pill outline" data-x type="button">Cancel</button><button class="pill brand" data-ok type="button">' + I.send + 'Send</button></div>',
            function (root) {
                $('[data-x]', root).addEventListener('click', closeSheet);
                $('[data-ok]', root).addEventListener('click', function () {
                    closeSheet(); m.resolved = true; save();
                    var pr = $('.pill-row', d); if (pr) pr.remove();
                    pushBot({ text: 'Done, I let ' + c.name + ' know 💛 Proud of you for reaching out. I\'m staying right here with you.' });
                });
            });
    }
    function pushBot(m) { m.from = 'bot'; S.chat.push(m); save(); $('#chat-log').appendChild(bubble(m)); scrollChat(); }
    function scrollChat() { window.scrollTo({ top: document.body.scrollHeight, behavior: reduce ? 'auto' : 'smooth' }); }

    function sendChat(text) {
        text = text.trim(); if (!text) return;
        var me = { from: 'me', text: text };
        S.chat.push(me); save();
        var log = $('#chat-log');
        log.appendChild(bubble(me));
        var typing = document.createElement('div');
        typing.className = 'bubble bot'; typing.innerHTML = '<span class="typing"><i></i><i></i><i></i></span>';
        log.appendChild(typing); scrollChat();
        API.chat(text, { memoryConsent: S.memoryConsent === true, memories: S.memories.map(function (m) { return m.text; }) })
            .then(function (r) {
                typing.remove();
                (r.replies || []).forEach(function (rep, i) {
                    setTimeout(function () { pushBot(rep); }, i * 700);
                });
                if (r.memory && S.memoryConsent === true) {
                    var id = uid();
                    S.memories.unshift({ id: id, text: r.memory, tag: 'chat', date: now.getDate() + ' ' + MONTHS[now.getMonth()].slice(0, 3) });
                    var note = { from: 'mem', text: r.memory, undoId: id };
                    S.chat.push(note); save();
                    setTimeout(function () { log.appendChild(bubble(note)); scrollChat(); }, 500);
                }
                markTaskByDeco('deco-bell');
            })
            .catch(function () { typing.remove(); pushBot({ text: 'Oops, lost my connection for a sec. Say that again?' }); });
    }
    $('#chat-form').addEventListener('submit', function (e) { e.preventDefault(); var i = $('#chat-input'); sendChat(i.value); i.value = ''; });
    $$('#suggest-row .chip').forEach(function (c) { c.addEventListener('click', function () { sendChat(c.textContent); }); });

    $$('[data-call]').forEach(function (b) {
        b.addEventListener('click', function () {
            var kind = b.dataset.call;
            if (kind === 'social') return openSocialSheet();
            var t0 = Date.now(), iv;
            var gb = '<svg viewBox="0 0 160 100" style="width:120px;height:80px;margin:0 auto"><line x1="40" y1="42" x2="84" y2="42" stroke="#353B35" stroke-width="10" stroke-linecap="round"/><line x1="55" y1="56" x2="47" y2="74" stroke="#353B35" stroke-width="10" stroke-linecap="round"/><line x1="69" y1="56" x2="77" y2="74" stroke="#353B35" stroke-width="10" stroke-linecap="round"/><ellipse cx="62" cy="48" rx="13" ry="16" fill="#353B35"/><circle cx="62" cy="27" r="12" fill="#353B35"/><circle cx="57.5" cy="25" r="1.8" fill="#FFFEFA"/><circle cx="66.5" cy="25" r="1.8" fill="#FFFEFA"/><path d="M57 31 Q62 35 67 31" fill="none" stroke="#FFFEFA" stroke-width="1.8" stroke-linecap="round"/><circle cx="62" cy="42" r="2.4" fill="#D6744C"/><circle cx="62" cy="50" r="2.4" fill="#D6744C"/></svg>';
            openSheet('<h2 id="sheet-title">' + (kind === 'video' ? 'Video call' : 'Voice call') + ' with Ginger</h2>' +
                '<div class="panel ' + (kind === 'video' ? 'dark' : 'orange') + '" style="text-align:center;padding:28px 18px">' + gb +
                '<div class="bold" style="margin-top:10px" id="call-status">Calling…</div>' +
                (kind === 'video' ? '<div style="position:absolute;right:12px;top:12px;width:62px;height:84px;border-radius:10px;background:#333;display:flex;align-items:center;justify-content:center;font-size:.6rem;color:#aaa">You</div>' : '') +
                '</div><p class="small muted">Also works through your linked WhatsApp or Instagram.</p>' +
                '<div class="sheet-actions"><button class="pill brand" data-x type="button">End call</button></div>',
                function (root) {
                    $('[data-x]', root).addEventListener('click', closeSheet);
                    setTimeout(function () {
                        iv = setInterval(function () {
                            var s = Math.floor((Date.now() - t0) / 1000) - 1, el = $('#call-status');
                            if (el) el.textContent = 'Connected · 0:' + (s < 10 ? '0' : '') + Math.max(0, s);
                        }, 1000);
                    }, 1200);
                },
                function () { clearInterval(iv); markTaskByDeco('deco-bell'); });
        });
    });
    function openSocialSheet() {
        openSheet('<h2 id="sheet-title">Ginger on social</h2><p class="lede">Ginger has its own account, <b>@figment.ginger</b>. It sends you fun finds there, and you can call or video chat through your linked apps.</p>' +
            '<div class="panel light" style="margin-top:12px"><ul class="list">' + S.social.map(function (s) {
                return '<li><div class="grow"><div class="item-title">' + esc(s.name) + '</div><div class="item-sub">' + esc(s.handle) + '</div></div>' + (s.on ? '<span class="badge green">Linked</span>' : '<a class="badge" href="#/me">Link</a>') + '</li>';
            }).join('') + '</ul></div>' +
            '<div class="label-caps" style="margin:16px 0 8px">Recently shared with you</div>' +
            S.agentPosts.map(function (p) { return '<div class="panel dark" style="margin-bottom:10px"><div class="tiny muted">@figment.ginger · ' + esc(p.when) + '</div><p class="small" style="margin-top:4px">' + esc(p.text) + '</p>' + sourcesHtml(p.sources, 'Found via') + '</div>'; }).join('') +
            '<div class="sheet-actions"><button class="pill dark" data-x type="button">Close</button></div>',
            function (root) { $('[data-x]', root).addEventListener('click', closeSheet); $$('a[href^="#"]', root).forEach(function (a) { a.addEventListener('click', closeSheet); }); });
    }

    /* =========================================================
       HEALTH
       ========================================================= */
    function spark(arr, color) {
        var mn = Math.min.apply(null, arr), mx = Math.max.apply(null, arr), w = 100, h = 26;
        var pts = arr.map(function (v, i) { return (i / (arr.length - 1) * w).toFixed(1) + ',' + (h - 3 - (v - mn) / ((mx - mn) || 1) * (h - 6)).toFixed(1); }).join(' ');
        return '<svg class="spark" viewBox="0 0 100 26" preserveAspectRatio="none"><polyline points="' + pts + '" fill="none" stroke="' + color + '" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>';
    }
    function renderHealth() {
        var L = S.healthLog, hr = L.hr[L.hr.length - 1], sl = L.sleep[L.sleep.length - 1], st = L.steps[L.steps.length - 1];
        var hrAvg = Math.round(L.hr.slice(0, 4).reduce(function (a, b) { return a + b; }, 0) / 4);
        $('#vitals-panel').innerHTML =
            '<div class="panel-head"><div><div class="panel-title">Smart watch</div><div class="panel-sub">Synced 2 min ago · last 7 days</div></div><span class="badge">' + I.lock + 'Encrypted</span></div>' +
            '<div class="stats">' +
            '<div class="stat alert"><div class="u">Resting HR</div><div class="v">' + hr + '</div><div class="u">bpm · avg ' + hrAvg + '</div>' + spark(L.hr, '#FFFEFA') + '</div>' +
            '<div class="stat alert"><div class="u">Sleep</div><div class="v">' + sl.toFixed(1) + '</div><div class="u">h · 3 short nights</div>' + spark(L.sleep, '#FFFEFA') + '</div>' +
            '<div class="stat"><div class="u">Steps</div><div class="v">' + (st / 1000).toFixed(1) + 'k</div><div class="u">today</div>' + spark(L.steps, '#B8A1D3') + '</div>' +
            '</div>';
        renderCare(); renderMeds(); renderAppt();
    }
    var MOODS = [{ id: 'great', t: 'Actually great' }, { id: 'tired', t: 'Tired' }, { id: 'stressed', t: 'Stressed' }, { id: 'unwell', t: 'A bit unwell' }];
    function renderCare() {
        var el = $('#care-panel');
        el.innerHTML = '<div class="panel orange tilt-r">' +
            '<div class="label-caps">Ginger noticed something</div>' +
            '<p class="panel-title" style="margin-top:6px;font-size:1.15rem">Hey, your resting heart rate\'s been up and you\'ve slept under 6 h for 3 nights. How are you feeling?</p>' +
            '<div class="chips" style="margin-top:12px">' + MOODS.map(function (m) { return '<button class="chip' + (UI.mood === m.id ? ' on' : '') + '" data-mood="' + m.id + '" type="button">' + m.t + '</button>'; }).join('') + '</div>' +
            '<div id="care-out"></div></div>';
        $$('[data-mood]', el).forEach(function (b) {
            b.addEventListener('click', function () {
                UI.mood = b.dataset.mood; UI.wellbeing = 'loading'; renderCare();
                API.wellbeing(UI.mood).then(function (r) { UI.wellbeing = r; renderCare(); });
            });
        });
        var out = $('#care-out');
        if (UI.wellbeing === 'loading') out.innerHTML = loadingHtml('Putting together some ideas…');
        else if (UI.wellbeing) {
            var w = UI.wellbeing;
            out.innerHTML = '<hr class="divider"><div class="label-caps" style="margin-bottom:6px">Meals that could help</div><ul class="list">' + w.meals.map(function (m) {
                return '<li><div class="grow"><div class="item-title">' + esc(m.title) + '</div><div class="item-sub">' + esc(m.why) + '</div></div><span class="badge">' + esc(m.time) + '</span></li>';
            }).join('') + '</ul><div class="label-caps" style="margin:14px 0 6px">Little things to try</div><ul class="list">' + w.activities.map(function (a) {
                return '<li style="padding:6px 0"><span class="small bold">→ ' + esc(a) + '</span></li>';
            }).join('') + '</ul>' + sourcesHtml(w.sources) +
            '<div class="pill-row" style="margin-top:14px"><button class="pill dark" id="add-ingr" type="button">' + I.plus + 'Add ingredients to list</button></div>';
            $('#add-ingr').addEventListener('click', function () {
                w.meals.forEach(function (m) {
                    var n = m.title.split(/,| & | with /)[0].trim();
                    if (!S.shopping.some(function (i) { return i.name === n; })) S.shopping.push({ id: uid(), name: n, qty: 1, prio: 2, from: 'health', note: 'For: ' + m.title });
                });
                save(); UI.deals = null; this.innerHTML = I.check + 'Added to shopping list'; this.disabled = true;
            });
        }
    }
    function renderMeds() {
        var el = $('#meds-panel');
        el.innerHTML =
            '<form class="search-row" id="med-form"><input class="field" name="q" value="' + esc(UI.medsQuery) + '" placeholder="Symptom or medicine, e.g. sore throat" aria-label="Symptom or medicine"><button class="pill brand" type="submit" aria-label="Search">' + I.search + '</button></form>' +
            '<div class="chips" style="margin-top:10px">' + ['Sore throat', 'Headache', 'Can\'t sleep', 'Blocked nose'].map(function (c) { return '<button class="chip" data-q="' + c + '" type="button">' + c + '</button>'; }).join('') + '</div>' +
            '<div id="med-out"></div>' +
            '<p class="tiny muted" style="margin-top:12px">I\'m not a doctor. These are over-the-counter options only; ask a pharmacist if unsure, and see a doctor if symptoms last.</p>';
        $('#med-form').addEventListener('submit', function (e) { e.preventDefault(); runMeds(this.q.value); });
        $$('[data-q]', el).forEach(function (c) { c.addEventListener('click', function () { runMeds(c.dataset.q); }); });
        renderMedOut();
    }
    function runMeds(q) {
        if (!q.trim()) return;
        UI.medsQuery = q; UI.medsLoading = true; $('#med-form').q.value = q; renderMedOut();
        API.findMedicine(q).then(function (r) { UI.meds = r.results; UI.medsLoading = false; renderMedOut(); });
    }
    function renderMedOut() {
        var out = $('#med-out'); if (!out) return;
        if (UI.medsLoading) { out.innerHTML = loadingHtml('Checking pharmacies near you…'); return; }
        if (!UI.meds) { out.innerHTML = ''; return; }
        out.innerHTML = '<ul class="list" style="margin-top:14px">' + UI.meds.map(function (m, i) {
            return '<li style="display:block"><div class="row between" style="align-items:flex-start"><div class="grow"><div class="item-title">' + esc(m.name) + '</div><div class="item-sub">' + esc(m.pharmacy) + ' · delivery ~' + esc(m.eta) + '</div></div><div class="bold">' + euro(m.price) + '</div></div>' +
                '<p class="tiny" style="margin-top:4px;opacity:.75">' + esc(m.note) + '</p>' + sourcesHtml(m.sources) +
                '<button class="pill brand" data-order="' + i + '" type="button" style="margin-top:10px">' + I.bag + 'Order delivery</button></li>';
        }).join('') + '</ul>';
        $$('[data-order]', out).forEach(function (b) {
            b.addEventListener('click', function () {
                var m = UI.meds[+b.dataset.order];
                openSheet('<h2 id="sheet-title">Order from ' + esc(m.pharmacy) + '</h2>' +
                    '<div class="panel light"><ul class="list"><li><div class="grow item-title">' + esc(m.name) + '</div><div class="bold">' + euro(m.price) + '</div></li>' +
                    '<li><div class="grow item-sub">Delivery to ' + esc(S.user.home) + '</div><div class="small bold">€4.90</div></li>' +
                    '<li><div class="grow item-title">Total · arrives ~' + esc(m.eta) + '</div><div class="bold">' + euro(m.price + 4.9) + '</div></li></ul></div>' +
                    '<p class="tiny muted">Payment and any pharmacist questions happen in the pharmacy\'s own app.</p>' +
                    '<div class="sheet-actions"><button class="pill outline" data-x type="button">Cancel</button><button class="pill brand" data-ok type="button">Confirm order</button></div>',
                    function (root) {
                        $('[data-x]', root).addEventListener('click', closeSheet);
                        $('[data-ok]', root).addEventListener('click', function () { closeSheet(); toast('Order sent. Arriving in ~' + m.eta + ' (demo)'); });
                    });
            });
        });
    }
    var APPTS = [
        { id: 'a1', when: 'Mon ' + dayShort(2).split(' ')[1] + ' · 08:30', where: 'Kallio Health Centre (GP)', why: 'Before your 10:00 lecture' },
        { id: 'a2', when: 'Tue ' + dayShort(3).split(' ')[1] + ' · 15:15', where: 'Mehiläinen Ruoholahti', why: 'Your afternoon is free' },
        { id: 'a3', when: 'Today · video', where: 'Online nurse chat', why: 'No travel, ~20 min wait' }
    ];
    function renderAppt() {
        var el = $('#appt-panel');
        el.innerHTML = '<div class="panel-title">Times that fit your calendar</div><div class="panel-sub" style="margin-bottom:10px">Based on your free slots this week</div>' +
            '<div class="stack">' + APPTS.map(function (a) {
                var booked = UI.apptBooked === a.id, sel = UI.apptSel === a.id;
                return '<button class="row" data-a="' + a.id + '" type="button" style="width:100%;text-align:left;padding:10px 12px;border-radius:12px;background:' + (booked || sel ? '#FFFEFA' : 'rgba(255,255,255,.1)') + ';color:' + (booked || sel ? '#353B35' : 'inherit') + '">' +
                    '<div class="grow"><div class="item-title">' + esc(a.when) + '</div><div class="item-sub">' + esc(a.where) + ' · ' + esc(a.why) + '</div></div>' +
                    (booked ? '<span class="badge green">Booked</span>' : sel ? '<span class="badge red">Selected</span>' : '') + '</button>';
            }).join('') + '</div>' +
            '<div class="pill-row" style="margin-top:14px"><button class="pill" id="book-appt" type="button" style="flex:1"' + (UI.apptSel && UI.apptSel !== UI.apptBooked ? '' : ' disabled') + '>' + I.cal + 'Book appointment</button></div>' +
            '<hr class="divider"><div class="row between"><div><div class="item-title">Need to go now?</div><div class="item-sub">I\'ll book a ride to the nearest ER</div></div><button class="pill orange" id="ride-btn" type="button">' + I.car + 'Ride</button></div>' +
            (UI.ride ? '<div class="panel dark" style="margin:12px 0 0;padding:12px 14px"><div class="row between"><div><div class="item-title">' + esc(UI.ride.car) + '</div><div class="item-sub">' + esc(UI.ride.dest) + '</div></div><span class="badge orange">' + esc(UI.ride.eta) + '</span></div></div>' : '') +
            '<p class="tiny" style="margin-top:12px;opacity:.85">Severe chest pain, trouble breathing or fainting? Call <b>112</b> right away.</p>';
        $$('[data-a]', el).forEach(function (b) { b.addEventListener('click', function () { UI.apptSel = b.dataset.a; renderAppt(); }); });
        $('#book-appt').addEventListener('click', function () { UI.apptBooked = UI.apptSel; renderAppt(); toast('Appointment booked and added to your calendar'); });
        $('#ride-btn').addEventListener('click', openRide);
    }
    function openRide() {
        var dests = [{ n: 'Haartman Hospital ER', d: '4.1 km · 11 min', f: '€14–18' }, { n: 'Meilahti Hospital ER', d: '5.6 km · 14 min', f: '€17–21' }];
        var pick = 0;
        openSheet('<h2 id="sheet-title">Ride to hospital</h2><p class="lede">Pick-up from your current location.</p>' +
            '<div class="stack" style="margin-top:12px">' + dests.map(function (d, i) {
                return '<button class="panel ' + (i === 0 ? 'dark' : 'light') + '" data-d="' + i + '" type="button" style="width:100%;text-align:left;margin:0"><div class="row between"><div><div class="item-title">' + d.n + '</div><div class="item-sub">' + d.d + '</div></div><div class="bold">' + d.f + '</div></div></button>';
            }).join('') + '</div><p class="tiny muted" style="margin-top:10px">Booked through your linked Uber account. Fare shown is an estimate.</p>' +
            '<div class="sheet-actions"><button class="pill outline" data-x type="button">Cancel</button><button class="pill brand" data-ok type="button">' + I.car + 'Request ride</button></div>',
            function (root) {
                $$('[data-d]', root).forEach(function (b) {
                    b.addEventListener('click', function () {
                        pick = +b.dataset.d;
                        $$('[data-d]', root).forEach(function (x) { x.className = 'panel ' + (+x.dataset.d === pick ? 'dark' : 'light'); });
                    });
                });
                $('[data-x]', root).addEventListener('click', closeSheet);
                $('[data-ok]', root).addEventListener('click', function () {
                    closeSheet(); UI.ride = { car: 'Toyota Corolla · white · ZKT-482', dest: 'To ' + dests[pick].n, eta: '4 min away' };
                    renderAppt(); toast('Driver on the way (demo)');
                });
            });
    }

    /* =========================================================
       SAFETY
       ========================================================= */
    var SOS_TYPES = ['Medical', 'Break-in', 'Being followed', 'Fire', 'Other'];
    var COORDS = '60.1841° N, 24.9497° E · ±5 m';
    function mapSvg() {
        return '<svg viewBox="0 0 300 150" preserveAspectRatio="xMidYMid slice"><rect width="300" height="150" fill="#E8E2D6"/>' +
            '<path d="M0 110 Q80 90 140 100 T300 80 L300 150 L0 150 Z" fill="#A9D4E8"/>' +
            '<path d="M0 40 L300 60 M60 0 L90 150 M190 0 L170 150 M0 80 L300 30" stroke="#fff" stroke-width="7"/>' +
            '<path d="M0 40 L300 60 M60 0 L90 150 M190 0 L170 150 M0 80 L300 30" stroke="#d9d2c4" stroke-width="1"/>' +
            '<rect x="100" y="10" width="40" height="22" fill="#cfe3c4"/><rect x="210" y="96" width="50" height="20" fill="#cfe3c4"/></svg>';
    }
    function renderSafety() {
        renderSOS(); renderCheckin(); renderDoor();
    }
    function renderSOS() {
        var el = $('#sos-panel');
        var recips = S.contacts.filter(function (c) { return c.on && !c.police; });
        if (UI.sosSent) {
            var s = UI.sosSent;
            el.className = 'panel dark';
            el.innerHTML = '<div class="panel-head"><div><div class="label-caps" style="color:var(--c-card-orange)">SOS active</div><div class="panel-title" style="font-size:1.4rem">Help is being alerted</div><div class="panel-sub">Sent ' + s.at + (s.type ? ' · ' + esc(s.type) : '') + '</div></div><span class="badge red">Live</span></div>' +
                '<div class="map">' + mapSvg() + '<span class="pin"></span><span class="coords">' + COORDS + '</span></div>' +
                '<ul class="timeline" style="margin-top:14px">' +
                '<li class="ok"><div class="item-title">Live location sharing on</div><div class="item-sub">Updates every 10 s until you\'re safe</div></li>' +
                s.to.map(function (c, i) { return '<li class="' + (i === 0 ? 'ok' : 'warn') + '"><div class="item-title">' + esc(c.name) + '</div><div class="item-sub">' + (i === 0 ? 'Delivered · seen just now' : 'Delivered') + ' · ' + esc(c.via) + '</div></li>'; }).join('') +
                (s.police ? '<li class="bad"><div class="item-title">Emergency services 112</div><div class="item-sub">Calling and sending location by SMS…</div></li>' : '') +
                '</ul><button class="pill block" id="sos-safe" type="button" style="margin-top:6px">I\'m safe now</button>';
            $('#sos-safe').addEventListener('click', function () {
                authenticate('Confirm you\'re safe so I can tell everyone.').then(function () {
                    UI.sosSent = null; renderSOS(); toast('Everyone\'s been told you\'re safe 💚');
                }).catch(function () {});
            });
            return;
        }
        el.className = 'panel light';
        el.innerHTML =
            '<div class="panel-title" style="text-align:center">Emergency</div><div class="panel-sub" style="text-align:center;margin-bottom:18px">Tap, verify with fingerprint or Face ID, and I\'ll send your exact location.</div>' +
            '<div class="sos-wrap"><button class="sos-btn" id="sos-btn" type="button" aria-label="Send SOS"><span class="big">SOS</span><span class="s">tap + verify</span>' + I.fp.replace('<svg', '<svg class="fp"') + '</button></div>' +
            '<div class="label-caps" style="margin:22px 0 8px;text-align:center">What\'s happening? (optional)</div>' +
            '<div class="chips" style="justify-content:center">' + SOS_TYPES.map(function (t) { return '<button class="chip' + (UI.sosType === t ? ' on' : '') + '" data-t="' + t + '" type="button">' + t + '</button>'; }).join('') + '</div>' +
            '<hr class="divider"><div class="row between"><div><div class="item-title">Sends to</div><div class="item-sub">' + (recips.length ? esc(recips.map(function (c) { return c.name; }).join(', ')) : 'No contacts yet') + ' · <a href="#/me" class="exa-link">edit</a></div></div></div>' +
            '<div class="row between" style="margin-top:12px"><div><div class="item-title">Also alert police (112)</div><div class="item-sub">Call + SMS with your location</div></div><label class="switch"><input type="checkbox" id="sos-police"' + (UI.sosPolice ? ' checked' : '') + ' aria-label="Also alert police"><span class="track"></span></label></div>';
        $$('[data-t]', el).forEach(function (c) { c.addEventListener('click', function () { UI.sosType = UI.sosType === c.dataset.t ? null : c.dataset.t; renderSOS(); }); });
        $('#sos-police').addEventListener('change', function () { UI.sosPolice = this.checked; });
        $('#sos-btn').addEventListener('click', function () {
            authenticate('Verify to send an SOS with your exact location' + (UI.sosType ? ' (' + UI.sosType + ')' : '') + '.').then(function () {
                UI.sosSent = { at: hhmm(new Date()), type: UI.sosType, to: recips, police: UI.sosPolice };
                renderSOS(); window.scrollTo({ top: 0, behavior: 'smooth' });
            }).catch(function () {});
        });
    }
    function doCheckin() {
        S.checkin.last = new Date().toISOString(); S.checkin.streak++; save();
    }
    function renderCheckin() {
        var c = S.checkin, el = $('#checkin-panel');
        var doneToday = c.last && c.last.slice(0, 10) === todayKey;
        var trail = [{ t: '08:10', p: 'Home · Kallio' }, { t: '09:45', p: 'University main building' }, { t: '12:20', p: 'Café Regatta' }, { t: '15:40', p: 'Home · Kallio' }];
        el.innerHTML =
            '<div class="panel-head"><div><div class="label-caps">' + (doneToday ? 'Checked in today' : 'Next check-in due') + '</div><div style="font-size:2rem;font-weight:800;letter-spacing:-.03em;line-height:1.1">' + (doneToday ? '✓ ' + hhmm(new Date(c.last)) : 'by ' + c.nextHour + ':00') + '</div></div><span class="badge orange">' + c.streak + ' day streak</span></div>' +
            '<button class="pill block" id="ci-now" type="button"' + (doneToday ? ' disabled' : '') + '>' + I.fp + (doneToday ? 'All good for today' : 'Check in now') + '</button>' +
            '<p class="small" style="margin-top:12px;opacity:.9">If you don\'t confirm within <b>' + c.grace + ' h</b> of the deadline, I\'ll message your emergency contacts with your location history since your last check-in.</p>' +
            '<hr class="divider"><div class="label-caps" style="margin-bottom:8px">Ask me every</div><div class="chips">' + [12, 24, 48].map(function (h) { return '<button class="chip' + (c.every === h ? ' on' : '') + '" data-every="' + h + '" type="button">' + h + ' h</button>'; }).join('') + '</div>' +
            '<div class="label-caps" style="margin:14px 0 8px">Grace period</div><div class="chips">' + [1, 2, 4].map(function (h) { return '<button class="chip' + (c.grace === h ? ' on' : '') + '" data-grace="' + h + '" type="button">' + h + ' h</button>'; }).join('') + '</div>' +
            '<hr class="divider"><div class="row between" style="margin-bottom:10px"><div class="label-caps">Location trail since last check-in</div><span class="badge">' + I.lock + 'Shared only if missed</span></div>' +
            '<ul class="timeline">' + trail.map(function (p) { return '<li><span class="small bold">' + p.t + '</span> <span class="small">' + p.p + '</span></li>'; }).join('') + '</ul>' +
            '<button class="pill outline" id="ci-sim" type="button">Preview a missed check-in</button>';
        $('#ci-now').addEventListener('click', function () {
            authenticate('Daily check-in, just confirming you\'re okay.').then(function () {
                doCheckin(); markTaskByDeco('deco-star'); renderCheckin(); toast('Checked in. Have a good one!');
            }).catch(function () {});
        });
        $$('[data-every]', el).forEach(function (b) { b.addEventListener('click', function () { c.every = +b.dataset.every; save(); renderCheckin(); }); });
        $$('[data-grace]', el).forEach(function (b) { b.addEventListener('click', function () { c.grace = +b.dataset.grace; save(); renderCheckin(); }); });
        $('#ci-sim').addEventListener('click', function () {
            var to = S.contacts.filter(function (x) { return x.on; });
            openSheet('<h2 id="sheet-title">If you miss a check-in</h2><p class="lede">' + c.grace + ' h after the deadline, this goes to ' + esc(to.map(function (x) { return x.name; }).join(', ') || 'your contacts') + ':</p>' +
                '<div class="panel light" style="margin-top:12px"><p class="small"><b>⚠️ Figment safety alert</b><br>' + esc(S.user.name) + ' hasn\'t confirmed their daily check-in (due ' + c.nextHour + ':00). Last confirmed: ' + (c.last ? esc(new Date(c.last).toLocaleString()) : 'yesterday 20:41') + '.<br><br>Location since then:</p>' +
                '<ul class="timeline" style="margin-top:8px">' + trail.map(function (p) { return '<li><span class="small bold">' + p.t + '</span> <span class="small">' + p.p + '</span></li>'; }).join('') + '</ul>' +
                '<div class="map" style="height:110px">' + mapSvg() + '<span class="pin"></span></div></div>' +
                '<div class="sheet-actions"><button class="pill dark" data-x type="button">Got it</button></div>',
                function (root) { $('[data-x]', root).addEventListener('click', closeSheet); });
        });
    }
    function renderDoor() {
        var el = $('#door-panel');
        el.innerHTML =
            '<div class="door-feed"><svg viewBox="0 0 320 200" preserveAspectRatio="xMidYMid slice">' +
            '<rect width="320" height="200" fill="#2a2a2a"/><rect x="0" y="150" width="320" height="50" fill="#1f1f1f"/>' +
            '<rect x="40" y="20" width="90" height="150" fill="#3a3a3a" stroke="#4a4a4a" stroke-width="3"/><circle cx="118" cy="98" r="4" fill="#777"/>' +
            '<rect x="250" y="40" width="40" height="30" fill="#444"/>' +
            '<g opacity=".85"><circle cx="205" cy="70" r="16" fill="#555"/><path d="M180 175 L184 110 Q205 92 226 110 L230 175 Z" fill="#555"/></g>' +
            '</svg>' +
            '<span class="rec"><i></i>LIVE</span><span class="ts">' + hhmm(new Date()) + '</span>' +
            (UI.doorReviewed ? '' : '<span class="box" style="left:53%;top:24%;width:20%;height:66%"><span>Unknown · 3 m 40 s</span></span>') + '</div>' +
            '<div class="row between" style="margin:14px 0 12px"><div class="panel-sub" style="margin:0">Face matching and loitering detection run on this phone.</div>' + localBadge() + '</div>' +
            '<ul class="timeline">' + S.doorEvents.map(function (e, i) {
                var flagged = e.kind === 'bad' && !UI.doorReviewed;
                return '<li class="' + (e.kind === 'bad' && UI.doorReviewed ? 'ok' : e.kind) + '"><div class="row between"><div class="item-title">' + esc(e.title) + '</div><span class="tiny bold muted">' + esc(e.t) + '</span></div><div class="item-sub">' + esc(e.detail) + '</div>' +
                    (flagged ? '<div class="pill-row" style="margin-top:8px"><button class="pill orange" data-door="known" type="button">It\'s someone I know</button><button class="pill brand" data-door="alert" type="button">Alert contacts</button></div>' : '') + '</li>';
            }).join('') + '</ul>' +
            '<hr class="divider"><div class="row between"><div><div class="item-title">Alert me if someone lingers</div><div class="item-sub">Longer than 60 s without knocking</div></div><label class="switch"><input type="checkbox" checked aria-label="Loitering alerts"><span class="track"></span></label></div>';
        $$('[data-door]', el).forEach(function (b) {
            b.addEventListener('click', function () {
                if (b.dataset.door === 'known') { UI.doorReviewed = true; renderDoor(); toast('Marked as known. I\'ll recognise them next time'); }
                else {
                    UI.doorReviewed = true; renderDoor();
                    toast('Clip + time sent to ' + S.contacts.filter(function (c) { return c.on && !c.police; }).map(function (c) { return c.name; }).join(' & '));
                }
            });
        });
    }

    /* =========================================================
       ME
       ========================================================= */
    function renderMe() {
        $('#me-name').textContent = S.user.name;
        // memories
        $('#mem-panel').innerHTML =
            '<div class="row between"><div><div class="item-title">Let Ginger remember things</div><div class="item-sub">Used to find events, products and chat better</div></div><label class="switch"><input type="checkbox" id="mem-sw"' + (S.memoryConsent ? ' checked' : '') + ' aria-label="Memory"><span class="track"></span></label></div>' +
            '<hr class="divider">' +
            (S.memories.length ? '<ul class="list">' + S.memories.map(function (m) {
                return '<li data-id="' + m.id + '"><span class="badge">' + esc(m.tag) + '</span><div class="grow"><div class="item-title" style="font-weight:600">' + esc(m.text) + '</div><div class="item-sub">' + esc(m.date) + '</div></div><button class="icon-btn" data-del type="button" aria-label="Forget this" style="width:28px;height:28px">' + I.x + '</button></li>';
            }).join('') + '</ul>' : '<p class="small muted">Nothing remembered yet.</p>');
        $('#mem-sw').addEventListener('change', function () { S.memoryConsent = this.checked; save(); toast(this.checked ? 'Memory on' : 'Memory off. Nothing new will be saved'); });
        $$('#mem-panel [data-del]').forEach(function (b) {
            b.addEventListener('click', function () { var id = b.closest('li').dataset.id; S.memories = S.memories.filter(function (m) { return m.id !== id; }); save(); renderMe(); toast('Forgotten'); });
        });

        // devices
        $('#dev-panel').innerHTML = '<ul class="list">' + S.devices.map(function (d) {
            return '<li data-id="' + d.id + '"><span class="icon-btn">' + (d.kind === 'health' ? I.watch : I.cam) + '</span><div class="grow"><div class="item-title">' + esc(d.name) + '</div><div class="item-sub">' + (d.on ? 'Last seen ' + esc(d.last) : 'Paused') + ' · ' + (d.local ? 'video stays on device' : 'encrypted sync') + '</div></div>' +
                '<label class="switch"><input type="checkbox"' + (d.on ? ' checked' : '') + ' aria-label="' + esc(d.name) + '"><span class="track"></span></label></li>';
        }).join('') + '</ul>';
        $$('#dev-panel input').forEach(function (inp) {
            inp.addEventListener('change', function () { var id = inp.closest('li').dataset.id; S.devices.forEach(function (d) { if (d.id === id) d.on = inp.checked; }); save(); renderMe(); });
        });

        // contacts
        $('#contacts-panel').innerHTML = '<ul class="list">' + S.contacts.map(function (c) {
            return '<li data-id="' + c.id + '"><div class="grow"><div class="item-title">' + esc(c.name) + '</div><div class="item-sub">' + esc(c.via) + '</div></div>' +
                (c.police ? '' : '<button class="icon-btn" data-del type="button" aria-label="Remove ' + esc(c.name) + '" style="width:28px;height:28px">' + I.x + '</button>') +
                '<label class="switch"><input type="checkbox"' + (c.on ? ' checked' : '') + ' aria-label="Alert ' + esc(c.name) + '"><span class="track"></span></label></li>';
        }).join('') + '</ul>' +
            '<hr class="divider"><form class="stack" id="add-contact"><input class="field" name="n" placeholder="Name, e.g. Emma (friend)" aria-label="Contact name"><div class="search-row"><input class="field" name="v" placeholder="WhatsApp / phone / @handle" aria-label="How to reach them"><button class="pill dark" type="submit">' + I.plus + 'Add</button></div></form>' +
            '<p class="tiny" style="margin-top:10px;opacity:.75">They get SOS alerts and missed check-in alerts. They\'ll receive a one-time invite to confirm.</p>';
        $$('#contacts-panel input[type=checkbox]').forEach(function (inp) {
            inp.addEventListener('change', function () { var id = inp.closest('li').dataset.id; S.contacts.forEach(function (c) { if (c.id === id) c.on = inp.checked; }); save(); });
        });
        $$('#contacts-panel [data-del]').forEach(function (b) {
            b.addEventListener('click', function () { var id = b.closest('li').dataset.id; S.contacts = S.contacts.filter(function (c) { return c.id !== id; }); save(); renderMe(); });
        });
        $('#add-contact').addEventListener('submit', function (e) {
            e.preventDefault(); var n = this.n.value.trim(), v = this.v.value.trim(); if (!n) return;
            S.contacts.splice(S.contacts.length - 1, 0, { id: uid(), name: n, via: v || 'invite pending', on: true });
            save(); renderMe(); toast('Invite sent to ' + n + ' (demo)');
        });

        // social
        $('#social-panel').innerHTML = '<ul class="list">' + S.social.map(function (s) {
            return '<li data-id="' + s.id + '"><div class="grow"><div class="item-title">' + esc(s.name) + '</div><div class="item-sub">' + esc(s.on ? s.handle : 'Not linked') + '</div></div><button class="pill ' + (s.on ? 'outline' : 'dark') + '" type="button">' + (s.on ? 'Unlink' : 'Link') + '</button></li>';
        }).join('') + '</ul><p class="small muted" style="margin-top:10px">Ginger posts finds from <b>@figment.ginger</b> and can call you on linked apps.</p>';
        $$('#social-panel li button').forEach(function (b) {
            b.addEventListener('click', function () {
                var id = b.closest('li').dataset.id;
                S.social.forEach(function (s) { if (s.id === id) { s.on = !s.on; if (s.on && s.handle === 'not linked') s.handle = '@' + S.user.name.toLowerCase(); } });
                save(); renderMe();
            });
        });
    }
    $('#reset-demo').addEventListener('click', function () {
        localStorage.removeItem(KEY); location.hash = '#/home'; location.reload();
    });

    /* ---------------- Boot ---------------- */
    route();
})();
