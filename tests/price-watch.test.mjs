import test from 'node:test';
import assert from 'node:assert/strict';
import { catalog, defaultSearch, parseMoney, searchResults, bestOffer, createWatch, checkWatch, loadWatches } from '../src/price-model.js';
const search = overrides => ({ ...structuredClone(defaultSearch), ...overrides });
test('compares delivered price and excludes unavailable cheaper offers', () => {
  const offer = bestOffer(catalog[0], 0, defaultSearch.stores);
  assert.equal(offer.store, 'Demo Direct');
  assert.equal(offer.price + offer.fees, 89900);
  assert.equal(bestOffer(catalog[0], 0, ['Example Deals']), null);
});
test('matches any fixture category and exact variants without inventing custom offers', () => {
  for (const category of ['electronics','footwear','clothing','tickets']) assert.ok(searchResults(search({category})).length);
  assert.equal(searchResults(search({category:'footwear',requirements:'waterproof, EU 42'}))[0].product.id, 'boots');
  assert.equal(searchResults(search({mode:'exact',query:'DTB-42-BK'})).length, 1);
  assert.equal(searchResults(search({mode:'exact',query:'DTB-43-BK'})).length, 0);
  assert.equal(searchResults(search({query:'My custom camera'})).length, 0);
  assert.equal(searchResults(search({budget:'1'})).length, 0);
});
test('target crossing alerts once, pause preserves history, custom watches have unknown quotes', () => {
  let w = createWatch(search({target:'870'}), 'air');
  w = checkWatch(w); assert.equal(w.alerts.length, 1);
  w = checkWatch(w); assert.equal(w.alerts.length, 1);
  const paused = {...w,paused:true}; assert.deepEqual(checkWatch(paused), paused);
  const overBudget = checkWatch(createWatch(search({budget:'1',target:'1500'}), 'air'));
  assert.equal(overBudget.alerts.length,0);
  const custom = checkWatch(createWatch(search({mode:'exact',query:'Custom boots size 47'})));
  assert.equal(custom.history[0].total, null); assert.equal(custom.alerts.length,0);
});
test('money parsing and watch storage reject corrupt values; valid watches survive refresh', () => {
  assert.equal(parseMoney('1.99'),199);
  for(const value of ['', '-1', '1.999', 'Infinity','1e3']) assert.equal(parseMoney(value),null);
  const w = checkWatch(createWatch(search({query:'boots',target:'100'})));
  assert.deepEqual(loadWatches({getItem:()=>JSON.stringify([w])}),[w]);
  assert.deepEqual(loadWatches({getItem:()=>JSON.stringify([{id:'bad'}])}),[]);
  assert.deepEqual(loadWatches({getItem:()=>'{broken'}),[]);
});
