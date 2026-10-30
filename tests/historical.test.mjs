import test from 'node:test';
import assert from 'node:assert/strict';
import { indexBoardSymbols, getBoardCapacity } from '../historical/frontend/src/lib/boardGrid.ts';
import { glossSymbolUtterance } from '../historical/frontend/src/lib/gloss.ts';
import { dedupeLearningSymbols, getUniquePlayableSymbols } from '../historical/frontend/src/lib/symbols.ts';

test('board capacity preserves historical default and explicit dimensions', () => {
  assert.equal(getBoardCapacity({}), 20);
  assert.equal(getBoardCapacity({ grid_rows: 2, grid_cols: 3 }), 6);
  assert.equal(getBoardCapacity({ grid_rows: null, grid_cols: null }), 20);
  assert.equal(getBoardCapacity({ grid_rows: 0, grid_cols: 3 }), 0);
});
test('grid indexing is empty-safe and preserves last-write-wins placement', () => {
  assert.equal(indexBoardSymbols([]).size, 0);
  const a = { id: 1, position_x: 0, position_y: 0 };
  const b = { id: 2, position_x: 0, position_y: 0 };
  const c = { id: 3, position_x: 1, position_y: 0 };
  const before = JSON.stringify([a, b, c]);
  const result = indexBoardSymbols([a, b, c]);
  assert.equal(result.size, 2);
  assert.equal(result.get('0-0'), b);
  assert.equal(result.get('1-0'), c);
  assert.equal(JSON.stringify([a, b, c]), before);
});
test('gloss handles empty and whitespace labels', () => {
  assert.equal(glossSymbolUtterance([]), '');
  assert.equal(glossSymbolUtterance([{ label: '  ' }]), '');
});
test('gloss applies historical English templates and fallback punctuation', () => {
  assert.equal(glossSymbolUtterance(['I', 'want', 'water'].map(label => ({ label }))), 'I want water.');
  assert.equal(glossSymbolUtterance([{ label: 'where water' }]), 'Where water?');
  assert.equal(glossSymbolUtterance([{ label: 'happy' }]), 'I feel happy.');
  assert.equal(glossSymbolUtterance([{ label: 'me tired' }]), 'I feel tired.');
  assert.equal(glossSymbolUtterance([{ label: 'we drink water' }]), 'We drink water.');
  assert.equal(glossSymbolUtterance([{ label: 'hola' }]), 'Hola.');
  assert.equal(glossSymbolUtterance([{ label: 'hello!' }]), 'Hello!');
});
test('library deduplication normalizes labels and prefers an image reference', () => {
  const a = { id: 1, label: ' Water ', category: 'sample' };
  const b = { id: 2, label: 'water', category: 'other', image_path: '/synthetic-placeholder.svg' };
  const c = { id: 3, label: 'WATER', category: 'sample' };
  const d = { id: 4, label: '  ', category: 'sample' };
  assert.deepEqual(dedupeLearningSymbols([a, b, c, d]), [b]);
  assert.deepEqual(dedupeLearningSymbols([]), []);
});
test('playable selection hides invisible entries, uses custom labels and keeps first duplicate', () => {
  const a = { id: 1, is_visible: true, symbol: { label: 'water' } };
  const b = { id: 2, is_visible: true, symbol: { label: ' WATER ' } };
  const c = { id: 3, is_visible: false, symbol: { label: 'food' } };
  const d = { id: 4, is_visible: true, custom_text: 'help', symbol: { label: 'water' } };
  const e = { id: 5, is_visible: true, symbol: { label: ' ' } };
  assert.deepEqual(getUniquePlayableSymbols([a, b, c, d, e]), [a, d]);
  assert.deepEqual(getUniquePlayableSymbols([]), []);
});
