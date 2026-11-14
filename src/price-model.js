// Entire catalog and all offers/history are fictional. No remote requests.
export const catalog = [
  { id: 'air', category: 'electronics', name: 'DemoBook Air 14', sku: 'DB-A14-16-512', variant: '16 GB RAM · 512 GB · Nordic keyboard', attributes: 'laptop, lightweight, work, 16 GB, 512 GB', emoji: '💻', base: 89900 },
  { id: 'pro', category: 'electronics', name: 'DemoBook Studio 15', sku: 'DB-S15-32-1T', variant: '32 GB RAM · 1 TB · Nordic keyboard', attributes: 'laptop, creative, 32 GB, 1 TB', emoji: '💻', base: 129900 },
  { id: 'boots', category: 'footwear', name: 'Demo Trail Boots', sku: 'DTB-42-BK', variant: 'EU 42 · black · waterproof', attributes: 'boots, waterproof, black, EU 42, walking', emoji: '🥾', base: 12900 },
  { id: 'sneakers', category: 'footwear', name: 'Demo City Sneakers', sku: 'DCS-42-WH', variant: 'EU 42 · white · canvas', attributes: 'sneakers, white, EU 42, casual', emoji: '👟', base: 7900 },
  { id: 'coat', category: 'clothing', name: 'Demo Winter Parka', sku: 'DWP-M-OL', variant: 'M · olive · insulated', attributes: 'coat, parka, winter, olive, insulated, M', emoji: '🧥', base: 15900 },
  { id: 'sweater', category: 'clothing', name: 'Demo Wool Sweater', sku: 'DWS-M-CR', variant: 'M · cream · wool', attributes: 'sweater, wool, cream, M', emoji: '🧶', base: 6900 },
  { id: 'concert', category: 'tickets', name: 'Demo Northern Lights Concert', sku: 'DNLC-DEC12-GA', variant: '12 Dec 2026 · 19:00 · Helsinki · general admission · 1 adult', attributes: 'concert, music, Helsinki, general admission, 12 Dec 2026', emoji: '🎟️', base: 5900 },
  { id: 'train', category: 'tickets', name: 'Demo Helsinki–Tampere Train', sku: 'DHT-DEC12-0900', variant: '12 Dec 2026 · 09:00 · one-way · standard · 1 adult', attributes: 'train, Helsinki, Tampere, standard, 12 Dec 2026', emoji: '🚆', base: 2900 }
];
export const categories = { all: 'All categories', electronics: 'Electronics', footwear: 'Footwear', clothing: 'Clothing', tickets: 'Tickets & travel', other: 'Other / custom item' };
export const stores = ['Demo Direct', 'Sample Outlet', 'Example Deals'];
export const defaultSearch = { mode: 'explore', category: 'all', query: '', requirements: '', budget: '1500', target: '800', stores: [...stores], sort: 'price' };
export function parseMoney(value) {
  const text = String(value).trim();
  if (!/^\d+(\.\d{1,2})?$/.test(text)) return null;
  const amount = Math.round(Number(text) * 100);
  return Number.isSafeInteger(amount) && amount > 0 && amount <= 100000000 ? amount : null;
}
export function matchingProducts(search) {
  const query = search.query.trim().toLowerCase();
  const terms = search.requirements.toLowerCase().split(',').map(s => s.trim()).filter(Boolean);
  return catalog.filter(p => (search.category === 'all' || p.category === search.category)
    && (!query || `${p.name} ${p.sku} ${p.attributes}`.toLowerCase().includes(query))
    && (search.mode !== 'exact' || (query && (p.name.toLowerCase() === query || p.sku.toLowerCase() === query)))
    && (search.mode === 'exact' || terms.every(t => `${p.attributes} ${p.variant}`.toLowerCase().includes(t))));
}
export function offersFor(product, step = 0) {
  const price = Math.max(100, product.base - Math.min(step, 8) * Math.round(product.base * .04));
  return [
    { store: stores[0], price, fees: 0, stock: true, condition: 'new / standard', note: 'Standard terms · fictional' },
    { store: stores[1], price: Math.max(100, price - 500), fees: 990, stock: true, condition: 'new / standard', note: 'Delivery / booking fee included below' },
    { store: stores[2], price: Math.max(100, price - 1500), fees: 0, stock: false, condition: 'new / standard', note: 'Unavailable · excluded from best offer' }
  ];
}
export function bestOffer(product, step, selectedStores) {
  return offersFor(product, step).filter(o => o.stock && selectedStores.includes(o.store)).sort((a,b) => (a.price+a.fees)-(b.price+b.fees))[0] || null;
}
export function searchResults(search, step = 0) {
  const budget = parseMoney(search.budget);
  const results = matchingProducts(search).map(product => ({ product, offer: bestOffer(product, step, search.stores) }))
    .filter(r => r.offer && budget !== null && r.offer.price+r.offer.fees <= budget);
  return results.sort(search.sort === 'name' ? (a,b) => a.product.name.localeCompare(b.product.name) : (a,b) => a.offer.price+a.offer.fees-b.offer.price-b.offer.fees);
}
export function createWatch(search, productId = null) {
  if (parseMoney(search.budget) === null || parseMoney(search.target) === null || !search.stores.length) throw Error('Enter positive prices (up to €1,000,000) and select at least one store.');
  if (!productId && !search.query.trim()) throw Error('Enter an item or search phrase to save this watch.');
  return { id: crypto.randomUUID(), search: structuredClone(search), productId, paused: false, step: 0, history: [], alerts: [], wasBelow: false, createdAt: new Date().toISOString() };
}
export function checkWatch(watch, now = new Date().toISOString()) {
  if (watch.paused) return watch;
  const step = Math.min(watch.step + 1, 8);
  const product = watch.productId ? catalog.find(p => p.id === watch.productId) : null;
  const result = product ? { product, offer: bestOffer(product, step, watch.search.stores) } : searchResults(watch.search, step)[0];
  const total = result?.offer ? result.offer.price + result.offer.fees : null;
  const below = total !== null && total <= parseMoney(watch.search.target) && total <= parseMoney(watch.search.budget);
  const alerts = below && !watch.wasBelow ? [{ id: crypto.randomUUID(), at: now, text: `Sample target reached: ${result.product.name}`, total }, ...watch.alerts].slice(0, 10) : watch.alerts;
  return { ...watch, step, history: [...watch.history, { at: now, total, product: result?.product.name || null }].slice(-12), alerts, wasBelow: below };
}
export function loadWatches(storage) {
  try {
    const list = JSON.parse(storage.getItem('sola-price-watch-v1'));
    if (!Array.isArray(list)) return [];
    return list.filter(w => w && typeof w.id === 'string' && (w.productId === null || catalog.some(p => p.id === w.productId)) && typeof w.paused === 'boolean' && Number.isInteger(w.step) && w.step >= 0 && w.step <= 8 && typeof w.wasBelow === 'boolean' && w.search && ['explore','exact'].includes(w.search.mode) && Object.hasOwn(categories,w.search.category) && ['query','requirements','budget','target','sort'].every(k => typeof w.search[k] === 'string') && parseMoney(w.search.budget) !== null && parseMoney(w.search.target) !== null && Array.isArray(w.search.stores) && w.search.stores.length && w.search.stores.every(s => stores.includes(s)) && Array.isArray(w.history) && w.history.every(h => h && typeof h.at === 'string' && (h.total === null || Number.isSafeInteger(h.total) && h.total >= 0) && (h.product === null || typeof h.product === 'string')) && Array.isArray(w.alerts) && w.alerts.every(a => a && typeof a.id === 'string' && typeof a.at === 'string' && typeof a.text === 'string' && Number.isSafeInteger(a.total) && a.total >= 0)).slice(0, 50);
  } catch { return []; }
}
