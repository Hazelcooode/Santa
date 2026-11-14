/* Sola edge: the laundry-basket camera and the models that run next to it.

   This file plays the part of the camera hub at home. Everything here runs on
   the user's own machine (in the demo, in this browser tab):
     1. camera   - "captures" real photos of the basket (served from
                   /laundry-frames/; in a real hub these come off the sensor);
     2. models   - two small open vision models, run locally with ONNX Runtime
                   (WebAssembly) through transformers.js:
                     * OWL-ViT B/32 finds where each garment is, even when
                       garments overlap (zero-shot object detection);
                     * CLIP B/32 names each found region (t-shirt, cardigan,
                       towel, joggers, jeans, ...);
                   plus a pixel rule for the colour family (white/dark/colour);
     3. summary  - only a formatted summary (labels, colours, confidence, boxes,
                   an image fingerprint) is sent to the server. Pixels never are.
   Images leave this device only after the user grants the
   "camera_images_off_device" consent, and only as the exact bytes the models
   analysed (the server checks them against the fingerprint).

   The UI never reads images from here: it shows them only from the server, so
   what the app/web can display is exactly what has left the device. */
(function () {
    'use strict';

    var CONSENT = 'camera_images_off_device';
    var RUNTIME = '/vendor/transformers.min.js';
    var DETECTOR = 'Xenova/owlvit-base-patch32', NAMER = 'Xenova/clip-vit-base-patch32';
    var MODEL_INFO = { id: 'owlvit-b32-clip-b32', version: 'q8', runtime: 'on-device (browser, WASM)', params: 304000000 };

    // The basket's photos, oldest first. Frame 0 is the empty basket (the hub's calibration shot).
    var HISTORY = [
        { src: '/laundry-frames/frame-0.jpg', hoursAgo: 30 },
        { src: '/laundry-frames/frame-1.jpg', hoursAgo: 22 },
        { src: '/laundry-frames/frame-2.jpg', hoursAgo: 9 },
        { src: '/laundry-frames/frame-3.jpg', hoursAgo: 2.5 }
    ];
    // "If a new piece comes in…": the next photo(s) the camera will take.
    var NEXT = ['/laundry-frames/frame-4.jpg'];

    /* ------------------------------------------------------- vision models */
    // OWL-ViT proposes garment regions; these prompts only steer *where* to look.
    var REGION_PROMPTS = ['a piece of clothing', 'a t-shirt', 'a sweater', 'a towel', 'trousers', 'jeans', 'a denim fabric', 'socks'];
    var REGION_MIN_SCORE = 0.05, MAX_REGIONS = 6;
    // CLIP names each region: prompt ensemble per garment class.
    var TEMPLATES = ['a photo of a {}.', 'a photo of a {} in a laundry basket.', 'a close-up photo of a crumpled {}.', 'a {} lying in a hamper.',
                     'a top-down photo of a {} in a basket of dirty laundry.'];
    var NAMES = {
        tshirt: ['t-shirt', 'cotton t-shirt'], knitwear: ['knitted cardigan', 'wool cardigan with buttons', 'knit sweater'],
        towel: ['towel', 'terry cloth towel'], joggers: ['pair of sweatpants', 'pair of jogging trousers', 'pair of track pants'],
        jeans: ['pair of jeans', 'denim jeans'], socks: ['pair of socks'], underwear: ['pair of underwear']
    };
    var MIN_NAME_CONFIDENCE = 0.25;

    var models = null, modelsPromise = null;
    function loadModels(progress) {
        if (modelsPromise) return modelsPromise;
        modelsPromise = import(RUNTIME).then(function (T) {
            T.env.allowRemoteModels = false; T.env.allowLocalModels = true;   // weights come from this server only
            T.env.localModelPath = '/vendor/models/';
            T.env.backends.onnx.wasm.wasmPaths = '/vendor/';
            if (progress) progress('Loading the on-device models…');
            return paint().then(function () { return Promise.all([
                T.pipeline('zero-shot-object-detection', DETECTOR, { dtype: 'q8', device: 'wasm' }),
                T.AutoTokenizer.from_pretrained(NAMER), T.AutoProcessor.from_pretrained(NAMER),
                T.CLIPTextModelWithProjection.from_pretrained(NAMER, { dtype: 'q8', device: 'wasm' }),
                T.CLIPVisionModelWithProjection.from_pretrained(NAMER, { dtype: 'q8', device: 'wasm' })
            ]); }).then(function (r) {
                var m = { T: T, detect: r[0], tok: r[1], proc: r[2], text: r[3], vision: r[4], classes: Object.keys(NAMES), protos: [] };
                return m.classes.reduce(function (p, k) {
                    return p.then(function () {
                        var texts = [];
                        NAMES[k].forEach(function (n) { TEMPLATES.forEach(function (t) { texts.push(t.replace('{}', n)); }); });
                        return m.text(m.tok(texts, { padding: true, truncation: true })).then(function (o) {
                            var E = rows(o.text_embeds), mean = E[0].map(function (_, j) { return E.reduce(function (s, e) { return s + e[j]; }, 0) / E.length; });
                            m.protos.push(unit(mean));
                        });
                    });
                }, Promise.resolve()).then(function () { models = m; return m; });
            });
        });
        modelsPromise.catch(function () { modelsPromise = null; });
        return modelsPromise;
    }
    // let the page paint the latest step before the next heavy model call
    function paint(v) { return new Promise(function (ok) { requestAnimationFrame(function () { setTimeout(function () { ok(v); }, 0); }); }); }
    function unit(v) { var s = Math.hypot.apply(null, v) || 1; return v.map(function (x) { return x / s; }); }
    function rows(t) { var d = t.dims[1], a = t.data, out = []; for (var i = 0; i < a.length / d; i++) out.push(unit(Array.from(a.slice(i * d, (i + 1) * d)))); return out; }
    function iou(a, b) {
        var x0 = Math.max(a[0], b[0]), y0 = Math.max(a[1], b[1]), x1 = Math.min(a[2], b[2]), y1 = Math.min(a[3], b[3]);
        var inter = Math.max(0, x1 - x0) * Math.max(0, y1 - y0), area = function (r) { return (r[2] - r[0]) * (r[3] - r[1]); };
        return inter / (area(a) + area(b) - inter || 1);
    }
    function area(b) { return (b[2] - b[0]) * (b[3] - b[1]); }
    function inside(small, big) {   // share of `small` that lies inside `big`
        var x0 = Math.max(small[0], big[0]), y0 = Math.max(small[1], big[1]), x1 = Math.min(small[2], big[2]), y1 = Math.min(small[3], big[3]);
        return Math.max(0, x1 - x0) * Math.max(0, y1 - y0) / ((small[2] - small[0]) * (small[3] - small[1]) || 1);
    }

    function loadImage(url) { var im = new Image(); im.src = url; return im.decode().then(function () { return im; }); }
    function squareCrop(im, b, f, size, mirror) {
        var cx = (b[0] + b[2]) / 2, cy = (b[1] + b[3]) / 2, s = Math.max(b[2] - b[0], b[3] - b[1]) * f, c = document.createElement('canvas');
        c.width = c.height = size;
        var ctx = c.getContext('2d');
        if (mirror) { ctx.translate(size, 0); ctx.scale(-1, 1); }
        ctx.drawImage(im, cx - s / 2, cy - s / 2, s, s, 0, 0, size, size);
        return c;
    }
    function colourOf(im, b) {
        var w = b[2] - b[0], h = b[3] - b[1], c = document.createElement('canvas'), N = 32;   // central half of the region
        c.width = c.height = N;
        var ctx = c.getContext('2d');
        ctx.drawImage(im, b[0] + w * 0.25, b[1] + h * 0.25, w * 0.5, h * 0.5, 0, 0, N, N);
        var d = ctx.getImageData(0, 0, N, N).data, Ys = [], Ss = [];
        for (var i = 0; i < d.length; i += 4) {
            var mx = Math.max(d[i], d[i + 1], d[i + 2]), mn = Math.min(d[i], d[i + 1], d[i + 2]);
            Ys.push(0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]); Ss.push(mx ? (mx - mn) / mx : 0);
        }
        var med = function (a) { a.sort(function (x, y) { return x - y; }); return a[a.length >> 1]; }, Y = med(Ys), S = med(Ss);
        if (S < 0.15) return Y >= 120 ? 'white' : 'dark';      // whites, light greys / charcoal, black
        return Y < 75 ? 'dark' : 'colour';                       // navy, dark denim / beige, red, ...
    }
    function labelFor(cls, colour) {
        if (cls === 'tshirt') return colour === 'white' ? 'white_tshirt' : colour === 'dark' ? 'dark_tshirt' : 'colour_tshirt';
        return cls;   // knitwear, towel, joggers, jeans, socks, underwear
    }
    function r3(v) { return Math.round(v * 1000) / 1000; }

    // CLIP: embed several views of each region (centre crops to the whole box, mirrored), average, compare with the class prompts.
    var VIEWS = [[0.6, false], [0.6, true], [0.85, false], [0.85, true], [1.0, false], [1.0, true]];
    async function nameRegions(m, im, regions) {
        var found = [];
        for (var i = 0; i < regions.length; i++) {
            var r = regions[i], sum = null;
            for (var view of VIEWS) {
                var raw = await m.T.RawImage.fromURL(squareCrop(im, r.box, view[0], 224, view[1]).toDataURL('image/jpeg', 0.92));
                var pv = await m.proc(raw), out = await m.vision({ pixel_values: pv.pixel_values }), v = rows(out.image_embeds)[0];
                sum = sum ? sum.map(function (x, j) { return x + v[j]; }) : v;
            }
            var e = unit(sum), logits = m.protos.map(function (p) { return 100 * p.reduce(function (s, x, j) { return s + x * e[j]; }, 0); });
            var mx = Math.max.apply(null, logits), ex = logits.map(function (l) { return Math.exp(l - mx); }), Z = ex.reduce(function (a, b) { return a + b; }, 0);
            var probs = ex.map(function (x) { return x / Z; }), best = probs.indexOf(Math.max.apply(null, probs));
            found.push({ box: r.box, regionScore: r.score, cls: m.classes[best], conf: probs[best], colour: colourOf(im, r.box),
                         top: m.classes.map(function (k, j) { return [k, r3(probs[j])]; }).sort(function (a, b) { return b[1] - a[1]; }).slice(0, 3) });
        }
        return found;
    }

    /* Run both models on one photo. Returns derived data only (no pixels). */
    function analyse(url, progress) {
        var t0 = performance.now(), say = progress || function () {};
        return Promise.all([loadModels(say), loadImage(url)]).then(function (res) {
            var m = res[0], im = res[1], W = im.naturalWidth, H = im.naturalHeight;
            say('Finding garments (OWL-ViT)…');
            return paint().then(function () { return m.detect(url, REGION_PROMPTS, { threshold: REGION_MIN_SCORE, topk: 200 }); }).then(function (dets) {
                var byBox = {};
                dets.forEach(function (d) {
                    var b = [d.box.xmin, d.box.ymin, d.box.xmax, d.box.ymax].map(function (v) { return Math.round(v); });
                    var key = b.join(','), area = (b[2] - b[0]) * (b[3] - b[1]) / (W * H);
                    if (area < 0.015 || area > 0.8) return;   // specks, or the whole basket
                    if (!byBox[key] || byBox[key].score < d.score) byBox[key] = { box: b, score: d.score };
                });
                var regions = [];
                Object.keys(byBox).map(function (k) { return byBox[k]; }).sort(function (a, b) { return b.score - a.score; }).forEach(function (r) {
                    if (regions.length < MAX_REGIONS && regions.every(function (k) { return iou(k.box, r.box) < 0.55; })) regions.push(r);
                });
                say('Found ' + regions.length + ' garment region' + (regions.length === 1 ? '' : 's') + '. Naming each one (CLIP)…');
                return paint().then(function () { return nameRegions(m, im, regions); }).then(function (found) {
                    // weak for both models: not a separate garment
                    found = found.filter(function (f) { return f.conf >= 0.3 || f.regionScore >= 0.15; });
                    found.forEach(function (f) { f.sure = f.conf >= MIN_NAME_CONFIDENCE; });
                    // one garment seen as several boxes (a part and the whole): merge into one box
                    found.sort(function (a, b) { return b.conf - a.conf; });
                    var kept = [];
                    found.forEach(function (f) {
                        var same = kept.filter(function (k) { return k.sure && f.sure && k.cls === f.cls && (inside(f.box, k.box) > 0.6 || inside(k.box, f.box) > 0.6); })[0];
                        if (same) { if (area(f.box) > area(same.box)) same.box = f.box; return; }   // keep the whole garment's box
                        if (!f.sure && kept.some(function (k) { return k.sure && inside(f.box, k.box) > 0.6; })) return;   // an unsure part of a named garment
                        kept.push(f);
                    });
                    var items = kept.map(function (f) {
                        var conf = r3(f.conf);
                        return { label: f.sure ? labelFor(f.cls, f.colour) : 'unknown_item', colour: f.colour, confidence: conf,
                                 bbox: [f.box[0] / W, f.box[1] / H, (f.box[2] - f.box[0]) / W, (f.box[3] - f.box[1]) / H].map(function (v) { return r3(Math.max(0, Math.min(1, v))); }) };
                    }).sort(function (a, b) { return a.bbox[1] - b.bbox[1] || a.bbox[0] - b.bbox[0]; });
                    var counts = {};
                    items.forEach(function (it) { counts[it.label] = (counts[it.label] || 0) + 1; });
                    return { items: items, width: W, height: H, regions: regions.length, debug: kept.map(function (k) { return { box: k.box, owl: r3(k.regionScore), colour: k.colour, top: k.top }; }),
                             detections: Object.keys(counts).map(function (l) { return { label: l, n: counts[l] }; }),
                             processingMs: Math.round(performance.now() - t0) };
                });
            });
        });
    }

    /* --------------------------------------------------- frames + summaries */
    function bytesOf(url) { return fetch(url, { cache: 'no-cache' }).then(function (r) { if (!r.ok) throw new Error('camera frame missing'); return r.arrayBuffer(); }); }
    function sha256(buf) {
        return crypto.subtle.digest('SHA-256', buf).then(function (h) {
            return Array.prototype.map.call(new Uint8Array(h), function (b) { return (b < 16 ? '0' : '') + b.toString(16); }).join('');
        });
    }
    function dataUrl(buf) {
        var bin = '', a = new Uint8Array(buf);
        for (var i = 0; i < a.length; i += 0x8000) bin += String.fromCharCode.apply(null, a.subarray(i, i + 0x8000));
        return 'data:image/jpeg;base64,' + btoa(bin);
    }

    function capture(src, frameId, when, trigger, progress) {
        return bytesOf(src).then(function (buf) {
            return Promise.all([sha256(buf), analyse(src, progress)]).then(function (r) {
                var a = r[1];
                return {
                    frameId: frameId, capturedAt: new Date(when).toISOString(), trigger: trigger, model: MODEL_INFO,
                    imageSha256: r[0], imageWidth: a.width, imageHeight: a.height, processingMs: a.processingMs,
                    items: a.items, detections: a.detections
                };
            });
        });
    }

    /* ------------------------------------------------------------ local store */
    // Only frame sources + summaries are kept (a few KB); the photos stay where the camera keeps them.
    var store = null, userId = null;
    function storeKey() { return 'taimi-edge-v3:' + userId; }
    function loadStore() { try { return JSON.parse(localStorage.getItem(storeKey()) || 'null'); } catch (e) { return null; } }
    function saveStore() {
        try { ['v1', 'v2'].forEach(function (v) { localStorage.removeItem('taimi-edge-' + v + ':' + userId); }); localStorage.setItem(storeKey(), JSON.stringify(store)); } catch (e) { /* memory only */ }
    }

    /* ---------------------------------------------------------------- server */
    function api(method, path, body) {
        return fetch(path, { method: method, credentials: 'same-origin', headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined })
            .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw Object.assign(new Error((j.error && j.error.message) || r.statusText), { status: r.status }); return j; }); });
    }
    function send(summaries, reset) { return api('POST', '/api/v1/laundry/observations', { reset: !!reset, observations: summaries }); }

    /* ------------------------------------------------------------ public API */
    var listeners = [], ready = null, busy = false, lastRun = null, consented = false;
    function emit(type, data) { listeners.forEach(function (fn) { try { fn(type, data); } catch (e) { /* ignore */ } }); }
    function step(id, text, extra) { emit('status', Object.assign({ step: id, text: text, at: Date.now() }, extra || {})); }

    function analyseHistory() {
        var now = Date.now(), frames = [];
        return HISTORY.reduce(function (p, h, k) {
            return p.then(function () {
                var when = now - h.hoursAgo * 3600e3, id = 'bf-' + userId.slice(-6) + '-' + k + '-' + (when / 1000 | 0).toString(36);
                step('history', 'Photo ' + (k + 1) + '/' + HISTORY.length + ': analysing on your device…');
                return capture(h.src, id, when, 'history', function (t) { step('history', 'Photo ' + (k + 1) + '/' + HISTORY.length + ': ' + t); })
                    .then(function (s) {
                        frames.push({ src: h.src, summary: s });
                        step('history', 'Photo ' + (k + 1) + '/' + HISTORY.length + ': ' + (s.items.length ? s.items.length + ' garment' + (s.items.length === 1 ? '' : 's') + ' recognised' : 'empty basket') + ' in ' + (s.processingMs / 1000).toFixed(1) + ' s');
                    });
            });
        }, Promise.resolve()).then(function () { return { frames: frames, next: 0, uploaded: {} }; });
    }

    function init() {
        if (ready) return ready;
        ready = api('GET', '/api/v1/me').then(function (me) {
            userId = me.id; consented = (me.consents || []).indexOf(CONSENT) !== -1;
            store = loadStore();
            return api('GET', '/api/v1/laundry').then(function (st) {
                var serverFrames = (st.camera && st.camera.frames) || [], lastId = serverFrames.length && serverFrames[serverFrames.length - 1].frameId;
                if (store && lastId && store.frames.some(function (f) { return f.summary.frameId === lastId; })) return st;   // in sync
                busy = true;
                emit('busy', { kind: 'history' });
                var make = store ? Promise.resolve(store) : analyseHistory();
                return make.then(function (s) {
                    store = s; saveStore();
                    step('send', 'Sending ' + s.frames.length + ' summaries to Sola (no images)…');
                    return send(s.frames.map(function (f) { return f.summary; }), true);
                }).then(function (st2) { busy = false; step('done', 'Plan updated from the camera history'); return st2; },
                        function (e) { busy = false; throw e; });
            });
        }).then(function (st) {
            if (consented) syncImages();
            emit('state', st);
            // warm the models up while the user reads, so a new photo is analysed straight away
            setTimeout(function () { if (!busy) loadModels().catch(function () { /* loaded on demand */ }); }, 2500);
            return st;
        });
        ready.catch(function () { ready = null; });
        return ready;
    }

    function hasNext() { return !store || store.next < NEXT.length; }

    /* "If a new piece comes in…": the camera takes one more photo, the models run here, the summary goes up. */
    function addPiece() {
        if (busy) return Promise.reject(new Error('busy'));
        return init().then(function () {
            if (store.next >= NEXT.length) throw new Error('That was the last photo in this demo. Reset the camera demo to replay it.');
            busy = true;
            var src = NEXT[store.next], when = Date.now(), id = 'np-' + userId.slice(-6) + '-' + (when / 1000 | 0).toString(36), before = performance.now();
            step('capture', 'Basket camera took a new photo');
            return capture(src, id, when, 'new_item', function (t) { step('model', t); }).then(function (s) {
                store.next++;
                store.frames.push({ src: src, summary: s });
                saveStore();
                lastRun = { frameId: id, items: s.items.length, ms: s.processingMs };
                step('model', 'Models found ' + s.items.length + ' garment' + (s.items.length === 1 ? '' : 's') + ' in ' + (s.processingMs / 1000).toFixed(1) + ' s, on your device',
                     { items: s.items });
                step('send', 'Sending the summary to Sola (labels and boxes only, no photo)…', { summary: s });
                return send([s], false);
            }).then(function (st) { return route(st, src, id); }).then(function (st) {
                var f = st.camera.frames[st.camera.frames.length - 1] || {};
                step('plan', 'Sola updated the wash plan' + (f.added && f.added.length ? ': new ' + f.added.map(function (a) { return a.name; }).join(', ') : ''));
                step('done', 'Done in ' + ((performance.now() - before) / 1000).toFixed(1) + ' s');
                emit('state', st);
                if (consented) syncImages();
                return st;
            });
        }).then(function (st) { busy = false; return st; }, function (e) { busy = false; throw e; });
    }

    /* The server's router decides whether the agent takes a second look (only with photo consent). */
    var ROUTE_TEXT = {
        sure: 'The camera was sure about every piece: no second look needed',
        reviewed: "Sola's agent looked at the photo and worked out what's in the basket",
        done: "Sola's agent had already checked this photo",
        'agent-unavailable': "Sola's agent isn't available right now: using the on-device result",
        'agent-failed': "Sola's agent couldn't read the photo: using the on-device result",
        'no-image': 'Using the on-device result'
    };
    function route(st, src, id) {
        var unsure = st.camera && st.camera.secondLookNeeded;
        if (!consented) {
            step('route', unsure ? 'Some pieces overlap. Photos stay on your device, so Sola uses the on-device result' : 'The camera was sure about every piece');
            return st;
        }
        if (!unsure) { step('route', ROUTE_TEXT.sure); }
        else step('route', "Some pieces overlap: sending this photo to Sola's agent for a second look (you allowed photos)…");
        return bytesOf(src).then(function (buf) { return api('POST', '/api/v1/laundry/frames/' + id + '/image', { image: dataUrl(buf) }); }).then(function (r) {
            store.uploaded[id] = true; saveStore();
            if (unsure) step('route', ROUTE_TEXT[(r.route || {}).reason] || ROUTE_TEXT['no-image']);
            return api('GET', '/api/v1/laundry');
        }, function () { return st; });
    }

    /* Upload images only with consent, and only the bytes the models analysed. */
    function syncImages() {
        if (!consented || !store) return Promise.resolve(0);
        var todo = store.frames.filter(function (f) { return !store.uploaded[f.summary.frameId]; });
        var chain = Promise.resolve(0);
        todo.forEach(function (f) {
            chain = chain.then(function (n) {
                return bytesOf(f.src).then(function (buf) { return api('POST', '/api/v1/laundry/frames/' + f.summary.frameId + '/image', { image: dataUrl(buf) }); })
                    .then(function () { store.uploaded[f.summary.frameId] = true; return n + 1; }, function () { return n; });
            });
        });
        return chain.then(function (n) {
            saveStore();
            if (!n) return 0;
            emit('images', { uploaded: n });
            return api('GET', '/api/v1/laundry').then(function (st) { emit('state', st); return n; });
        });
    }

    function setImageConsent(allow) {
        return api(allow ? 'POST' : 'DELETE', '/api/v1/consents/' + CONSENT).then(function () {
            consented = !!allow;
            if (!allow && store) { store.uploaded = {}; saveStore(); }
            return allow ? syncImages() : 0;
        }).then(function () { return api('GET', '/api/v1/laundry'); }).then(function (st) { emit('state', st); return st; });
    }

    function reset() {
        return init().then(function () {
            busy = true;
            emit('busy', { kind: 'reset' });
            if (!store) return analyseHistory();
            // replay: keep the history's summaries (same photos, same result), drop the new pieces
            var hist = store.frames.filter(function (f) { return f.summary.trigger === 'history'; });
            return { frames: hist, next: 0, uploaded: {} };
        }).then(function (s) {
            store = s; saveStore();
            step('send', 'Re-sending the camera history (summaries only)…');
            return send(s.frames.map(function (f) { return f.summary; }), true);
        }).then(function (st) { busy = false; step('done', 'Camera demo reset'); if (consented) syncImages(); emit('state', st); return st; },
                function (e) { busy = false; throw e; });
    }

    window.TaimiEdge = {
        init: init, addPiece: addPiece, reset: reset, syncImages: syncImages, setImageConsent: setImageConsent, hasNext: hasNext,
        isBusy: function () { return busy; },
        on: function (fn) { listeners.push(fn); },
        info: function () { return { model: MODEL_INFO, detector: DETECTOR, namer: NAMER, lastRun: lastRun, consented: consented, frames: store ? store.frames.length : 0 }; },
        _dev: { analyse: analyse, loadModels: loadModels }   // for evaluation scripts only
    };
})();
