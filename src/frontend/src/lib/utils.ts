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
