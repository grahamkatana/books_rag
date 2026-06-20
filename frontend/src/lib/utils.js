import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merges Tailwind classes, letting later conditional classes correctly
 * override earlier ones (plain string concatenation can't do this --
 * "px-2 px-4" doesn't know px-4 should win, twMerge does). */
export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
