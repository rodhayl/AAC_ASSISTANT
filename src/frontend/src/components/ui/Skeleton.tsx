import type { HTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

/**
 * Skeleton placeholder: a muted pulsing block used to preview the layout
 * while data loads, instead of a centered spinner that causes a layout jump
 * when content arrives.
 */
export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden="true"
      className={cn('animate-pulse rounded-lg bg-muted', className)}
      {...props}
    />
  )
}
