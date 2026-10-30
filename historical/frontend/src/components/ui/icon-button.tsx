import type { ComponentProps } from "react"

import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"

type IconButtonProps = Omit<ComponentProps<typeof Button>, "title" | "size"> & {
  /** Accessible name; doubles as the tooltip content and native title fallback. */
  label: string
  /** Optional distinct native-title / tooltip text (defaults to `label`). */
  title?: string
  size?: Extract<
    NonNullable<ComponentProps<typeof Button>["size"]>,
    "icon" | "icon-xs" | "icon-sm" | "icon-lg"
  >
}

/**
 * Icon-only action button with an accessible tooltip.
 *
 * Replaces the hand-maintained `title={t('...')}`-only pattern: the Base UI
 * Tooltip gives keyboard focus + hover behavior with correct ARIA wiring, and
 * the native `title` is kept as a touch/fallback affordance (which also keeps
 * `getByTitle(...)` queries working in tests).
 */
function IconButton({
  label,
  title,
  size = "icon",
  variant = "ghost",
  className,
  children,
  ...props
}: IconButtonProps) {
  const tooltipText = title ?? label
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger
          render={
            <Button
              type="button"
              aria-label={label}
              title={tooltipText}
              size={size}
              variant={variant}
              className={className}
              {...props}
            />
          }
        >
          {children}
        </TooltipTrigger>
        <TooltipContent>{tooltipText}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

export { IconButton }
export type { IconButtonProps }
