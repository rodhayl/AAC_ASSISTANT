import React from 'react';
import { useAccessibleInteraction } from '../../hooks/useAccessibleInteraction';
import { cn } from '@/lib/utils';

type AccessibleButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  className?: string;
};

export function AccessibleButton({ onClick, disabled, children, className, ...props }: AccessibleButtonProps) {
  const { onClick: handleClick, onMouseDown, onMouseUp, onMouseLeave, onTouchStart, onTouchEnd } = useAccessibleInteraction({
    onClick: (e) => onClick?.(e as React.MouseEvent<HTMLButtonElement>),
    disabled
  });

  return (
    <button
      onClick={handleClick}
      onMouseDown={onMouseDown}
      onMouseUp={onMouseUp}
      onMouseLeave={onMouseLeave}
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
      disabled={disabled}
      className={cn(className)}
      {...props}
    >
      {children}
    </button>
  );
}
