import type { HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

interface LoadingStateProps extends HTMLAttributes<HTMLDivElement> {
  size?: 'sm' | 'md' | 'lg';
  label?: string;
  fullHeight?: boolean;
}

const sizeStyles = {
  sm: 'h-5 w-5 border-2',
  md: 'h-8 w-8 border-2',
  lg: 'h-12 w-12 border-4',
} as const;

export function LoadingState({
  size = 'md',
  label = 'Loading',
  fullHeight = false,
  className = '',
  ...props
}: LoadingStateProps) {
  return (
    <div
      role="status"
      aria-label={label}
      className={cn('flex items-center justify-center', fullHeight ? 'min-h-screen' : 'h-64', className)}
      {...props}
    >
      <span
        aria-hidden="true"
        className={cn('animate-spin rounded-full border-brand border-b-transparent', sizeStyles[size])}
      />
      <span className="sr-only">{label}</span>
    </div>
  );
}
