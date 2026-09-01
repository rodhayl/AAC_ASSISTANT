import { useMemo } from 'react';
import { AVATAR_BG_COLORS } from '../../lib/avatarPalette';
import { cn } from '../../lib/utils';

function hashName(name: string): number {
  let hash = 0;
  for (let i = 0; i < name.length; i += 1) {
    hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  }
  return hash;
}

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase();
  // First letter of the first and last word (e.g. "Ms. Johnson" -> "MJ").
  return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
}

/**
 * Small deterministic avatar for a teacher's attribution label: a colored
 * circle with the teacher's initials. The color is stable per name so the
 * same teacher always gets the same hue across the picker and the sidebar.
 */
export function TeacherAvatar({
  name,
  className,
}: {
  name: string;
  className?: string;
}) {
  const color = useMemo(
    () => AVATAR_BG_COLORS[hashName(name) % AVATAR_BG_COLORS.length],
    [name],
  );
  return (
    <span
      aria-hidden="true"
      className={cn(
        'inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[8px] font-bold text-white',
        color,
        className,
      )}
    >
      {initialsOf(name)}
    </span>
  );
}
