import { Bot, Edit, Grid as GridIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { SymbolMessageEditor } from '../SymbolMessageEditor';
import { SymbolImage } from '../common/SymbolImage';

export interface LearningMessage {
  role: 'user' | 'assistant';
  content: string;
  symbolImages?: Array<{
    id?: number;
    label: string;
    image_path?: string;
    category?: string;
  }>;
}

interface LearningMessageListProps {
  messages: LearningMessage[];
  editingMessageIndex: number | null;
  onEditMessage: (index: number) => void;
  onUpdateSymbols: (symbols: Array<{
    id: number;
    label: string;
    image_path?: string;
    category?: string;
  }>) => Promise<void>;
  onCancelEdit: () => void;
}

export function LearningMessageList({
  messages,
  editingMessageIndex,
  onEditMessage,
  onUpdateSymbols,
  onCancelEdit,
}: LearningMessageListProps) {
  const { t } = useTranslation('learning');

  return (
    <>
      {messages.map((message, index) => {
        const content = message.content || '';
        const symbolData = message.symbolImages;
        const isSymbolMessage = Boolean(symbolData && symbolData.length > 0);
        const isEditing = editingMessageIndex === index;

        if (isEditing && isSymbolMessage && symbolData) {
          return (
            <div key={index} className="flex justify-end">
              <div className="max-w-[80%] w-full">
                <SymbolMessageEditor
                  message={{
                    content: message.content,
                    symbolImages: symbolData.map((symbol, symbolIndex) => ({
                        id: symbol.id ?? symbolIndex,
                        label: symbol.label,
                        image_path: symbol.image_path,
                        category: symbol.category,
                      })),
                  }}
                  onUpdate={async (newSymbols) => {
                    await onUpdateSymbols(newSymbols);
                    onCancelEdit();
                  }}
                  onCancel={onCancelEdit}
                />
              </div>
            </div>
          );
        }

        return (
          <div
            key={index}
            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'} group relative`}
          >
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                message.role === 'user'
                  ? 'bg-indigo-600 text-white rounded-br-none'
                  : 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded-bl-none'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center opacity-75 text-xs">
                  {message.role === 'assistant' && <Bot className="w-3 h-3 mr-1" />}
                  {isSymbolMessage && <GridIcon className="w-3 h-3 mr-1" />}
                  <span>{message.role === 'user' ? t('messageRole.user') : t('messageRole.assistant')}</span>
                </div>
                {message.role === 'user' && isSymbolMessage && (
                  <button
                    onClick={() => onEditMessage(index)}
                    className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-white/20 rounded"
                    title={t('editSymbols', 'Edit symbols')}
                    aria-label={t('editSymbolMessage', 'Edit symbol message')}
                  >
                    <Edit className="w-3 h-3" />
                  </button>
                )}
              </div>

              {symbolData && symbolData.length > 0 && (
                <div className="flex gap-1 mb-2 flex-wrap">
                  {symbolData.map((symbol, symbolIndex) => (
                    <div
                      key={symbolIndex}
                      className="w-8 h-8 rounded bg-white/10 overflow-hidden border border-white/20"
                      title={symbol.label}
                    >
                      {symbol.image_path ? (
                        <SymbolImage
                          imagePath={symbol.image_path}
                          alt={symbol.label}
                          className="w-full h-full object-contain"
                        />
                      ) : (
                        <GridIcon className="w-4 h-4 m-auto mt-2 text-white/40" />
                      )}
                    </div>
                  ))}
                </div>
              )}

              <p className="whitespace-pre-wrap">{content}</p>
            </div>
          </div>
        );
      })}
    </>
  );
}
