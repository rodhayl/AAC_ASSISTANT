import React from 'react';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  fullWidth?: boolean;
}

const baseStyles =
  'inline-flex items-center justify-center rounded-lg font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed';

const variantStyles: Record<Variant, string> = {
  primary:
    'bg-indigo-600 text-white hover:bg-indigo-700 focus:ring-indigo-500 border border-transparent',
  secondary:
    'bg-white text-indigo-700 border border-indigo-200 hover:bg-indigo-50 focus:ring-indigo-500 dark:bg-gray-900/60 dark:text-indigo-200 dark:border-indigo-700 dark:hover:bg-indigo-800',
  ghost:
    'bg-transparent text-gray-700 hover:bg-gray-100 focus:ring-indigo-500 dark:text-gray-200 dark:hover:bg-gray-800',
  danger:
    'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500 border border-transparent',
};

const sizeStyles: Record<Size, string> = {
  sm: 'px-3 py-2 text-sm',
  md: 'px-4 py-2 text-sm',
};

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  loading = false,
  fullWidth = false,
  className,
  ...props
}) => {
  return (
    <button
      type={props.type || 'button'}
      className={[
        baseStyles,
        variantStyles[variant],
        sizeStyles[size],
        fullWidth ? 'w-full' : '',
        className || ''
      ].filter(Boolean).join(' ')}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading && <span className="mr-2 h-4 w-4 animate-spin rounded-full border-b-2 border-current" />}
      {children}
    </button>
  );
};
