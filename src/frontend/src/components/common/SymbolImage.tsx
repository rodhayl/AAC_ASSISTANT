import { useState } from 'react';
import { assetUrl } from '../../lib/utils';
import { Image as ImageIcon } from 'lucide-react';

interface SymbolImageProps {
  imagePath?: string | null;
  alt?: string;
  className?: string;
  /** Explicit status label shown when the configured image cannot be loaded. */
  missingImageLabel?: string;
}

export function SymbolImage({
  imagePath,
  alt,
  className = '',
  missingImageLabel = 'Image unavailable',
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
    const bg = 'bg-gray-100 dark:bg-gray-800';
    const fg = 'text-gray-500 dark:text-gray-400';
    return (
      <div
        className={`flex items-center justify-center rounded-lg ${bg} ${className}`}
      >
        <span className={`flex flex-col items-center gap-1 text-center text-[10px] font-medium leading-tight ${fg}`}>
          <ImageIcon className="h-1/2 w-1/2" aria-hidden="true" />
          {missingImageLabel}
        </span>
      </div>
    );
  }

  return (
    <img
      src={assetUrl(normalizedPath)}
      alt={alt ?? ''}
      className={className}
      onError={() => setError(true)}
    />
  );
}
