/* Taimi bridge: injected only when the backend serves the frontends.
   - mobile: hydrate the first-run state from the signed-in account (/api/v1/state)
     and clear another account's cached local state;
   - both: send the user to /login when the session expires, and add a sign-out control.
   The frontends keep working unchanged as static demos without this file. */
(function () {
    'use strict';
    var isMobile = !!window.FigmentAPI;
    var KEY = 'figment-state-v1';

    var origFetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
        return origFetch(input, init).then(function (r) {
            if (r.status === 401 && String(input).indexOf('/api/') !== -1) {
                location.href = '/login?next=' + encodeURIComponent(location.pathname + location.hash);
            }
            return r;
        });
    };

    if (isMobile) {
        try {
            var xhr = new XMLHttpRequest();
            xhr.open('GET', '/api/v1/state', false); // before app.js reads seed()
            xhr.send();
            if (xhr.status === 200) {
                var server = JSON.parse(xhr.responseText);
                if (localStorage.getItem('taimi-user') !== server.user.id) {
                    localStorage.removeItem(KEY);
                    localStorage.setItem('taimi-user', server.user.id);
                }
                var baseSeed = window.FigmentAPI.seed;
                window.FigmentAPI.seed = function () {
                    var s = baseSeed();
                    Object.keys(server).forEach(function (k) {
                        if (k === 'memoryConsent' && server[k] === false) return; // let the app ask
                        if (server[k] !== undefined && server[k] !== null) s[k] = server[k];
                    });
                    if (!s.chat || !s.chat.length) s.chat = baseSeed().chat;
                    return s;
                };
            } else if (xhr.status === 401) {
                location.href = '/login?next=/mobile/';
            }
        } catch (e) { /* fall back to the built-in seed */ }
    }

    function addSignOut() {
        var a = document.createElement('a');
        a.href = '/logout';
        a.textContent = 'Sign out';
        a.setAttribute('aria-label', 'Sign out of Taimi');
        var reset = document.getElementById('reset-demo');
        if (reset && reset.parentNode) {
            a.className = reset.className || 'pill outline';
            a.style.marginTop = '10px';
            a.style.display = 'inline-flex';
            reset.parentNode.insertBefore(a, reset.nextSibling);
        } else {
            a.style.cssText = 'position:fixed;right:12px;bottom:12px;z-index:9999;background:#353b35;color:#fff;padding:8px 14px;border-radius:999px;font:600 13px system-ui;text-decoration:none;box-shadow:0 4px 14px rgba(0,0,0,.15)';
            document.body.appendChild(a);
        }
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', addSignOut);
    else addSignOut();
})();
