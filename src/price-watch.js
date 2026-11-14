import { money, safeText as esc } from './model.js';
import { catalog, categories, stores, defaultSearch, searchResults, offersFor, bestOffer, createWatch, checkWatch, loadWatches, parseMoney } from './price-model.js';

let search = structuredClone(defaultSearch);
let watches;
try { watches = loadWatches(localStorage); } catch { watches = []; }
const selected = new Set();
let searched = false;
const option = (value, label, current) => `<option value="${esc(value)}" ${value === current ? 'selected' : ''}>${esc(label)}</option>`;
const action = (label, name, extra = '', cls = 'button secondary') => `<button type="button" class="${cls}" data-price-action="${name}" ${extra}>${label}</button>`;
const formatDate = value => { const d = new Date(value); return Number.isNaN(d.getTime()) ? 'Unknown time' : d.toLocaleString([], { dateStyle: 'short', timeStyle: 'short' }); };
function save(toast) { try { localStorage.setItem('sola-price-watch-v1', JSON.stringify(watches)); } catch { toast('Storage unavailable. Watches last only for this session.'); } }
export function resetPriceWatches() { watches = []; search = structuredClone(defaultSearch); searched = false; selected.clear(); try { localStorage.removeItem('sola-price-watch-v1'); } catch {} }
export function priceWatchView() {
  const results = searchResults(search);
  return `<div class="page-heading"><div><p class="eyebrow">SOMETHING WORTH WAITING FOR</p><h1>Find your thing. Watch the price.</h1><p class="muted">A laptop, the right boots, a winter coat, a ticket somewhere. Your choice, your budget.</p></div><span class="pill">${watches.length} SAVED WATCHES</span></div>
  <div class="notice">All products, stores, prices and histories are fictional fixtures. Checks run only when you click “Simulate check”. No websites, background jobs or notifications are connected.</div>
  <section class="panel price-search"><div class="section-heading"><h2>What are you looking for?</h2><span class="pill">ANY ITEM · DEMO CATALOG</span></div>
  <form id="price-search-form"><div class="price-mode" role="group" aria-label="Shopping mode">${action('Help me choose', 'mode', `data-value="explore" aria-pressed="${search.mode === 'explore'}"`, `store-option ${search.mode === 'explore' ? 'selected' : ''}`)}${action('I know the exact item', 'mode', `data-value="exact" aria-pressed="${search.mode === 'exact'}"`, `store-option ${search.mode === 'exact' ? 'selected' : ''}`)}</div>
  <div class="price-form-grid"><label>Category<select name="category">${Object.entries(categories).map(([v,l]) => option(v,l,search.category)).join('')}</select></label><label>${search.mode === 'exact' ? 'Exact model / SKU' : 'Item or search phrase (optional)'}<input name="query" value="${esc(search.query)}" placeholder="${search.mode === 'exact' ? 'Choose a sample below or enter your own item' : 'Try boots, laptop, train…'}" list="sample-products" maxlength="160" ${search.mode === 'exact' ? 'required' : ''}></label>
  <label>Maximum total (€)<input name="budget" type="number" min="0.01" max="1000000" step="0.01" value="${esc(search.budget)}" required></label><label>Alert at or below (€)<input name="target" type="number" min="0.01" max="1000000" step="0.01" value="${esc(search.target)}" required></label>
  <label class="wide">Must-have details (comma-separated)<input name="requirements" value="${esc(search.requirements)}" placeholder="e.g. waterproof, EU 42 · or Helsinki, general admission" maxlength="240" ${search.mode === 'exact' ? 'disabled' : ''}></label></div>
  <datalist id="sample-products">${catalog.map(p => `<option value="${esc(p.name)}">${esc(p.variant)}</option>`).join('')}</datalist>
  <fieldset class="price-stores"><legend>Stores / websites to compare (fictional)</legend>${stores.map(s => `<label><input type="checkbox" name="stores" value="${s}" ${search.stores.includes(s) ? 'checked' : ''}> ${s}</label>`).join('')}</fieldset>
  <div class="price-form-actions"><button class="button dark" type="submit">Compare sample offers →</button>${action('Save this search as a watch', 'save-search')}<label>Sort<select name="sort">${option('price','Lowest delivered total',search.sort)}${option('name','Product name',search.sort)}</select></label></div>
  <p class="small-text muted">Sample matching uses names, SKUs and comma-separated text phrases—not AI. Exact mode requires a full sample name or SKU. Custom items can be saved, but get no invented offers.</p></form></section>
  <div class="section-heading price-section"><h2>${searched ? 'Your sample matches' : 'Explore the sample catalog'}</h2>${action(`Compare selected (${selected.size}/3)`, 'compare')}</div>
  <div class="price-results">${results.length ? results.map(({product:p,offer:o}) => `<article class="panel product-card"><div class="product-card-top"><span class="product-emoji" aria-hidden="true">${p.emoji}</span><label class="compare-check"><input type="checkbox" data-price-select="${p.id}" ${selected.has(p.id) ? 'checked' : ''}> Compare</label></div><p class="eyebrow">${esc(categories[p.category])} · SAMPLE</p><h2>${esc(p.name)}</h2><p class="product-variant">${esc(p.variant)}</p><p class="small-text muted">SKU ${esc(p.sku)}</p><div class="product-price"><strong>${money(o.price+o.fees)}</strong><span>${esc(o.store)} · ${o.fees ? 'fees included' : 'no extra fee in fixture'}</span></div><p class="small-text muted">Lowest eligible sample offer · ${money(o.price)} + ${money(o.fees)} fees · simulated available</p><div class="product-actions">${action('See store comparison','offers',`data-id="${p.id}"`)}${action('Watch this item','watch',`data-id="${p.id}"`,'button dark')}</div></article>`).join('') : '<div class="panel empty"><h2>No eligible sample offers</h2><p>Try another category, budget, store, or matching phrase. Other/custom items have no fixtures; you can still save a named watch for the future live integration.</p></div>'}</div>
  <div class="section-heading price-section"><h2>Your price watches</h2><span class="muted small-text">On-device demo state · manual checks only</span></div><div class="watch-list">${watches.length ? watches.map(watchCard).join('') : '<div class="panel empty"><h2>A little patience can pay off.</h2><p>Watch an exact item, or save a search while you’re still deciding. Your target stays under your control.</p></div>'}</div>`;
}
function watchCard(w) {
  const p = catalog.find(p => p.id === w.productId);
  const last = w.history.at(-1);
  const title = p?.name || w.search.query;
  const points = w.history.filter(h => h.total !== null);
  return `<article class="panel watch-card"><div class="section-heading"><div><p class="eyebrow">${p || w.search.mode === 'exact' ? 'EXACT ITEM' : 'OPEN SEARCH'} · ${w.paused ? 'PAUSED' : 'MANUAL DEMO'}</p><h2>${esc(title)}</h2></div>${action('Remove','remove',`data-id="${esc(w.id)}"`,'text-button')}</div><p class="muted small-text">${p ? esc(p.variant) : esc(w.search.requirements || 'Any matching variant; review before choosing')} · ${esc(categories[w.search.category])}</p><p class="muted small-text">Sites: ${w.search.stores.map(esc).join(', ')} · budget ${money(parseMoney(w.search.budget))}</p><div class="watch-metrics"><div><small>Target total</small><strong>${money(parseMoney(w.search.target))}</strong></div><div><small>Latest simulated total</small><strong>${last?.total != null ? money(last.total) : 'No quote'}</strong></div><div><small>Last manual check</small><span>${last ? esc(formatDate(last.at)) : 'Not checked'}</span></div></div>
  ${w.alerts.length ? `<div class="price-alert" role="status">✓ ${esc(w.alerts[0].text)} at ${money(w.alerts[0].total)} · in-app demo alert only</div>` : ''}
  ${w.history.length ? `<details class="price-history"><summary>Sample price history · ${w.history.length} checks</summary><p class="small-text muted">Synthetic values, not market history. Open searches can change product; each quote names its match.</p>${points.length ? `<div class="history-bars" aria-hidden="true">${points.map(h => `<span style="height:${Math.max(8,Math.round(h.total/Math.max(...points.map(i=>i.total))*65))}px"></span>`).join('')}</div>` : ''}<ol>${w.history.map(h => `<li><time>${esc(formatDate(h.at))}</time><span>${h.total === null ? 'No matching quote' : `${money(h.total)} · ${esc(h.product)}`}</span></li>`).join('')}</ol></details>` : ''}<div class="watch-actions">${action(w.step >= 8 ? 'Demo limit reached' : 'Simulate check', 'check', `data-id="${esc(w.id)}" ${w.paused || w.step >= 8 ? 'disabled' : ''}`, 'button dark')}${action(w.paused ? 'Resume watch' : 'Pause watch','pause',`data-id="${esc(w.id)}" aria-pressed="${w.paused}"`)}${action('Edit target','target',`data-id="${esc(w.id)}"`)}</div><p class="small-text muted">No automatic checks or messages. Simulation lowers sample prices by 4% of base per check, up to eight checks.</p></article>`;
}
function readSearch() {
  const form = document.querySelector('#price-search-form'); if (!form) return;
  const data = new FormData(form);
  search = { mode: search.mode, category: data.get('category'), query: String(data.get('query') || '').trim(), requirements: search.mode === 'exact' ? '' : String(data.get('requirements') || '').trim(), budget: String(data.get('budget') || ''), target: String(data.get('target') || ''), stores: data.getAll('stores'), sort: data.get('sort') };
}
export function priceWatchSubmit(event, render, toast) {
  if (event.target.id !== 'price-search-form') return false;
  event.preventDefault(); readSearch();
  if (!search.stores.length) { toast('Choose at least one sample store.'); return true; }
  searched = true; selected.clear(); render(); return true;
}
export function priceWatchChange(event, render, toast) {
  if (!event.target.matches('[data-price-select]')) return false;
  const id = event.target.dataset.priceSelect;
  if (event.target.checked && selected.size >= 3) { event.target.checked = false; toast('Compare up to three items at a time.'); return true; }
  if (event.target.checked) selected.add(id); else selected.delete(id);
  readSearch(); render(); return true;
}
export function priceWatchClick(event, render, toast, modal, close) {
  const el = event.target.closest('[data-price-action]'); if (!el) return false;
  const a = el.dataset.priceAction; const id = el.dataset.id;
  if (a === 'mode') { readSearch(); search.mode = el.dataset.value; selected.clear(); render(); }
  if (a === 'compare') {
    const products = catalog.filter(p => selected.has(p.id));
    if (products.length < 2) { toast('Select two or three items to compare.'); return true; }
    modal('Compare your shortlist', `<p class="muted">Different item variants are shown explicitly. Lowest cost alone does not mean best fit. All values are fictional.</p><div class="shortlist">${products.map(p => { const o = bestOffer(p,0,search.stores); return `<article><h3>${esc(p.name)}</h3><p>${esc(p.variant)}</p><p>${esc(categories[p.category])}</p><strong>${o ? money(o.price+o.fees) : 'No eligible offer'}</strong><p>${esc(p.attributes)}</p></article>`; }).join('')}</div>`);
  }
  if (a === 'offers') {
    const p = catalog.find(p => p.id === id); if (!p) return true;
    modal('Same item. Different stores.', `<h3>${esc(p.name)}</h3><p>${esc(p.variant)} · SKU ${esc(p.sku)}</p><p class="muted">All offers refer to this exact fixture variant. Prices include sample tax; shipping/booking fees are listed separately. No live source exists.</p><div class="offer-list">${offersFor(p).filter(o => search.stores.includes(o.store)).map(o => `<article><strong>${esc(o.store)}</strong><p>Item ${money(o.price)} + fees ${money(o.fees)} = <strong>${money(o.price+o.fees)}</strong></p><p>${o.stock ? 'Simulated available' : 'Unavailable · excluded'} · ${esc(o.condition)}</p><small>${esc(o.note)} · source: fixture · not fetched</small></article>`).join('') || '<p>No stores selected.</p>'}</div>`);
  }
  if (a === 'watch' || a === 'save-search') {
    readSearch();
    if (watches.length >= 50) { toast('Demo limit: 50 watches. Remove one to add another.'); return true; }
    try { const w = createWatch(search,a === 'watch' ? id : null); watches.unshift(w); save(toast); render(); toast('Watch saved locally. Use Simulate check to try an alert.'); } catch(error) { toast(error.message); }
  }
  const w = watches.find(w => w.id === id);
  if (w && a === 'check' && w.step < 8) { watches = watches.map(i => i.id === id ? checkWatch(i) : i); save(toast); render(); }
  if (w && a === 'pause') { w.paused = !w.paused; save(toast); render(); }
  if (w && a === 'remove') { watches = watches.filter(i => i.id !== id); save(toast); render(); toast('Watch removed from this browser.'); }
  if (w && a === 'target') modal('Change your target', `<label class="price-target">Alert at or below (€)<input id="price-target-input" type="number" min="0.01" max="1000000" step="0.01" value="${esc(w.search.target)}"></label><p class="muted">This changes your in-app demo threshold. It doesn’t create notifications or run checks.</p>`,action('Save target','save-target',`data-id="${esc(id)}"`,'button dark'));
  if (w && a === 'save-target') { const value = document.querySelector('#price-target-input').value; if (parseMoney(value) === null) { toast('Enter a positive target with up to two decimal places.'); return true; } w.search.target = value; w.wasBelow = false; w.alerts = []; save(toast); close(); render(); toast('Target updated. Run a simulated check to evaluate it.'); }
  return true;
}
