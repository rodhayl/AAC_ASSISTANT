import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { config } from '../config';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// The UI offers regional codes (es-ES / en-US), but the language switcher and
// legacy rows may persist short codes (es / en). Normalize so a stored value
// always matches one of the <select> options regardless of how it was saved.
export function normalizeUILanguage(code: string | null | undefined): string {
  const lang = (code || '').trim().toLowerCase();
  if (lang.startsWith('en')) return 'en-US';
  if (lang.startsWith('es')) return 'es-ES';
  return lang || 'es-ES';
}

export function assetUrl(path?: string) {
  if (!path) return '';
  if (path.startsWith('/uploads')) return `${config.BACKEND_URL}${path}`;
  return path;
}
