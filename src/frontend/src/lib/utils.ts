import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { config } from '../config';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function assetUrl(path?: string) {
  if (!path) return '';
  if (path.startsWith('/uploads')) return `${config.BACKEND_URL}${path}`;
  return path;
}

export function safeImageUrl(url?: string | null): string | undefined {
  if (!url) return undefined;
  const trimmed = url.trim();
  if (
    trimmed.startsWith('blob:') ||
    trimmed.startsWith('data:image/') ||
    trimmed.startsWith('http://') ||
    trimmed.startsWith('https://') ||
    trimmed.startsWith('/')
  ) {
    return trimmed;
  }
  return undefined;
}
