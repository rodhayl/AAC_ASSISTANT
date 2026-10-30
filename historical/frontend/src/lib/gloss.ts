
// Template-based glossing patterns for common AAC constructions
interface GlossTemplate {
  pattern: RegExp;
  transform: (matches: RegExpMatchArray) => string;
}

const glossTemplates: GlossTemplate[] = [
  // Pronoun + want/need + object → "I want X" / "I need X"
  {
    pattern: /^(I|me|my)\s+(want|need)\s+(.+)$/i,
    transform: (matches) => `I ${matches[2].toLowerCase()} ${matches[3]}.`
  },
  // Subject + action verb + object → Proper capitalization
  {
    pattern: /^(.+?)\s+(eat|drink|play|go|help|like|love|see)\s+(.+)$/i,
    transform: (matches) => {
      const subj = matches[1].charAt(0).toUpperCase() + matches[1].slice(1).toLowerCase();
      return `${subj} ${matches[2].toLowerCase()} ${matches[3]}.`;
    }
  },
  // Question words → Add question mark
  {
    pattern: /^(what|where|when|who|why|how)\s+(.+)$/i,
    transform: (matches) => {
      const qWord = matches[1].charAt(0).toUpperCase() + matches[1].slice(1).toLowerCase();
      return `${qWord} ${matches[2].toLowerCase()}?`;
    }
  },
  // Single feeling word → "I feel X"
  {
    pattern: /^(happy|sad|angry|tired|hungry|thirsty|excited|scared|bored)$/i,
    transform: (matches) => `I feel ${matches[1].toLowerCase()}.`
  },
  // Pronoun + feeling → "I feel X"
  {
    pattern: /^(I|me)\s+(happy|sad|angry|tired|hungry|thirsty|excited|scared)$/i,
    transform: (matches) => `I feel ${matches[2].toLowerCase()}.`
  }
];

export const glossSymbolUtterance = (symbols: Array<{ label: string; category?: string }>): string => {
  if (!symbols.length) return '';
  const joined = symbols.map(s => s.label.trim()).filter(Boolean).join(' ');
  if (!joined) return '';

  // Try template matching for enhanced glossing
  for (const template of glossTemplates) {
    const match = joined.match(template.pattern);
    if (match) {
      return template.transform(match);
    }
  }

  // Fallback: basic capitalization + punctuation
  const capped = joined.charAt(0).toUpperCase() + joined.slice(1);
  const needsPeriod = !/[.!?]$/.test(capped);
  return needsPeriod ? `${capped}.` : capped;
};
