export const initialItems = [
  { id: 'oat', name: 'Oat milk', detail: '1 L · unsweetened', icon: '🥛', priority: 'Essentials', done: false, prices: [179, 219] },
  { id: 'banana', name: 'Bananas', detail: '1 kg · a little green', icon: '🍌', priority: 'Essentials', done: false, prices: [169, 149] },
  { id: 'avocado', name: 'Avocados', detail: '2 pack · ready to eat', icon: '🥑', priority: 'Nice to have', done: false, prices: [249, 299] },
  { id: 'bread', name: 'Sourdough bread', detail: '500 g · wholegrain', icon: '🍞', priority: 'Essentials', done: false, prices: [329, 359] },
  { id: 'spinach', name: 'Baby spinach', detail: '100 g · fresh', icon: '🥬', priority: 'Nice to have', done: false, prices: [159, 189] }
];
export const money = cents => new Intl.NumberFormat('en-IE', { style: 'currency', currency: 'EUR' }).format(cents / 100);
export function basketTotal(items, mode = 'one') {
  return items.filter(item => !item.done).reduce((sum, item) => sum + (mode === 'split' ? Math.min(...item.prices) : item.prices[0]), 0);
}
export function addItem(items, name) {
  const trimmed = name.trim().slice(0, 80);
  if (!trimmed) return items;
  return [...items, { id: `custom-${Date.now()}`, name: trimmed, detail: 'Added by you · price unknown', icon: '🛍️', priority: 'Essentials', done: false, prices: [0, 0], unknownPrice: true }];
}
export function safeText(value) {
  return String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}
export function loadState(storage) {
  try {
    const data = JSON.parse(storage.getItem('sola-demo-v1'));
    if (!data || !Array.isArray(data.items) || !data.items.every(i => i && typeof i.id === 'string' && typeof i.name === 'string' && typeof i.detail === 'string' && typeof i.icon === 'string' && typeof i.priority === 'string' && typeof i.done === 'boolean' && Array.isArray(i.prices) && i.prices.length === 2 && i.prices.every(n => Number.isInteger(n) && n >= 0))) throw Error();
    return { items: data.items, mode: data.mode === 'split' ? 'split' : 'one', approved: data.approved === true, laundry: data.laundry === true, checkedIn: data.checkedIn === true, memory: data.memory === true, saved: Array.isArray(data.saved) ? data.saved.filter(x => typeof x === 'string') : [] };
  } catch { return { items: structuredClone(initialItems), mode: 'one', approved: false, laundry: false, checkedIn: false, memory: false, saved: [] }; }
}
