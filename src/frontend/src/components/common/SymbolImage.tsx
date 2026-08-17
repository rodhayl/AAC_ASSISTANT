import { useState } from 'react';
import { assetUrl } from '../../lib/utils';
import { Image as ImageIcon } from 'lucide-react';

interface SymbolImageProps {
  imagePath?: string | null;
  alt?: string;
  className?: string;
}

export function SymbolImage({ imagePath, alt, className = '' }: SymbolImageProps) {
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
    return (
      <div className={`flex items-center justify-center bg-gray-100 dark:bg-gray-800 rounded-lg ${className}`}>
        <ImageIcon className="w-1/2 h-1/2 text-gray-400" />
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
