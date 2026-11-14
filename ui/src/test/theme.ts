import { readFileSync } from "node:fs";
import { join } from "node:path";

const DECLARATION = /^\s*(--[\w-]+):\s*([^;]+);/gm;

/**
 * jsdom does not load index.css, so the theme variables the WebGL view reads are copied from it
 * onto the document root: the tests use the real theme, from the one place it is defined.
 */
export function applyThemeVariables(): void {
  const css = readFileSync(join(import.meta.dirname, "..", "index.css"), "utf8");
  for (const [, name, value] of css.matchAll(DECLARATION)) {
    if (name && value) document.documentElement.style.setProperty(name, value.trim());
  }
}
