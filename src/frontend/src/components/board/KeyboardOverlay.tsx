import React, { useState, useEffect, useRef, useMemo } from 'react';
import { X, Volume2, History, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface KeyboardOverlayProps {
  isOpen: boolean;
  onClose: () => void;
  onSpeak: (text: string) => void;
}

// Simple trie-based or frequency-based word prediction could go here.
// For now, let's use a static list of common core words + recent history.
// Lists are per-language so predictions match what the user actually types.
const COMMON_WORDS: Record<string, string[]> = {
  en: [
    "I", "you", "want", "go", "help", "more", "stop", "like", "eat", "drink",
    "play", "read", "watch", "yes", "no", "good", "bad", "happy", "sad"
  ],
  es: [
    "yo", "tú", "quiero", "ir", "ayuda", "más", "parar", "gusta", "comer", "beber",
    "jugar", "leer", "ver", "sí", "no", "bueno", "malo", "feliz", "triste"
  ],
};

export function KeyboardOverlay({ isOpen, onClose, onSpeak }: KeyboardOverlayProps) {
  const { t, i18n } = useTranslation('boards');
  const [text, setText] = useState('');
  const [history, setHistory] = useState<string[]>(() => {
    const saved = localStorage.getItem('aac_phrase_history');
    if (!saved) return [];
    try {
      const parsed = JSON.parse(saved);
      return Array.isArray(parsed) ? parsed.filter((item) => typeof item === 'string') : [];
    } catch {
      // Corrupt history must never crash the overlay.
      return [];
    }
  });
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const suggestions = useMemo(() => {
    if (!text.trim()) {
        return [];
    }
    const words = text.split(' ');
    const lastWord = words[words.length - 1].toLowerCase();
    
    if (lastWord.length === 0) {
        return [];
    }

    const baseLang = (i18n.language || 'en').split('-')[0].toLowerCase();
    const wordsForLang = COMMON_WORDS[baseLang] || COMMON_WORDS.en;
    const matches = wordsForLang.filter(w => w.toLowerCase().startsWith(lastWord));
    return matches.slice(0, 5);
  }, [text, i18n.language]);

  useEffect(() => {
    if (!isOpen) return;

    const focusTimer = window.setTimeout(() => inputRef.current?.focus(), 100);
    return () => window.clearTimeout(focusTimer);
  }, [isOpen]);

  // Close on Escape so keyboard users are never trapped in the modal.
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  const handleSpeak = () => {
    if (text.trim()) {
      onSpeak(text);
      
      // Save to history
      const newHistory = [text, ...history.filter(h => h !== text)].slice(0, 10);
      setHistory(newHistory);
      try {
        localStorage.setItem('aac_phrase_history', JSON.stringify(newHistory));
      } catch {
        // Storage may be unavailable (private mode/quota); the in-memory
        // history still works for this session.
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSpeak();
    }
  };

  const insertSuggestion = (word: string) => {
      const words = text.split(' ');
      words.pop(); // remove partial
      words.push(word);
      setText(words.join(' ') + ' ');
      inputRef.current?.focus();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 backdrop-blur-sm p-4 animate-in fade-in duration-200" role="presentation">
      <div
        className="w-full max-w-2xl bg-surface rounded-2xl border border-border shadow-2xl overflow-hidden flex flex-col animate-in slide-in-from-bottom-10 duration-300 h-[80vh] sm:h-auto"
        data-mobile-dialog="true"
        role="dialog"
        aria-modal="true"
        aria-labelledby="keyboard-overlay-title"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h3 id="keyboard-overlay-title" className="text-lg font-bold text-primary flex items-center gap-2">
            {t('typeToSpeak', 'Type to Speak')}
          </h3>
          <button 
            onClick={onClose}
            className="modal-close p-2 rounded-lg text-secondary hover:bg-surface-hover transition-colors"
            aria-label={t('close', 'Close')}
            data-touch-target="true"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Input Area */}
        <div className="p-4 flex-1 flex flex-col min-h-0">
          <textarea
            ref={inputRef}
            aria-label={t('typeHere', 'Type something here...')}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t('typeHere', 'Type something here...')}
            className="w-full flex-1 p-4 text-lg sm:text-2xl rounded-xl border-2 border-border focus:border-indigo-500 focus:ring-0 bg-background text-primary resize-none"
          />
          
          {/* Suggestions */}
          {suggestions.length > 0 && (
            <div className="flex gap-2 mt-2 overflow-x-auto pb-2">
                {suggestions.map(s => (
                    <button
                        key={s}
                        onClick={() => insertSuggestion(s)}
                        className="px-3 py-2 bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 rounded-lg text-sm font-medium hover:bg-indigo-100 dark:hover:bg-indigo-900/50 transition-colors flex items-center gap-1"
                    >
                        <Sparkles className="w-3 h-3" />
                        {s}
                    </button>
                ))}
            </div>
          )}
        </div>

        {/* History & Actions */}
        <div className="p-4 border-t border-border bg-surface/60">
             {/* Recent History */}
            {history.length > 0 && (
                <div className="mb-4">
                    <div className="text-xs font-semibold text-muted uppercase mb-2 flex items-center gap-1">
                        <History className="w-3 h-3" />
                        {t('recent', 'Recent')}
                    </div>
                    <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
                        {history.map((phrase, i) => (
                            <button
                                key={i}
                                onClick={() => {
                                    setText(phrase);
                                    inputRef.current?.focus();
                                }}
                                className="whitespace-nowrap px-3 py-1.5 bg-surface border border-border rounded-full text-sm text-secondary hover:border-indigo-500 transition-colors"
                                data-touch-target="true"
                            >
                                {phrase}
                            </button>
                        ))}
                    </div>
                </div>
            )}

            <div className="flex justify-between items-center">
                <div className="text-sm text-muted hidden sm:block">
                    {t('pressEnterToSpeak', 'Press Enter to speak')}
                </div>
                <div className="flex gap-3 ml-auto w-full sm:w-auto">
                    <button
                        onClick={() => setText('')}
                        className="flex-1 sm:flex-none px-4 py-2 text-secondary hover:bg-surface-hover rounded-lg font-medium transition-colors"
                        data-touch-target="true"
                    >
                        {t('clear', 'Clear')}
                    </button>
                    <button
                        onClick={handleSpeak}
                        disabled={!text.trim()}
                        className="flex-1 sm:flex-none flex items-center justify-center gap-2 px-6 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-bold shadow-lg shadow-indigo-500/30 transition-all transform active:scale-95 disabled:opacity-50 disabled:shadow-none disabled:cursor-not-allowed"
                        data-touch-target="true"
                    >
                        <Volume2 className="w-5 h-5" />
                        {t('speak', 'Speak')}
                    </button>
                </div>
            </div>
        </div>
      </div>
    </div>
  );
}
