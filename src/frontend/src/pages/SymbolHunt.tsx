import { useTranslation } from 'react-i18next';
import { useToastStore } from '../store/toastStore';
import type { BoardSymbol } from '../types';
import { SymbolCard } from '../components/board/SymbolCard';
import { useSymbolHunt } from '../hooks/useSymbolHunt';
import { Trophy, Play, ArrowLeft, RotateCcw, Volume2, CheckCircle, XCircle } from 'lucide-react';
import { Button } from '../components/ui/button';
import { IconButton } from '../components/ui/icon-button';

import { SectionTitle } from '@/components/ui/SectionTitle';

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
          <div className="inline-flex items-center justify-center w-16 h-16 bg-brand/10 rounded-full mb-4">
            <Trophy className="w-8 h-8 text-brand" />
          </div>
          <h1 className="text-3xl font-bold text-foreground mb-2">{t('symbolHunt.title')}</h1>
          <p className="text-muted-foreground">{t('symbolHunt.selectBoard')}</p>
        </div>

        {!loading && playableBoards.length === 0 && unplayableBoards.length === 0 ? (
          <div className="text-center py-16 bg-surface rounded-xl border border-border">
            <p className="text-muted-foreground">{t('symbolHunt.noBoards')}</p>
          </div>
        ) : loading ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-brand mx-auto" />
          </div>
        ) : (
          <div className="space-y-12">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {playableBoards.map((board) => (
                <button
                  key={board.id}
                  onClick={() => { void startGame(board); }}
                  className="bg-surface p-6 rounded-xl shadow-sm border border-border hover:border-brand hover:shadow-md transition-all text-left group"
                >
                  <SectionTitle as="h3" className="group-hover:text-brand mb-2">{board.name}</SectionTitle>
                  <p className="text-sm text-muted-foreground mb-4 line-clamp-2">
                    {board.description || t('symbolHunt.noDescription')}
                  </p>
                  <div className="flex items-center text-sm text-muted-foreground">
                    <Play className="w-4 h-4 mr-2" />
                    {t('symbolHunt.playNow')}
                  </div>
                </button>
              ))}
            </div>

            {unplayableBoards.length > 0 && (
              <div>
                <h2 className="text-xl font-semibold text-muted-foreground mb-4">
                  {t('symbolHunt.notEnoughSymbolsTitle')}
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 opacity-60">
                  {unplayableBoards.map((board) => (
                    <div key={board.id} className="bg-muted p-6 rounded-xl border border-border text-left cursor-not-allowed relative overflow-hidden">
                      <h3 className="text-lg font-semibold text-muted-foreground mb-2">{board.name}</h3>
                      <p className="text-sm text-muted-foreground mb-4 line-clamp-2">
                        {board.description || t('symbolHunt.noDescription')}
                      </p>
                      <div className="flex items-center text-sm text-muted-foreground">
                        <div className="w-4 h-4 mr-2 flex items-center justify-center rounded-full text-xs font-bold">!</div>
                        {t('symbolHunt.minSymbolsRequired')}
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
          <div className="inline-flex items-center justify-center w-24 h-24 bg-yellow-100 dark:bg-yellow-900/50 rounded-full mb-6 animate-bounce">
            <Trophy className="w-12 h-12 text-yellow-600 dark:text-yellow-300" />
          </div>
          <h2 className="text-3xl font-bold text-foreground mb-2">{t('symbolHunt.greatJob')}</h2>
          <p className="text-xl text-muted-foreground mb-8">
            {t('symbolHunt.scoreMessage', { score })}
          </p>
          <div className="space-y-4">
            <Button onClick={playAgain} className="w-full">
              <RotateCcw />
              {t('symbolHunt.playAgain')}
            </Button>
            <Button variant="outline" onClick={() => setGameState('selecting')} className="w-full">
              {t('symbolHunt.chooseDifferent')}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col bg-background">
      <div className="bg-surface border-b border-border px-6 py-4 flex items-center justify-between shadow-sm z-10">
        <div className="flex items-center">
          <button onClick={() => setGameState('selecting')} aria-label={t('symbolHunt.back')} className="p-2 hover:bg-surface-hover rounded-full mr-4">
            <ArrowLeft className="w-6 h-6 text-muted-foreground" />
          </button>
          <div>
            <h2 className="text-xl font-bold text-foreground">{selectedBoard?.name}</h2>
            <div className="text-sm text-muted-foreground">
              {t('symbolHunt.round', { current: round, total: 10 })}
            </div>
          </div>
        </div>

        <div className="flex items-center space-x-6">
          <div className="text-center">
            <div className="text-sm text-muted-foreground">{t('symbolHunt.score')}</div>
            <div className="text-2xl font-bold text-brand">{score}</div>
          </div>
          {voiceEnabled && targetSymbol && (
            <IconButton label={t('symbolHunt.repeat')} onClick={repeatInstruction} className="p-3 bg-brand/10 text-brand rounded-full hover:bg-brand/20 transition-colors size-12">
              <Volume2 className="w-6 h-6" />
            </IconButton>
          )}
        </div>
      </div>

      <div className="bg-brand text-white py-4 text-center text-xl font-medium shadow-md">
        {t('symbolHunt.find', { label: targetSymbol?.custom_text || targetSymbol?.symbol.label })}
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
                  <CheckCircle className="w-12 h-12 text-green-600 dark:text-green-400 drop-shadow-lg" />
                </div>
              )}
              {feedback === 'incorrect' && symbol.id === incorrectSymbolId && (
                <div className="absolute inset-0 bg-red-500 bg-opacity-30 rounded-xl flex items-center justify-center pointer-events-none border-4 border-red-500">
                  <XCircle className="w-12 h-12 text-red-600 dark:text-red-400 drop-shadow-lg" />
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
