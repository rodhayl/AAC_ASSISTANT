import type { ComponentProps, ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

interface EmptyStateProps {
  icon: ReactNode
  title: string
  description?: string
  action?: Omit<ComponentProps<typeof Button>, 'children'> & { label: string }
  className?: string
}

/**
 * Shared empty-state block. Standardizes the "nothing here yet" pattern
 * (plain text today) so every empty view pairs the message with the next
 * concrete action instead of leaving the user stranded.
 */
export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  const { label, ...actionProps } = action ?? {}
  return (
    <div className={cn('flex flex-col items-center justify-center text-center py-12 px-4', className)}>
      <div className="bg-muted p-4 rounded-full mb-4" aria-hidden="true">
        {icon}
      </div>
      <p className="text-lg font-medium text-foreground">{title}</p>
      {description && <p className="text-sm text-muted-foreground mt-1 max-w-sm">{description}</p>}
      {action && (
        <Button className="mt-5" data-touch-target="true" {...actionProps}>
          {label}
        </Button>
      )}
    </div>
  )
}
