import type { LabelHTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

type FormLabelProps = LabelHTMLAttributes<HTMLLabelElement>

/**
 * Shared form-field label. Standardizes the most-duplicated label pattern
 * (37x verbatim copies of "block text-sm font-medium text-foreground mb-1")
 * so future spacing/typography changes happen in one place.
 */
function FormLabel({ className, ...props }: FormLabelProps) {
  return (
    <label
      className={cn('block text-sm font-medium text-foreground mb-1', className)}
      {...props}
    />
  )
}

export { FormLabel }
export type { FormLabelProps }
