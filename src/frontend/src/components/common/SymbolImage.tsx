import { useState } from 'react';
import { assetUrl } from '../../lib/utils';
import { Image as ImageIcon } from 'lucide-react';

interface SymbolImageProps {
  imagePath?: string | null;
  alt?: string;
  className?: string;
  /** First letter(s) fallback shown when no image is available. */
  fallbackText?: string;
  /** Category-derived background when using the text fallback. */
  fallbackBg?: string;
}

function _fallbackInitials(text: string): string {
  // Take first 1-2 chars for avatar-style text fallback.
  const clean = text.trim();
  if (!clean) return '?';
  if (clean.length <= 2) return clean.toUpperCase();
  // Multi-word: first char of first two words.
  const words = clean.split(/\s+/);
  if (words.length >= 2) {
    return (words[0][0] + words[1][0]).toUpperCase();
  }
  return clean.slice(0, 2).toUpperCase();
}

export function SymbolImage({
  imagePath,
  alt,
  className = '',
  fallbackText,
  fallbackBg,
}: SymbolImageProps) {
  const [error, setError] = useState(false);
  const normalizedPath = imagePath?.trim();
  const isSafePath = Boolean(
    normalizedPath &&
      (normalizedPath.startsWith('blob:') ||
        normalizedPath.startsWith('data:image/') ||
        normalizedPath.startsWith('http://') ||
        normalizedPath.startsWith('https://') ||
        normalizedPath.startsWith('/')),
  );

  if (!isSafePath || error) {
    const initials = fallbackText ? _fallbackInitials(fallbackText) : null;
    const bg = fallbackBg || 'bg-indigo-100 dark:bg-indigo-900/40';
    const fg = 'text-indigo-600 dark:text-indigo-300';
    return (
      <div
        className={`flex items-center justify-center rounded-lg ${bg} ${className}`}
      >
        {initials ? (
          <span className={`text-sm font-bold leading-none ${fg}`}>
            {initials}
          </span>
        ) : (
          <ImageIcon className="w-1/2 h-1/2 text-gray-400" />
        )}
      </div>
    );
  }

  return (
    <img
      src={assetUrl(normalizedPath)}
      alt={alt || ''}
      className={className}
      onError={() => setError(true)}
    />
  );
}
