import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** `value` limited to [low, high]. */
export function clamp(value: number, low: number, high: number): number {
  return Math.min(Math.max(value, low), high);
}

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
