import type { LearningSymbolItem } from '../types';

// The picker pool of canonical topics. Keys must match the `topics.*` keys in
// the learning locale files and the backend COMMON_TOPICS list.
export const COMMON_TOPIC_KEYS = [
  'general',
  'daily',
  'food',
  'school',
  'emotions',
  'travel',
  'hobbies',
  'health',
  'shopping',
] as const;

export type CommonTopicKey = (typeof COMMON_TOPIC_KEYS)[number];

// The English topic value sent to the backend when a session starts. Kept in
// sync with the backend's COMMON_TOPICS / welcome-message topic_labels so the
// welcome message localizes correctly for every picker topic.
export const TOPIC_CANONICAL_NAME: Record<CommonTopicKey, string> = {
  general: 'general conversation',
  daily: 'daily routines',
  food: 'food and dining',
  school: 'school and education',
  emotions: 'emotions and feelings',
  travel: 'travel and transport',
  hobbies: 'hobbies and play',
  health: 'health and body',
  shopping: 'shopping',
};

// Emoji fallback used when no pictogram symbol exists for a topic.
export const TOPIC_EMOJI: Record<CommonTopicKey, string> = {
  general: '💬',
  daily: '☀️',
  food: '🍽️',
  school: '🎒',
  emotions: '😊',
  travel: '🚗',
  hobbies: '🎲',
  health: '🏥',
  shopping: '🛒',
};

// Keywords (both languages) used to find a representative pictogram for a
// topic from the user's symbol library.
export const TOPIC_SYMBOL_TERMS: Record<CommonTopicKey, string[]> = {
  general: ['hello', 'hola', 'talk', 'hablar'],
  daily: ['wake up', 'despertar', 'morning', 'mañana', 'routine'],
  food: ['eat', 'comer', 'food', 'comida'],
  school: ['school', 'escuela', 'book', 'libro'],
  emotions: ['happy', 'feliz', 'sad', 'triste'],
  travel: ['go', 'ir', 'car', 'coche', 'bus', 'autobús'],
  hobbies: ['play', 'jugar', 'ball', 'pelota', 'game'],
  health: ['doctor', 'médico', 'sick', 'enfermo'],
  shopping: ['buy', 'comprar', 'shop', 'tienda'],
};

// Lowercase, strip accents, collapse whitespace — for matching topic names
// across surfaces (session history, saved topics, backend payloads).
export function normalizeTopic(text: string): string {
  return text
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function symbolMatchesTerm(symbol: LearningSymbolItem, term: string): boolean {
  const needle = normalizeTopic(term);
  if (!needle) return false;
  const haystack = normalizeTopic(`${symbol.label} ${symbol.keywords ?? ''} ${symbol.category ?? ''}`);
  return haystack.includes(needle);
}

/**
 * Find a representative pictogram for a topic from the user's symbol library.
 * Prefers a symbol with an image; falls back to the topic emoji.
 */
export function findTopicPictogram(
  key: string,
  symbols: LearningSymbolItem[],
  fallbackEmoji: string,
): { imagePath?: string; emoji: string } {
  const terms = TOPIC_SYMBOL_TERMS[key as CommonTopicKey] ?? [];
  const matches = symbols.filter((symbol) => terms.some((term) => symbolMatchesTerm(symbol, term)));
  const withImage = matches.find((symbol) => symbol.image_path);
  return {
    imagePath: withImage?.image_path ?? matches[0]?.image_path,
    emoji: fallbackEmoji,
  };
}
