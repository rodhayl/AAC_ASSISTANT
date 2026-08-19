import { useTranslation } from 'react-i18next';
import { useToastStore } from '../store/toastStore';
import type { BoardSymbol } from '../types';
import { SymbolCard } from '../components/board/SymbolCard';
import { useSymbolHunt } from '../hooks/useSymbolHunt';
import { Trophy, Play, ArrowLeft, RotateCcw, Volume2, CheckCircle, XCircle } from 'lucide-react';

export function SymbolHunt() {
  const { t } = useTranslation('games');
  const addToast = useToastStore((state) => state.addToast);
  const {
    playableBoards,
    unplayableBoards,
    selectedBoard,
    gameState,
    setGameState,
    loading,
    round,
    score,
    targetSymbol,
    feedback,
    incorrectSymbolId,
    symbols,
    startGame,
    handleSymbolClick,
    repeatInstruction,
    playAgain,
    voiceEnabled,
  } = useSymbolHunt({ addToast });

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

        {!loading && playableBoards.length === 0 && unplayableBoards.length === 0 ? (
          <div className="text-center py-16 bg-white rounded-xl border border-gray-200">
            <p className="text-gray-500">{t('symbolHunt.noBoards', 'No boards available yet. Ask your teacher to create one.')}</p>
          </div>
        ) : loading ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto" />
          </div>
        ) : (
          <div className="space-y-12">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {playableBoards.map((board) => (
                <button
                  key={board.id}
                  onClick={() => { void startGame(board); }}
                  className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 hover:border-indigo-500 hover:shadow-md transition-all text-left group"
                >
                  <h3 className="text-lg font-semibold text-gray-900 group-hover:text-indigo-600 mb-2">{board.name}</h3>
                  <p className="text-sm text-gray-500 mb-4 line-clamp-2">
                    {board.description || t('symbolHunt.noDescription', 'No description')}
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
                <h2 className="text-xl font-semibold text-gray-500 mb-4">
                  {t('symbolHunt.notEnoughSymbolsTitle', 'Needs more symbols')}
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 opacity-60">
                  {unplayableBoards.map((board) => (
                    <div key={board.id} className="bg-gray-50 p-6 rounded-xl border border-gray-200 text-left cursor-not-allowed relative overflow-hidden">
                      <h3 className="text-lg font-semibold text-gray-500 mb-2">{board.name}</h3>
                      <p className="text-sm text-gray-400 mb-4 line-clamp-2">
                        {board.description || t('symbolHunt.noDescription', 'No description')}
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
            <button onClick={playAgain} className="w-full py-3 bg-indigo-600 text-white rounded-xl font-semibold hover:bg-indigo-700 flex items-center justify-center">
              <RotateCcw className="w-5 h-5 mr-2" />
              {t('symbolHunt.playAgain', 'Play Again')}
            </button>
            <button onClick={() => setGameState('selecting')} className="w-full py-3 bg-white text-gray-700 border border-gray-300 rounded-xl font-semibold hover:bg-gray-50">
              {t('symbolHunt.chooseDifferent', 'Choose Different Board')}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col bg-gray-50">
      <div className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between shadow-sm z-10">
        <div className="flex items-center">
          <button onClick={() => setGameState('selecting')} aria-label={t('symbolHunt.back', 'Back')} className="p-2 hover:bg-gray-100 rounded-full mr-4">
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
          {voiceEnabled && targetSymbol && (
            <button onClick={repeatInstruction} className="p-3 bg-indigo-100 text-indigo-600 rounded-full hover:bg-indigo-200 transition-colors" title={t('symbolHunt.repeat', 'Repeat Instruction')}>
              <Volume2 className="w-6 h-6" />
            </button>
          )}
        </div>
      </div>

      <div className="bg-indigo-600 text-white py-4 text-center text-xl font-medium shadow-md">
        {t('symbolHunt.find', 'Find {{label}}', { label: targetSymbol?.custom_text || targetSymbol?.symbol.label })}
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="grid gap-4 mx-auto max-w-5xl" style={{ gridTemplateColumns: `repeat(${selectedBoard?.grid_cols || 5}, minmax(0, 1fr))` }}>
          {symbols.map((symbol: BoardSymbol) => (
            <div key={symbol.id} className="relative aspect-square w-full min-h-[110px]">
              <SymbolCard
                boardSymbol={symbol}
                onClick={handleSymbolClick}
                ariaLabel={symbol.custom_text || symbol.symbol.label}
              />
              {feedback === 'correct' && symbol.id === targetSymbol?.id && (
                <div className="absolute inset-0 bg-green-500 bg-opacity-30 rounded-xl flex items-center justify-center pointer-events-none border-4 border-green-500">
                  <CheckCircle className="w-12 h-12 text-green-600 drop-shadow-lg" />
                </div>
              )}
              {feedback === 'incorrect' && symbol.id === incorrectSymbolId && (
                <div className="absolute inset-0 bg-red-500 bg-opacity-30 rounded-xl flex items-center justify-center pointer-events-none border-4 border-red-500">
                  <XCircle className="w-12 h-12 text-red-600 drop-shadow-lg" />
                </div>
              )}
              {feedback === 'incorrect' && symbol.id !== targetSymbol?.id && <div className="absolute inset-0 z-10" />}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
