import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import type { DragEndEvent, DragStartEvent } from '@dnd-kit/core';
import { DraggableSymbol } from './DraggableSymbol';
import { DroppableCell } from './DroppableCell';
import type { BoardSymbol } from '../../types';

interface BoardEditorGridProps {
  rows: number;
  cols: number;
  symbols: BoardSymbol[];
  activeSymbol: BoardSymbol | null;
  onDragStart: (event: DragStartEvent) => void;
  onDragEnd: (event: DragEndEvent) => void;
  onAddSymbol: (x: number, y: number) => void;
  onRemoveSymbol: (id: number) => void;
  onEditSymbol: (symbol: BoardSymbol) => void;
}

export function BoardEditorGrid({
  rows,
  cols,
  symbols,
  activeSymbol,
  onDragStart,
  onDragEnd,
  onAddSymbol,
  onRemoveSymbol,
  onEditSymbol,
}: BoardEditorGridProps) {
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));

  return (
    <div className="flex-1 bg-gray-100 dark:bg-gray-800 rounded-xl p-8 overflow-auto">
      <DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd}>
        <div
          className="grid gap-4 mx-auto max-w-4xl"
          style={{
            gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
            gridTemplateRows: `repeat(${rows}, minmax(0, 1fr))`,
          }}
        >
          {Array.from({ length: rows }).map((_, row) =>
            Array.from({ length: cols }).map((_, col) => {
              const symbol = symbols.find((item) => item.position_x === col && item.position_y === row);
              return (
                <DroppableCell
                  key={`${col}-${row}`}
                  x={col}
                  y={row}
                  onAddClick={() => onAddSymbol(col, row)}
                >
                  {symbol && (
                    <DraggableSymbol
                      boardSymbol={symbol}
                      onRemove={onRemoveSymbol}
                      onEdit={onEditSymbol}
                    />
                  )}
                </DroppableCell>
              );
            }),
          )}
        </div>
        <DragOverlay>
          {activeSymbol ? (
            <div className="w-32 h-32">
              <DraggableSymbol boardSymbol={activeSymbol} isOverlay />
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>
    </div>
  );
}
