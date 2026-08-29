import { useState, useEffect, useRef, useCallback } from 'react';
import { X, Mic } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '../ui/button';
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from '../ui/dialog';

interface PartnerOverlayProps {
  isOpen: boolean;
  onClose: () => void;
}

export function PartnerOverlay({ isOpen, onClose }: PartnerOverlayProps) {
  const { t, i18n } = useTranslation('boards');
  const [transcript, setTranscript] = useState('');
  const [isListening, setIsListening] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const recognitionRef = useRef<any>(null);
  const isMounted = useRef(false);

  useEffect(() => {
    isMounted.current = true;
    return () => { isMounted.current = false; };
  }, []);

  const cleanupRecognition = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
  }, []);

  const stopListening = useCallback(() => {
    cleanupRecognition();
    if (isMounted.current) {
      setIsListening(false);
    }
  }, [cleanupRecognition]);

  const startListening = useCallback(() => {
    if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
      setTranscript(t('speechNotSupported'));
      return;
    }

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognitionRef.current = recognition;

    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = i18n.language || 'es-ES';

    recognition.onstart = () => {
        if (isMounted.current) setIsListening(true);
    };
    recognition.onend = () => {
        if (isMounted.current) setIsListening(false);
    };
    recognition.onerror = () => {
      if (isMounted.current) {
        setIsListening(false);
        setTranscript(t('speechNotAvailable'));
      }
    };
    
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    recognition.onresult = (event: any) => {
      let finalTranscript = '';
      for (let i = event.resultIndex; i < event.results.length; ++i) {
          finalTranscript += event.results[i][0].transcript;
      }
      if (isMounted.current) setTranscript(finalTranscript);
    };

    recognition.start();
  }, [i18n.language, t]);

  useEffect(() => {
    if (isOpen) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      startListening();
    } else {
      stopListening();
      setTranscript('');
    }
    return () => cleanupRecognition();
  }, [isOpen, startListening, stopListening, cleanupRecognition]);

  if (!isOpen) return null;

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent
        showCloseButton={false}
        className="max-w-3xl p-6 text-center"
      >
        <button 
            onClick={onClose}
            className="absolute top-4 right-4 p-2 rounded-full bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600"
            aria-label={t('close')}
        >
            <X className="w-6 h-6" />
        </button>

        <div className="mb-6">
            <div className={`p-4 rounded-full inline-flex items-center justify-center ${isListening ? 'bg-red-100 text-red-600 animate-pulse' : 'bg-gray-100 text-gray-500'}`}>
                <Mic className="w-12 h-12" />
            </div>
            <DialogTitle className="mt-4 text-xl font-semibold text-gray-900 dark:text-gray-100">
                {isListening ? t('listening') : t('paused')}
            </DialogTitle>
        </div>

        <div className="w-full min-h-[200px] bg-gray-50 dark:bg-gray-900/50 rounded-xl p-6 flex items-center justify-center border-2 border-dashed border-gray-200 dark:border-gray-700 overflow-y-auto max-h-[60vh]">
            {transcript ? (
                <p className="text-3xl md:text-4xl font-bold text-gray-800 dark:text-gray-100 leading-relaxed">
                    "{transcript}"
                </p>
            ) : (
                <p className="text-gray-400 italic text-xl dark:text-gray-500">
                    {t('waitingForSpeech')}
                </p>
            )}
        </div>
        
        <div className="mt-6 flex gap-4">
             <Button
                onClick={isListening ? stopListening : startListening}
                className="px-6"
                variant={isListening ? 'destructive' : 'default'}
             >
                {isListening ? t('stopListening') : t('startListening')}
             </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
