import test from 'node:test';
import assert from 'node:assert/strict';
import { initialItems, basketTotal, addItem, safeText, loadState } from '../src/model.js';
test('comparison uses integer cents, excludes completed items, and splits across stores', () => {
  assert.equal(basketTotal(initialItems, 'one'), 1085);
  assert.equal(basketTotal(initialItems, 'split'), 1065);
  assert.equal(basketTotal(initialItems.map(i => ({ ...i, done: true }))), 0);
});
test('new items have an unknown price rather than an invented quote', () => {
  const items = addItem([], '  Rice  ');
  assert.equal(items[0].name, 'Rice');
  assert.equal(items[0].unknownPrice, true);
  assert.deepEqual(addItem([], '   '), []);
});
test('user input is escaped for HTML and corrupted storage recovers', () => {
  assert.equal(safeText('<img onerror="x">'), '&lt;img onerror=&quot;x&quot;&gt;');
  assert.equal(loadState({ getItem: () => '{broken' }).items.length, 5);
  assert.equal(loadState({ getItem: () => '{"items":[{}]}' }).items.length, 5);
});
