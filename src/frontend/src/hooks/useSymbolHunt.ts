import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../store/authStore';
import { tts } from '../lib/tts';
import api from '../lib/api';
import type { Board, BoardSymbol } from '../types';
import { getUniquePlayableSymbols } from '../lib/symbols';
import type { ToastType } from '../store/toastStore';

interface UseSymbolHuntOptions {
  addToast: (message: string, type?: ToastType) => void;
}

export function useSymbolHunt({ addToast }: UseSymbolHuntOptions) {
  const { t } = useTranslation('games');
  const user = useAuthStore((state) => state.user);
  const [boards, setBoards] = useState<Board[]>([]);
  const [selectedBoard, setSelectedBoard] = useState<Board | null>(null);
  const [gameState, setGameState] = useState<'selecting' | 'playing' | 'finished'>('selecting');
  const [loading, setLoading] = useState(false);
  const [round, setRound] = useState(0);
  const [score, setScore] = useState(0);
  const [targetSymbol, setTargetSymbol] = useState<BoardSymbol | null>(null);
  const [feedback, setFeedback] = useState<'correct' | 'incorrect' | null>(null);
  const [symbols, setSymbols] = useState<BoardSymbol[]>([]);
  const gameGenerationRef = useRef(0);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  const clearTimers = useCallback(() => {
    timersRef.current.forEach((timer) => clearTimeout(timer));
    timersRef.current = [];
  }, []);

  const schedule = useCallback((callback: () => void, delay: number) => {
    const timer = setTimeout(() => {
      timersRef.current = timersRef.current.filter((current) => current !== timer);
      callback();
    }, delay);
    timersRef.current.push(timer);
  }, []);

  const playableBoards = useMemo(
    () => boards.filter((board) => (board.playable_symbols_count ?? 0) >= 2),
    [boards],
  );
  const unplayableBoards = useMemo(
    () => boards.filter((board) => (board.playable_symbols_count ?? 0) < 2),
    [boards],
  );

  useEffect(() => {
    if (!user?.id) return;
    let cancelled = false;

    const fetchBoards = async () => {
      try {
        setLoading(true);
        // The unfiltered list includes the user's boards and public boards;
        // assigned student boards are added below as a separate scoped request.
        const response = await api.get('/boards/');
        let allBoards = response.data as Board[];

        if (user.user_type === 'student') {
          try {
            const assignedResponse = await api.get('/boards/assigned', {
              params: { student_id: user.id },
            });
            allBoards = [...allBoards, ...(assignedResponse.data as Board[])];
          } catch (error) {
            console.warn('Failed to fetch assigned boards', error);
          }
        }

        if (cancelled) return;
        setBoards(Array.from(new Map(allBoards.map((board) => [board.id, board])).values()));
      } catch (error) {
        if (!cancelled) console.error('Failed to fetch boards:', error);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void fetchBoards();
    return () => {
      cancelled = true;
    };
  }, [user?.id, user?.user_type]);

  const nextRound = useCallback((currentSymbols: BoardSymbol[]) => {
    clearTimers();
    const generation = gameGenerationRef.current;
    const target = currentSymbols[Math.floor(Math.random() * currentSymbols.length)];
    if (!target) return;
    setTargetSymbol(target);
    setFeedback(null);
    const label = target.custom_text || target.symbol.label;
    if (user?.settings?.voice_mode_enabled !== false) {
      schedule(() => {
        if (generation === gameGenerationRef.current) {
          tts.enqueue(t('symbolHunt.find', 'Find {{label}}', { label }));
        }
      }, 500);
    }
  }, [clearTimers, schedule, t, user?.settings?.voice_mode_enabled]);

  const startGame = useCallback(async (board: Board) => {
    const generation = ++gameGenerationRef.current;
    clearTimers();
    try {
      setLoading(true);
      const response = await api.get(`/boards/${board.id}`, {
        params: { skip_translation: true },
      });
      const fullBoard = response.data as Board;
      if (generation !== gameGenerationRef.current) return;
      const uniqueSymbols = getUniquePlayableSymbols(fullBoard.symbols);
      if (uniqueSymbols.length < 2) {
        addToast(
          t('symbolHunt.notEnoughSymbols', 'This board needs at least 2 unique symbols to play.'),
          'error',
        );
        return;
      }

      setSymbols(uniqueSymbols);
      setSelectedBoard(fullBoard);
      setGameState('playing');
      setScore(0);
      setRound(1);
      nextRound(uniqueSymbols);
    } catch (error) {
      if (generation === gameGenerationRef.current) {
        console.error('Failed to start game:', error);
      }
    } finally {
      if (generation === gameGenerationRef.current) setLoading(false);
    }
  }, [addToast, clearTimers, nextRound, t]);

  const handleSymbolClick = useCallback((symbol: BoardSymbol) => {
    if (feedback || !targetSymbol) return;
    const clickedLabel = symbol.custom_text || symbol.symbol.label;
    const targetLabel = targetSymbol.custom_text || targetSymbol.symbol.label;

    if (clickedLabel !== targetLabel) {
      setFeedback('incorrect');
      if (user?.settings?.voice_mode_enabled !== false) {
        tts.enqueue(t('symbolHunt.tryAgain', 'Try again'));
      }
      const generation = gameGenerationRef.current;
      schedule(() => {
        if (generation === gameGenerationRef.current) setFeedback(null);
      }, 1000);
      return;
    }

    setFeedback('correct');
    setScore((currentScore) => currentScore + 1);
    Promise.resolve(api.post('/analytics/usage', {
      symbols: [{
        id: symbol.symbol.id,
        label: clickedLabel,
        category: symbol.symbol.category,
      }],
      context_topic: 'symbol_hunt',
    })).catch((error) => console.error('Failed to log symbol usage:', error));

    if (user?.settings?.voice_mode_enabled !== false) {
      tts.enqueue(t('symbolHunt.correct', 'Correct!'));
    }

    const generation = gameGenerationRef.current;
    schedule(() => {
        if (generation !== gameGenerationRef.current) return;
        if (round >= 10) {
          setGameState('finished');
        } else {
          setRound((currentRound) => currentRound + 1);
          nextRound(symbols);
        }
    }, 1500);
  }, [feedback, nextRound, round, schedule, symbols, t, targetSymbol, user?.settings?.voice_mode_enabled]);

  const repeatInstruction = useCallback(() => {
    if (!targetSymbol || user?.settings?.voice_mode_enabled === false) return;
    const label = targetSymbol.custom_text || targetSymbol.symbol.label;
    tts.enqueue(t('symbolHunt.find', 'Find {{label}}', { label }));
  }, [t, targetSymbol, user?.settings?.voice_mode_enabled]);

  const playAgain = useCallback(() => {
    ++gameGenerationRef.current;
    clearTimers();
    setGameState('playing');
    setScore(0);
    setRound(1);
    nextRound(symbols);
  }, [clearTimers, nextRound, symbols]);

  const changeGameState = useCallback((nextState: 'selecting' | 'playing' | 'finished') => {
    if (nextState === 'selecting') {
      ++gameGenerationRef.current;
      clearTimers();
    }
    setGameState(nextState);
  }, [clearTimers]);

  useEffect(() => () => {
    ++gameGenerationRef.current;
    clearTimers();
  }, [clearTimers]);

  return {
    boards,
    playableBoards,
    unplayableBoards,
    selectedBoard,
    gameState,
    setGameState: changeGameState,
    loading,
    round,
    score,
    targetSymbol,
    feedback,
    symbols,
    startGame,
    handleSymbolClick,
    repeatInstruction,
    playAgain,
    voiceEnabled: user?.settings?.voice_mode_enabled !== false,
  };
}
