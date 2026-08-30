import type { HTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

type StatusMessageProps = HTMLAttributes<HTMLDivElement> & {
  variant?: 'info' | 'success' | 'warning' | 'error'
}

const variants = {
  info: 'border-brand/30 bg-brand/10 text-foreground',
  success: 'border-green-200 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-900/20 dark:text-green-300',
  warning: 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300',
  error: 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300',
} as const

function StatusMessage({ className, variant = 'info', ...props }: StatusMessageProps) {
  return (
    <div
      role={props.role ?? (variant === 'error' ? 'alert' : undefined)}
      className={cn('rounded-lg border px-4 py-3 text-sm', variants[variant], className)}
      {...props}
    />
  )
}

export { StatusMessage }
