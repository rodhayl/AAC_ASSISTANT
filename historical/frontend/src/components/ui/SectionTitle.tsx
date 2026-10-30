import type { HTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

type SectionTitleProps = HTMLAttributes<HTMLHeadingElement> & {
  as?: 'h1' | 'h2' | 'h3' | 'h4'
}

/**
 * Shared section heading. Standardizes the most-duplicated heading pattern
 * (31x verbatim copies of "text-lg font-semibold text-foreground") so
 * typography changes happen in one place. Renders the semantic heading level
 * passed via `as` (default h2) with a consistent visual scale.
 */
function SectionTitle({ className, as: Tag = 'h2', ...props }: SectionTitleProps) {
  return (
    <Tag
      className={cn('text-lg font-semibold text-foreground', className)}
      {...props}
    />
  )
}

export { SectionTitle }
export type { SectionTitleProps }
