import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import api from '../lib/api';
import { useBoardStore } from '../store/boardStore';
import type { BoardSymbol } from '../types';

type Suggestion = {
  symbol_id: number;
  label: string;
  image_path?: string;
};

export function BoardPlayer() {
  const navigate = useNavigate();
  const params = useParams();
  const boardId = useMemo(() => Number(params.id), [params.id]);

  const { currentBoard, fetchBoard, isLoading, error } = useBoardStore();
  const [sentence, setSentence] = useState<BoardSymbol[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);

  useEffect(() => {
    if (!Number.isFinite(boardId)) return;
    fetchBoard(boardId);
  }, [boardId, fetchBoard]);

  const handleSelect = async (symbol: BoardSymbol) => {
    if (symbol.linked_board_id) {
      navigate(`/play/${symbol.linked_board_id}`);
      return;
    }

    setSentence(prev => [...prev, symbol]);

    try {
      const labels = [...sentence, symbol]
        .map(s => s.custom_text || s.symbol.label)
        .join(',');
      const response = await api.get('/analytics/next-symbol', {
        params: { current_symbols: labels, limit: 20, board_id: currentBoard?.id },
      });
      setSuggestions(response.data ?? []);
    } catch {
      setSuggestions([]);
    }
  };

  const symbols = currentBoard?.symbols ?? [];

  if (isLoading) return <div>Loading…</div>;
  if (error) return <div>Error</div>;
  if (!currentBoard) return <div>No board</div>;

  return (
    <div>
      <div aria-label="sentence-strip">
        {sentence.map((s, idx) => (
          <span key={`${s.symbol_id}-${idx}`}>{s.custom_text || s.symbol.label}</span>
        ))}
      </div>

      <div aria-label="board-grid">
        {symbols.map(s => (
          <button key={s.id} type="button" onClick={() => handleSelect(s)}>
            {s.custom_text || s.symbol.label}
          </button>
        ))}
      </div>

      <div aria-label="smartbar">
        {suggestions.map(s => (
          <button
            key={s.symbol_id}
            type="button"
            onClick={() =>
              handleSelect({
                id: -s.symbol_id,
                symbol_id: s.symbol_id,
                position_x: 0,
                position_y: 0,
                is_visible: true,
                custom_text: s.label,
                symbol: { id: s.symbol_id, label: s.label, image_path: s.image_path },
              } as BoardSymbol)
            }
          >
            {s.label}
          </button>
        ))}
      </div>
    </div>
  );
}
