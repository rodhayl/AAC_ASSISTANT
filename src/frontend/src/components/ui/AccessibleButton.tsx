import React from 'react';
import { useAccessibleInteraction } from '../../hooks/useAccessibleInteraction';

type AccessibleButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement>;

export function AccessibleButton({ onClick, disabled, children, ...props }: AccessibleButtonProps) {
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
      {...props}
    >
      {children}
    </button>
  );
}
