import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../store/authStore';
import { tts } from '../lib/tts';
import { useToastStore } from '../store/toastStore';
import api from '../lib/api';
import type { Board, BoardSymbol } from '../types/index';
import { SymbolCard } from '../components/board/SymbolCard';
import { Trophy, Play, ArrowLeft, RotateCcw, Volume2, CheckCircle } from 'lucide-react';

export function SymbolHunt() {
  const { t } = useTranslation('games');
  const { user } = useAuthStore();
  const { addToast } = useToastStore();

  const [boards, setBoards] = useState<Board[]>([]);
  const [selectedBoard, setSelectedBoard] = useState<Board | null>(null);
  const [gameState, setGameState] = useState<'selecting' | 'playing' | 'finished'>('selecting');
  const [loading, setLoading] = useState(false);

  // Game State
  const [round, setRound] = useState(0);
  const [score, setScore] = useState(0);
  const [targetSymbol, setTargetSymbol] = useState<BoardSymbol | null>(null);
  const [feedback, setFeedback] = useState<'correct' | 'incorrect' | null>(null);
  const [symbols, setSymbols] = useState<BoardSymbol[]>([]);

  // console.log(`Render state - GameState: ${gameState}, Board: ${selectedBoard?.id}, Symbols: ${symbols.length}`);

  const playableBoards = boards.filter(b => (b.playable_symbols_count ?? 0) >= 2);
  const unplayableBoards = boards.filter(b => (b.playable_symbols_count ?? 0) < 2);

  useEffect(() => {
    const fetchBoards = async () => {
      try {
        setLoading(true);
        const response = await api.get('/boards/', {
          params: { user_id: user?.id }
        });
        
        let allBoards = response.data;

        // Also fetch assigned boards for students
        if (user?.user_type === 'student') {
          try {
            const assignedRes = await api.get('/boards/assigned', {
              params: { student_id: user.id }
            });
            allBoards = [...allBoards, ...assignedRes.data];
          } catch (err) {
            console.warn('Failed to fetch assigned boards', err);
          }
        }

        // Deduplicate boards by ID
        const uniqueBoards = Array.from(new Map(allBoards.map((b: Board) => [b.id, b])).values());
        setBoards(uniqueBoards as Board[]);
      } catch (error) {
        console.error('Failed to fetch boards:', error);
      } finally {
        setLoading(false);
      }
    };

    if (user?.id) {
      fetchBoards();
    }
  }, [user?.id, user?.user_type]);

  const startGame = async (board: Board) => {
    // console.log('Starting game with board:', board.id);
    try {
      setLoading(true);
      // Fetch full board details with symbols
      const response = await api.get(`/boards/${board.id}`, {
        params: { skip_translation: true }
      });
      // console.log('Full board fetched:', response.data);
      const fullBoard = response.data;
      
      const playableSymbols = fullBoard.symbols.filter((s: BoardSymbol) => s.is_visible && (s.custom_text || s.symbol.label));
      // console.log('Playable symbols:', playableSymbols.length);
      
      // Deduplicate symbols by their label/custom_text to avoid confusing gameplay
      // When board has same symbol multiple times, keep only one instance
      const uniqueSymbolsMap = new Map<string, BoardSymbol>();
      for (const sym of playableSymbols) {
        const label = sym.custom_text || sym.symbol.label;
        if (!uniqueSymbolsMap.has(label)) {
          uniqueSymbolsMap.set(label, sym);
        }
      }
      const uniqueSymbols = Array.from(uniqueSymbolsMap.values());
      // console.log('Unique symbols:', uniqueSymbols.length);
      
      if (uniqueSymbols.length < 2) {
        console.warn('Not enough symbols');
        addToast(t('symbolHunt.notEnoughSymbols', 'This board needs at least 2 unique symbols to play.'), 'error');
        setLoading(false);
        return;
      }

      setSymbols(uniqueSymbols);
      setSelectedBoard(fullBoard);
      setGameState('playing');
      setScore(0);
      setRound(1);
      nextRound(uniqueSymbols);
    } catch (error) {
      console.error('Failed to start game:', error);
    } finally {
      setLoading(false);
    }
  };

  const nextRound = (currentSymbols: BoardSymbol[]) => {
    const randomIndex = Math.floor(Math.random() * currentSymbols.length);
    const target = currentSymbols[randomIndex];
    setTargetSymbol(target);
    setFeedback(null);
    
    // Speak the target
    const label = target.custom_text || target.symbol.label;
    if (user?.settings?.voice_mode_enabled !== false) {
      setTimeout(() => {
        tts.enqueue(t('symbolHunt.find', 'Find {{label}}', { label }));
      }, 500);
    }
  };

  const handleSymbolClick = (symbol: BoardSymbol) => {
    if (feedback) return; // Prevent clicks during feedback

    // Compare by label/custom_text instead of ID to handle duplicate symbols gracefully
    const clickedLabel = symbol.custom_text || symbol.symbol.label;
    const targetLabel = targetSymbol?.custom_text || targetSymbol?.symbol.label;
    
    if (clickedLabel === targetLabel) {
      setFeedback('correct');
      setScore(s => s + 1);

      // Log successful selection to personalize future suggestions
      Promise.resolve(
        api.post('/analytics/usage', {
          symbols: [
            {
              id: symbol.symbol.id,
              label: clickedLabel,
              category: symbol.symbol.category,
            },
          ],
          context_topic: 'symbol_hunt',
        })
      ).catch(err => console.error('Failed to log symbol usage:', err));
      
      if (user?.settings?.voice_mode_enabled !== false) {
        tts.enqueue(t('symbolHunt.correct', 'Correct!'));
      }
      
      setTimeout(() => {
        if (round >= 10) {
          setGameState('finished');
        } else {
          setRound(r => r + 1);
          nextRound(symbols);
        }
      }, 1500);
    } else {
      setFeedback('incorrect');
      if (user?.settings?.voice_mode_enabled !== false) {
        tts.enqueue(t('symbolHunt.tryAgain', 'Try again'));
      }
      setTimeout(() => setFeedback(null), 1000);
    }
  };

  const repeatInstruction = () => {
    if (targetSymbol && user?.settings?.voice_mode_enabled !== false) {
      const label = targetSymbol.custom_text || targetSymbol.symbol.label;
      tts.enqueue(t('symbolHunt.find', 'Find {{label}}', { label }));
    }
  };

  if (gameState === 'selecting') {
    return (
      <div className="max-w-4xl mx-auto p-6">
        <div className="mb-8 text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-indigo-100 rounded-full mb-4">
            <Trophy className="w-8 h-8 text-indigo-600" />
          </div>
          <h1 className="text-3xl font-bold text-gray-900 mb-2">{t('symbolHunt.title', 'Symbol Hunt')}</h1>
          <p className="text-gray-600">{t('symbolHunt.selectBoard', 'Select a board to start playing')}</p>
        </div>

        {loading ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"></div>
          </div>
        ) : (
          <div className="space-y-12">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {playableBoards.map(board => (
                <button
                  key={board.id}
                  onClick={() => startGame(board)}
                  className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 hover:border-indigo-500 hover:shadow-md transition-all text-left group"
                >
                  <h3 className="text-lg font-semibold text-gray-900 group-hover:text-indigo-600 mb-2">
                    {board.name}
                  </h3>
                  <p className="text-sm text-gray-500 mb-4 line-clamp-2">
                    {board.description || t('common.noDescription', 'No description')}
                  </p>
                  <div className="flex items-center text-sm text-gray-400">
                    <Play className="w-4 h-4 mr-2" />
                    {t('symbolHunt.playNow', 'Play Now')}
                  </div>
                </button>
              ))}
            </div>

            {unplayableBoards.length > 0 && (
              <div>
                <h2 className="text-xl font-semibold text-gray-500 mb-4">{t('symbolHunt.notEnoughSymbolsTitle', 'Needs more symbols')}</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 opacity-60">
                  {unplayableBoards.map(board => (
                    <div
                      key={board.id}
                      className="bg-gray-50 p-6 rounded-xl border border-gray-200 text-left cursor-not-allowed relative overflow-hidden"
                    >
                      <h3 className="text-lg font-semibold text-gray-500 mb-2">
                        {board.name}
                      </h3>
                      <p className="text-sm text-gray-400 mb-4 line-clamp-2">
                        {board.description || t('common.noDescription', 'No description')}
                      </p>
                      <div className="flex items-center text-sm text-gray-400">
                        <div className="w-4 h-4 mr-2 flex items-center justify-center rounded-full text-xs font-bold">!</div>
                        {t('symbolHunt.minSymbolsRequired', 'At least 2 symbols required')}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  if (gameState === 'finished') {
    return (
      <div className="max-w-md mx-auto p-6 text-center pt-20">
        <div className="mb-8">
          <div className="inline-flex items-center justify-center w-24 h-24 bg-yellow-100 rounded-full mb-6 animate-bounce">
            <Trophy className="w-12 h-12 text-yellow-600" />
          </div>
          <h2 className="text-3xl font-bold text-gray-900 mb-2">{t('symbolHunt.greatJob', 'Great Job!')}</h2>
          <p className="text-xl text-gray-600 mb-8">
            {t('symbolHunt.scoreMessage', 'You found {{score}} symbols!', { score })}
          </p>
          <div className="space-y-4">
            <button
              onClick={() => {
                setGameState('playing');
                setScore(0);
                setRound(1);
                nextRound(symbols);
              }}
              className="w-full py-3 bg-indigo-600 text-white rounded-xl font-semibold hover:bg-indigo-700 flex items-center justify-center"
            >
              <RotateCcw className="w-5 h-5 mr-2" />
              {t('symbolHunt.playAgain', 'Play Again')}
            </button>
            <button
              onClick={() => setGameState('selecting')}
              className="w-full py-3 bg-white text-gray-700 border border-gray-300 rounded-xl font-semibold hover:bg-gray-50"
            >
              {t('symbolHunt.chooseDifferent', 'Choose Different Board')}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col bg-gray-50">
      {/* Game Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between shadow-sm z-10">
        <div className="flex items-center">
          <button
            onClick={() => setGameState('selecting')}
            className="p-2 hover:bg-gray-100 rounded-full mr-4"
          >
            <ArrowLeft className="w-6 h-6 text-gray-500" />
          </button>
          <div>
            <h2 className="text-xl font-bold text-gray-900">{selectedBoard?.name}</h2>
            <div className="text-sm text-gray-500">
              {t('symbolHunt.round', 'Round {{current}}/{{total}}', { current: round, total: 10 })}
            </div>
          </div>
        </div>
        
        <div className="flex items-center space-x-6">
          <div className="text-center">
            <div className="text-sm text-gray-500">{t('symbolHunt.score', 'Score')}</div>
            <div className="text-2xl font-bold text-indigo-600">{score}</div>
          </div>
          {user?.settings?.voice_mode_enabled !== false && (
            <button
              onClick={repeatInstruction}
              className="p-3 bg-indigo-100 text-indigo-600 rounded-full hover:bg-indigo-200 transition-colors"
              title={t('symbolHunt.repeat', 'Repeat Instruction')}
            >
              <Volume2 className="w-6 h-6" />
            </button>
          )}
        </div>
      </div>

      {/* Target Instruction */}
      <div className="bg-indigo-600 text-white py-4 text-center text-xl font-medium shadow-md">
        {t('symbolHunt.find', 'Find {{label}}', { label: targetSymbol?.custom_text || targetSymbol?.symbol.label })}
      </div>

      {/* Game Board */}
      <div className="flex-1 overflow-y-auto p-6">
        <div 
          className="grid gap-4 mx-auto max-w-5xl"
          style={{
            gridTemplateColumns: `repeat(${selectedBoard?.grid_cols || 5}, minmax(0, 1fr))`
          }}
        >
          {symbols.map((symbol) => (
            <div key={symbol.id} className="relative aspect-square w-full min-h-[110px]">
              <SymbolCard
                boardSymbol={symbol}
                onClick={() => handleSymbolClick(symbol)}
              />
              {/* Feedback Overlays */}
              {feedback === 'correct' && symbol.id === targetSymbol?.id && (
                <div className="absolute inset-0 bg-green-500 bg-opacity-30 rounded-xl flex items-center justify-center pointer-events-none border-4 border-green-500">
                  <CheckCircle className="w-12 h-12 text-green-600 drop-shadow-lg" />
                </div>
              )}
              {feedback === 'incorrect' && symbol.id !== targetSymbol?.id && (
                <div className="absolute inset-0 z-10" /> /* Block clicks on other symbols briefly? No, handled by feedback state check */
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
