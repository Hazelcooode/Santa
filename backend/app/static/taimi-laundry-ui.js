/* Sola laundry UI pieces shared by the mobile app and the website.

   - evidence(st)      photos-only evidence for the "Laundry basket" card: each photo
                       with a box around every garment that was recognised. Shown
                       only when the user allowed photos to leave the device;
                       otherwise a locked tile (the user sees only the on-device result).
   - process panel     the agent's live working steps after "If a new piece comes in…";
                       it folds into one line when done.
   - newPieceButton    the button at the bottom of the laundry page.
   - webCards(st)      the website's four cards, in the same order as the app:
                       Laundry basket, Wash plan, Wardrobe runway, Book the laundry room.
   Confidence scores never reach this file's output: they are for the server's router. */
(function () {
    'use strict';

    var SHORT = { dark_tshirt: 'T-shirt', white_tshirt: 'T-shirt', colour_tshirt: 'T-shirt', jeans: 'jeans', socks: 'socks', underwear: 'underwear',
                  towel: 'towel', gym_wear: 'gym wear', knitwear: 'cardigan', joggers: 'joggers', unknown_item: '?' };
    var LOADS = { darks: ['Darks', '40 °C', 'Mixed · 1 h 20'], whites: ['Whites & towels', '60 °C', 'Cotton · 1 h 50'], sport: ['Gym wear', '30 °C', 'Synthetics · 50 min'],
                  colours: ['Colours', '40 °C', 'Mixed · 1 h'], delicates: ['Wool & delicates', '30 °C', 'Wool · 40 min'] };

    function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
    function hhmm(iso) { var d = new Date(iso); return isNaN(d) ? '' : d.toTimeString().slice(0, 5); }
    function api(method, path, body) {
        return fetch(path, { method: method, credentials: 'same-origin', headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined })
            .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error((j.error && j.error.message) || r.statusText); return j; }); });
    }

    var CSS = [
        '.tl-ev{margin-top:14px}',
        '.tl-ev-strip{display:flex;gap:8px;overflow-x:auto;padding-bottom:4px;scroll-snap-type:x mandatory}',
        '.tl-shot{position:relative;flex:0 0 auto;width:min(46%,180px);aspect-ratio:1;border-radius:12px;overflow:hidden;background:#e9e4dc;border:0;padding:0;cursor:zoom-in;scroll-snap-align:start}',
        '.tl-shot.big{width:100%;cursor:default;border-radius:14px}',
        '.tl-shot img{width:100%;height:100%;object-fit:cover;display:block}',
        '.tl-box{position:absolute;border:2px solid rgba(255,255,255,.95);border-radius:6px;box-shadow:0 0 0 1px rgba(0,0,0,.25)}',
        '.tl-box.new{border-color:#e8743b}',
        '.tl-box.agent{border-style:dashed}',
        '.tl-tag{position:absolute;background:rgba(255,255,255,.95);color:#222;font:600 9px/1.3 system-ui,sans-serif;font-style:normal;padding:1px 5px;border-radius:5px;white-space:nowrap;box-shadow:0 1px 3px rgba(0,0,0,.25)}',
        '.tl-tag.new{background:#e8743b;color:#fff}',
        '.tl-shot.big .tl-tag{font-size:12px;padding:2px 7px}',
        '.tl-shot b{position:absolute;right:6px;bottom:6px;background:rgba(0,0,0,.55);color:#fff;font:600 9px/1 system-ui,sans-serif;padding:3px 6px;border-radius:6px}',
        '.tl-shot.big b{font-size:11px;padding:4px 8px}',
        '.tl-lock{display:flex;align-items:center;gap:12px;padding:12px;border-radius:12px;background:rgba(255,255,255,.6);border:1px dashed rgba(0,0,0,.15)}',
        '.tl-lock svg{flex:0 0 auto;opacity:.6;width:22px!important;height:22px!important}',
        '.tl-lock span{flex:1;font-size:12px;line-height:1.4;opacity:.8}',
        '.tl-mini{border:0;background:none;padding:0;font-size:11px;text-decoration:underline;opacity:.65;cursor:pointer;color:inherit}',
        '.tl-pill{border:0;border-radius:999px;padding:8px 13px;font-size:12px;font-weight:600;background:#2b2b2b;color:#fff;cursor:pointer;white-space:nowrap}',
        '.tl-ev-foot{display:flex;justify-content:space-between;align-items:center;margin-top:6px;font-size:10px;opacity:.75;gap:8px}',
        '.tl-key{display:inline-flex;align-items:center;gap:4px;margin-right:8px}.tl-key i{width:12px;height:9px;border:2px solid #fff;box-shadow:0 0 0 1px rgba(0,0,0,.3);border-radius:3px}.tl-key i.n{border-color:#e8743b}.tl-key i.a{border-style:dashed;border-color:#555}',
        /* process panel */
        '.tl-proc{border-radius:16px;background:#22252a;color:#f3f3ef;padding:14px 16px;margin:0 0 16px;box-shadow:0 8px 30px rgba(0,0,0,.12)}',
        '.tl-proc[hidden]{display:none}',
        '.tl-proc summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:10px;font-size:13px;font-weight:600}',
        '.tl-proc summary::-webkit-details-marker{display:none}',
        '.tl-proc summary .tl-chev{margin-left:auto;opacity:.6;transition:transform .2s}',
        '.tl-proc[open] summary .tl-chev{transform:rotate(180deg)}',
        '.tl-proc ol{list-style:none;margin:12px 0 2px;padding:0;display:grid;gap:8px}',
        '.tl-proc li{display:flex;gap:10px;align-items:flex-start;font-size:12px;line-height:1.45;opacity:.92;animation:tl-in .3s ease}',
        '.tl-proc li time{opacity:.5;font-variant-numeric:tabular-nums;min-width:52px}',
        '.tl-dot{width:8px;height:8px;border-radius:50%;background:#7bd389;margin-top:5px;flex:0 0 auto}',
        '.tl-proc li.now .tl-dot{background:#f0b35b;animation:tl-pulse 1s infinite}',
        '.tl-proc li.err .tl-dot{background:#ef6b5b}',
        '.tl-spin{width:14px;height:14px;border-radius:50%;border:2px solid rgba(255,255,255,.25);border-top-color:#fff;animation:tl-rot .8s linear infinite}',
        '.tl-ok{width:16px;height:16px;border-radius:50%;background:#7bd389;color:#22252a;display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:800}',
        '@keyframes tl-rot{to{transform:rotate(360deg)}}@keyframes tl-pulse{50%{opacity:.35}}@keyframes tl-in{from{opacity:0;transform:translateY(4px)}}',
        /* bottom button */
        '.tl-next{margin:22px 0 8px;text-align:center}',
        '.tl-next button.tl-go{width:100%;border:0;border-radius:16px;padding:16px;font-size:15px;font-weight:700;background:#e8743b;color:#fff;cursor:pointer;box-shadow:0 6px 18px rgba(232,116,59,.3)}',
        '.tl-next button.tl-go:disabled{opacity:.5;cursor:default;box-shadow:none}',
        '.tl-next .tl-mini{margin-top:10px}',
        '.tl-flash{animation:tl-flash 1.4s ease}@keyframes tl-flash{0%{box-shadow:0 0 0 0 rgba(232,116,59,.7)}100%{box-shadow:0 0 0 14px rgba(232,116,59,0)}}',
        /* lightbox */
        '.tl-lb{position:fixed;inset:0;background:rgba(20,20,22,.82);z-index:1000;display:flex;align-items:center;justify-content:center;padding:18px}',
        '.tl-lb .tl-shot{max-width:min(92vw,620px)}',
        /* notes inside the original cards */
        '.tl-note{display:flex;gap:8px;align-items:flex-start;font-size:12px;line-height:1.45;margin-top:10px}',
        '.tl-note b{font-weight:700}',
        '#wardrobe-panel>.tl-note{margin:0 0 10px}',
        '.tl-note.urgent{color:#b4532a}',
        /* website cards */
        '.tl-web{display:grid;gap:18px;grid-template-columns:minmax(0,1fr);min-width:0}',
        '.tl-web .tl-card h2{font-size:17px;margin-bottom:4px}',
        '.tl-web .tl-sub{font-size:11px;color:var(--muted,#777);margin-bottom:14px}',
        '.tl-meter{height:8px;border-radius:9px;background:rgba(0,0,0,.07);overflow:hidden}.tl-meter i{display:block;height:100%;background:#8fb57f;border-radius:9px}.tl-meter i.warn{background:#e2a64b}.tl-meter i.bad{background:#e0663f}',
        '.tl-chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}.tl-chips span{font-size:11px;background:#f3f1ea;border-radius:20px;padding:5px 10px}',
        '.tl-rows{list-style:none;padding:0;margin:0}.tl-rows li{display:flex;align-items:center;gap:12px;padding:11px 0;border-top:1px solid var(--line,#eee);font-size:12px}.tl-rows li:first-child{border-top:0}',
        '.tl-rows .n{width:24px;height:24px;border-radius:8px;background:#f0edf6;display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:11px}',
        '.tl-rows .grow{flex:1}.tl-rows small{display:block;color:var(--muted,#777);font-size:10px;margin-top:3px}',
        '.tl-grid{display:grid;grid-template-columns:52px repeat(3,1fr);gap:6px;font-size:11px;align-items:center}',
        '.tl-grid .h{text-align:center;font-weight:600;font-size:10px}.tl-grid .t{color:var(--muted,#777);font-size:10px}',
        '.tl-slot{border:0;border-radius:8px;padding:8px 0;font-size:10px;font-weight:600;text-align:center}',
        '.tl-slot.free{background:#e7eedf;cursor:pointer}.tl-slot.best{background:#cfe3c0;cursor:pointer}.tl-slot.sel{background:#353b35;color:#fff;cursor:pointer}',
        '.tl-slot.taken{background:repeating-linear-gradient(45deg,rgba(0,0,0,.08) 0 3px,transparent 3px 6px);color:#999}.tl-slot.busy{background:rgba(0,0,0,.06);color:#999}.tl-slot.mine{background:#ece8f7;color:#594972}.tl-slot.past{opacity:.35;background:#f3f3ef}',
        '.tl-web-cols{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);gap:18px;align-items:start}@media(max-width:900px){.tl-web-cols{grid-template-columns:minmax(0,1fr)}}',
        '.tl-web .tl-shot{width:150px}'
    ].join('\n');
    function injectCss() {
        if (document.getElementById('tl-css')) return;
        var st = document.createElement('style'); st.id = 'tl-css'; st.textContent = CSS; document.head.appendChild(st);
    }

    /* --------------------------------------------------------------- evidence */
    var LOCK = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><rect x="4" y="10" width="16" height="11" rx="2.5"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>';
    function boxesHtml(f) {
        var fresh = {};
        (f.added || []).forEach(function (a) { fresh[a.label + '/' + a.colour] = (fresh[a.label + '/' + a.colour] || 0) + a.n; });
        var boxes = (f.boxes || []).map(function (b) {
            var k = b.label + '/' + b.colour, isNew = f.trigger !== 'history' && fresh[k] > 0;
            if (isNew) fresh[k]--;
            return { b: b, isNew: isNew };
        });
        // tags sit inside each box's top-left corner; push a tag down when it would cover another
        var placed = [], tags = boxes.map(function (x) {
            var bb = x.b.bbox, tx = bb[0] * 100 + 1, ty = bb[1] * 100 + 1;
            while (placed.some(function (p) { return Math.abs(p[0] - tx) < 26 && Math.abs(p[1] - ty) < 8; })) ty += 8;
            placed.push([tx, ty]);
            return '<i class="tl-tag' + (x.isNew ? ' new' : '') + '" style="left:' + tx + '%;top:' + Math.min(92, ty) + '%">' + esc(SHORT[x.b.label] || x.b.label) + '</i>';
        });
        return boxes.map(function (x) {
            var bb = x.b.bbox;
            return '<span class="tl-box' + (x.isNew ? ' new' : '') + (x.b.by === 'agent' ? ' agent' : '') + '" style="left:' + (bb[0] * 100) + '%;top:' + (bb[1] * 100) +
                '%;width:' + (bb[2] * 100) + '%;height:' + (bb[3] * 100) + '%"></span>';
        }).join('') + tags.join('');
    }
    function shot(f, big) {
        return '<' + (big ? 'div' : 'button type="button"') + ' class="tl-shot' + (big ? ' big' : '') + '" data-frame="' + esc(f.frameId) + '" aria-label="Basket photo ' + esc(hhmm(f.capturedAt)) + '">' +
            '<img src="' + esc(f.image) + '" alt="" loading="lazy">' + boxesHtml(f) + '<b>' + esc(hhmm(f.capturedAt)) + '</b></' + (big ? 'div' : 'button') + '>';
    }
    function evidence(st) {
        var cam = st && st.camera;
        if (!cam || !cam.frames || !cam.frames.length) return '';
        if (!cam.imagesAllowed) {
            return '<div class="tl-ev"><div class="tl-lock">' + LOCK + '<span>Photos stay on your device.</span>' +
                '<button class="tl-pill" type="button" data-tl="allow">Show photos</button></div></div>';
        }
        var shots = cam.frames.filter(function (f) { return f.image && f.visible; }).slice().reverse();
        if (!shots.length) return '<div class="tl-ev"><div class="tl-lock">' + LOCK + '<span>Sending photos…</span></div></div>';
        var agent = shots.some(function (f) { return f.source === 'agent'; });
        return '<div class="tl-ev"><div class="tl-ev-strip">' + shots.slice(0, 6).map(function (f) { return shot(f); }).join('') + '</div>' +
            '<div class="tl-ev-foot"><span><span class="tl-key"><i class="n"></i>new</span>' + (agent ? '<span class="tl-key"><i class="a"></i>agent</span>' : '') + '</span>' +
            '<button class="tl-mini" type="button" data-tl="revoke">Stop sharing photos</button></div></div>';
    }

    /* Wire evidence buttons inside `root` (consent + lightbox). */
    function wire(root) {
        if (!root || root._tlWired) return;
        root._tlWired = true;
        root.addEventListener('click', function (e) {
            var b = e.target.closest('[data-tl],[data-frame]');
            if (!b || !root.contains(b)) return;
            var a = b.getAttribute('data-tl');
            if (a === 'allow') {
                if (!window.confirm('Let basket photos leave this device?\n\nTaimi will show them here as evidence, and when the camera is unsure, Sola\'s agent will look at the photo. You can stop any time; shared photos are then deleted.')) return;
                b.disabled = true;
                window.TaimiEdge.setImageConsent(true);
            } else if (a === 'revoke') {
                window.TaimiEdge.setImageConsent(false);
            } else if (b.hasAttribute('data-frame') && b.tagName === 'BUTTON') {
                var f = (last && last.camera.frames || []).filter(function (x) { return x.frameId === b.getAttribute('data-frame'); })[0];
                if (!f) return;
                var lb = document.createElement('div');
                lb.className = 'tl-lb'; lb.innerHTML = shot(f, true);
                lb.addEventListener('click', function () { lb.remove(); });
                document.body.appendChild(lb);
            }
        });
    }

    /* --------------------------------------------------------- card snippets */
    function sug(st, pred) { return ((st && st.suggestions) || []).filter(pred); }
    function headline(st) { return st && st.headline ? st.headline.text : ''; }
    function careNotes(st) {
        return sug(st, function (s) { return s.kind === 'care' || s.kind === 'check'; })
            .map(function (s) { return '<div class="tl-note"><span>•</span><span><b>' + esc(s.title) + '.</b> ' + esc(s.detail) + '</span></div>'; }).join('');
    }
    function runwayNote(st) {
        var s = sug(st, function (x) { return x.kind === 'runway'; })[0];
        return s ? '<div class="tl-note' + (s.tone === 'urgent' ? ' urgent' : '') + '"><b>' + esc(s.title) + '.</b></div>' : '';
    }
    function slotNote(st) {
        var s = sug(st, function (x) { return x.kind === 'slot'; })[0];
        return s ? '<div class="tl-note"><span>★</span><span><b>' + esc(s.title.replace(/^Book /, '')) + '</b> · free for you and the room, before you run out.</span></div>' : '';
    }

    /* ---------------------------------------------------------- process panel */
    var last = null, procEl = null, steps = [], running = false, summaryText = '', onStateCbs = [];
    function procRender() {
        if (!procEl) return;
        if (!steps.length) { procEl.hidden = true; return; }
        procEl.hidden = false;
        var head = running ? '<span class="tl-spin"></span><span>Sola is working…</span>' : '<span class="tl-ok">✓</span><span>' + esc(summaryText || 'Plan updated') + '</span>';
        procEl.innerHTML = '<summary>' + head + '<span class="tl-chev">▾</span></summary><ol>' + steps.map(function (s, i) {
            var now = running && i === steps.length - 1;
            return '<li class="' + (now ? 'now' : '') + (s.err ? ' err' : '') + '"><span class="tl-dot"></span><time>' + new Date(s.at).toTimeString().slice(0, 8) + '</time><span>' + esc(s.text) + '</span></li>';
        }).join('') + '</ol>';
    }
    function procStart() { steps = []; running = true; summaryText = ''; if (procEl) procEl.open = true; procRender(); }
    function procStep(text, err) {
        var prev = steps[steps.length - 1];
        if (prev && prev.text === text) return;
        // collapse the model's sub-steps for the same photo into one line that updates
        if (prev && prev.group && prev.group === groupOf(text)) { prev.text = text; prev.at = Date.now(); }
        else steps.push({ text: text, at: Date.now(), err: !!err, group: groupOf(text) });
        procRender();
    }
    function groupOf(t) { var m = /^Photo (\d+)\//.exec(t); return m ? 'p' + m[1] : null; }
    function procDone(text, err) {
        running = false; summaryText = text;
        if (err) procStep(text, true);
        procRender();
        setTimeout(function () { if (procEl && !running) procEl.open = false; }, err ? 6000 : 1600);   // fold when done
    }

    /* ------------------------------------------------------------- lifecycle */
    var started = false;
    var nextMount = null;
    function emitState(st) {
        last = st;
        if (nextMount && !running && document.body.contains(nextMount.el)) newPieceButton(nextMount.el, nextMount.opts);
        onStateCbs.forEach(function (fn) { try { fn(st); } catch (e) { console.error(e); } }); }
    function start(onState) {
        injectCss();
        if (onState && onStateCbs.indexOf(onState) === -1) onStateCbs.push(onState);
        if (last && onState) onState(last);
        if (started || !window.TaimiEdge) return;
        started = true;
        var E = window.TaimiEdge;
        E.on(function (type, d) {
            if (type === 'state') emitState(d);
            else if (type === 'busy' && d.kind === 'history') procStart();
            else if (type === 'status') {
                if (d.step === 'done') { if (running) procDone(d.text); }
                else if (running) procStep(d.text);
            }
        });
        E.init().catch(function (e) { if (running) procDone('Could not reach the basket camera: ' + e.message, true); });
    }

    function scrollTop(el) {
        var y = el ? el.getBoundingClientRect().top + window.scrollY - 70 : 0;
        window.scrollTo({ top: Math.max(0, y), behavior: 'smooth' });
    }

    /* The process panel element (place it near the top of the laundry page). */
    function mountProcess(el) {
        injectCss();
        if (!el) return;
        if (el.tagName !== 'DETAILS') { var d = document.createElement('details'); el.replaceWith(d); d.id = el.id; el = d; }
        el.className = 'tl-proc';
        el.open = running;
        procEl = el;
        procRender();
        return el;
    }

    /* The bottom button. */
    function newPieceButton(el, opts) {
        injectCss();
        if (!el) return;
        nextMount = { el: el, opts: opts };
        var E = window.TaimiEdge, left = E && E.hasNext ? E.hasNext() : true;
        el.className = 'tl-next';
        el.innerHTML = '<button class="tl-go" type="button"' + (left ? '' : ' disabled') + '>' + (left ? 'If a new piece comes in…' : 'No more photos in this demo') + '</button>' +
            '<div><button class="tl-mini" type="button" data-a="reset">Reset the camera demo</button></div>';
        el.querySelector('.tl-go').addEventListener('click', function () {
            var btn = this;
            if (!E || E.isBusy()) return;
            btn.disabled = true;
            scrollTop(opts && opts.top);
            procStart();
            E.addPiece().then(function (st) {
                var f = st.camera.frames[st.camera.frames.length - 1] || {};
                procDone(f.added && f.added.length ? 'New in the basket: ' + f.added.map(function (a) { return a.name; }).join(', ') : 'Plan updated');
                if (opts && opts.flash) opts.flash.forEach(function (sel) { var n = document.querySelector(sel); if (n) { n.classList.remove('tl-flash'); void n.offsetWidth; n.classList.add('tl-flash'); } });
            }, function (e) { procDone(e.message, true); }).then(function () { newPieceButton(el, opts); });
        });
        el.querySelector('[data-a="reset"]').addEventListener('click', function () {
            if (!E || E.isBusy()) return;
            procStart();
            E.reset().then(function () { procDone('Camera demo reset'); newPieceButton(el, opts); }, function (e) { procDone(e.message, true); });
        });
    }

    /* ------------------------------------------------------------ website */
    function dayName(d) { var x = new Date(); x.setDate(x.getDate() + d); return d === 0 ? 'Today' : d === 1 ? 'Tomorrow' : x.toLocaleDateString(undefined, { weekday: 'short' }); }
    function webCards(st) {
        var pct = st.fullPct, cls = pct > 75 ? 'bad' : pct > 50 ? 'warn' : '';
        var basket = '<section class="panel roomy tl-card" id="tl-basket"><div class="section-heading"><h2>Laundry basket</h2><span class="pill">ON-DEVICE</span></div>' +
            '<div class="tl-sub">Seen ' + esc(hhmm(st.basketSeenAt)) + ' · ' + st.basketCount + ' items</div>' +
            '<div style="display:flex;justify-content:space-between;font-size:11px;font-weight:600;margin-bottom:6px"><span>' + pct + '% full</span><span>' + (pct > 75 ? 'Time to wash' : 'Plenty of room') + '</span></div>' +
            '<div class="tl-meter"><i class="' + cls + '" style="width:' + pct + '%"></i></div>' +
            '<div class="tl-chips">' + st.basket.map(function (b) { return '<span>' + b.n + ' × ' + esc(b.name) + '</span>'; }).join('') + '</div>' + evidence(st) + '</section>';
        var plan = '<section class="panel roomy tl-card" id="tl-plan"><div class="section-heading"><h2>Wash plan</h2><span class="pill warm">PLAN</span></div>' +
            '<div class="tl-sub">' + esc(headline(st)) + '</div><ul class="tl-rows">' + st.loads.map(function (l, i) {
                return '<li><span class="n">' + (i + 1) + '</span><span class="grow"><strong>' + esc(l.t) + ' · ' + esc(l.temp) + '</strong><small>' +
                    esc(l.items.map(function (b) { return b.n + ' ' + b.name.toLowerCase(); }).join(', ')) + ' · ' + esc(l.prog) + '</small></span></li>';
            }).join('') + '</ul>' + careNotes(st) + '</section>';
        var runway = '<section class="panel roomy tl-card" id="tl-runway"><div class="section-heading"><h2>Wardrobe runway</h2><span class="pill">DAYS LEFT</span></div>' + runwayNote(st) +
            '<ul class="tl-rows" style="margin-top:8px">' + st.wardrobe.map(function (w) {
                var r = w.runway, c = r <= 1 ? 'bad' : r <= 3 ? 'warn' : '';
                return '<li style="display:block"><div style="display:flex;justify-content:space-between"><strong>' + esc(w.cat) + '</strong><span style="font-weight:600' + (r <= 1 ? ';color:#b4532a' : '') + '">' +
                    (w.clean === 0 ? 'Out now' : r >= 99 ? '—' : r + (r === 1 ? ' day' : ' days')) + '</span></div><div style="display:flex;gap:10px;align-items:center;margin-top:6px"><div class="tl-meter" style="flex:1"><i class="' + c +
                    '" style="width:' + Math.round(w.clean / Math.max(1, w.total) * 100) + '%"></i></div><small style="width:70px;text-align:right">' + w.clean + ' / ' + w.total + ' clean</small></div></li>';
            }).join('') + '</ul></section>';
        var grid = '<div></div>' + [0, 1, 2].map(function (d) { return '<div class="h">' + dayName(d) + '</div>'; }).join('') +
            st.slotTimes.map(function (t, si) {
                return '<div class="t">' + (t < 10 ? '0' : '') + t + ':00</div>' + [0, 1, 2].map(function (d) {
                    var s = st.slots.filter(function (x) { return x.day === d && x.slot === si; })[0] || {}, k = s.key;
                    if (s.status === 'free') {
                        var c = webSel === k ? 'sel' : k === st.best ? 'best' : 'free';
                        return '<button class="tl-slot ' + c + '" type="button" data-slot="' + k + '">' + (k === st.best && webSel !== k ? '★ Best' : 'Free') + '</button>';
                    }
                    return '<span class="tl-slot ' + (s.status || 'taken') + '">' + ({ taken: 'Taken', busy: 'Busy', mine: 'Yours', past: '—' }[s.status] || '') + '</span>';
                }).join('');
            }).join('');
        var bookings = (st.bookings || []).map(function (b) { return '<li><span class="grow"><strong>' + esc(b.label) + '</strong><small>' + esc(b.machine || 'Room B') + ' · reminder 15 min before</small></span><button class="text-button" type="button" data-cancel="' + esc(b.id) + '">Cancel</button></li>'; }).join('');
        var room = '<section class="panel roomy tl-card" id="tl-room"><div class="section-heading"><h2>Book the laundry room</h2><span class="pill">ROOM FREE + YOU FREE</span></div>' +
            '<div class="tl-sub">' + esc(st.room) + '</div>' + slotNote(st) + '<div class="tl-grid" style="margin-top:12px">' + grid + '</div>' +
            (bookings ? '<ul class="tl-rows" style="margin-top:12px">' + bookings + '</ul>' : '') +
            '<button class="button dark full" type="button" data-book style="margin-top:16px"' + (webSel ? '' : ' disabled') + '>' + (webSel ? 'Reserve this slot' : 'Pick a free slot') + '</button></section>';
        return '<div class="tl-web"><details id="tl-proc" class="tl-proc" hidden></details><div class="tl-web-cols">' + basket + plan + runway + room + '</div>' +
            '<div id="tl-next"></div></div>';
    }
    var webSel = null, webEl = null;
    function renderWeb() {
        if (!webEl || !last || !document.body.contains(webEl)) return;
        webEl.innerHTML = webCards(last);
        mountProcess(webEl.querySelector('#tl-proc'));
        newPieceButton(webEl.querySelector('#tl-next'), { top: webEl, flash: ['#tl-basket', '#tl-plan', '#tl-runway', '#tl-room'] });
    }
    function mountWeb(el) {
        injectCss();
        webEl = el;
        el.innerHTML = '<div class="tl-sub">Loading your basket camera…</div>';
        wire(el);
        if (!el._tlWeb) {
            el._tlWeb = true;
            el.addEventListener('click', function (e) {
                var s = e.target.closest('[data-slot]'), bk = e.target.closest('[data-book]'), c = e.target.closest('[data-cancel]');
                if (s) { webSel = webSel === s.dataset.slot ? null : s.dataset.slot; renderWeb(); }
                else if (bk && webSel) api('POST', '/api/v1/laundry/bookings', { key: webSel }).then(function () { webSel = null; return api('GET', '/api/v1/laundry'); }).then(emitState, function (er) { window.alert(er.message); });
                else if (c) api('DELETE', '/api/v1/laundry/bookings/' + encodeURIComponent(c.dataset.cancel)).then(function () { return api('GET', '/api/v1/laundry'); }).then(emitState);
            });
        }
        start(renderWeb);
    }

    window.TaimiLaundryUI = {
        start: start, evidence: evidence, wire: wire, mountProcess: mountProcess, newPieceButton: newPieceButton, mountWeb: mountWeb,
        headline: headline, careNotes: careNotes, runwayNote: runwayNote, slotNote: slotNote,
        isRunning: function () { return running; }, state: function () { return last; }, LOADS: LOADS
    };
})();
