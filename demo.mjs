import { indexBoardSymbols, getBoardCapacity } from './historical/frontend/src/lib/boardGrid.ts';
import { glossSymbolUtterance } from './historical/frontend/src/lib/gloss.ts';
import { dedupeLearningSymbols, getUniquePlayableSymbols } from './historical/frontend/src/lib/symbols.ts';

// Synthetic in-memory inputs only. This is not the complete AAC application.
const labels = ['I', 'want', 'water'];
const boardSymbols = labels.map((label, id) => ({
  id, symbol_id: id, position_x: id, position_y: 0, size: 1,
  is_visible: true,
  symbol: { id, label, category: 'sample', language: 'en', is_builtin: false, created_at: '2026-08-31' },
}));
const indexed = indexBoardSymbols(boardSymbols);
console.log('AAC Assistant — historical logic sample (31 August 2026)');
console.log(`Board capacity: ${getBoardCapacity({ grid_rows: 1, grid_cols: 3 })}`);
console.log('Cells:', [...indexed.keys()].join(', '));
console.log('Phrase:', glossSymbolUtterance(boardSymbols.map(item => item.symbol)));
console.log('Playable symbols:', getUniquePlayableSymbols(boardSymbols).length);
console.log('Unique library labels:', dedupeLearningSymbols([
  { id: 1, label: 'water', category: 'sample' },
  { id: 2, label: ' WATER ', category: 'sample' },
]).length);
