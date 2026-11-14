/**
 * Theme colours for the WebGL network. Sigma parses hex and rgb() only, while index.css keeps the
 * theme as CSS variables (hex for chart colours, "H S% L%" components for the rest). These pure
 * helpers turn a variable's raw value into hex, so index.css stays the one place colours live.
 */

export class ThemeColorError extends Error {
  override name = "ThemeColorError";
}

const HEX_PATTERN = /^#[0-9a-f]{6}$/i;
const HSL_PATTERN = /^(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%$/;
const DEGREES = 360;
const PERCENT = 100;
const CHANNEL_MAX = 255;

function channelHex(value: number): string {
  return Math.round(value * CHANNEL_MAX)
    .toString(16)
    .padStart(2, "0");
}

/** HSL (degrees, percent, percent) to "#rrggbb", by the CSS Color 4 conversion. */
export function hslToHex(hue: number, saturation: number, lightness: number): string {
  const s = saturation / PERCENT;
  const l = lightness / PERCENT;
  const channel = (n: number): number => {
    const k = (n + hue / (DEGREES / 12)) % 12;
    return l - s * Math.min(l, 1 - l) * Math.max(-1, Math.min(k - 3, 9 - k, 1));
  };
  return `#${channelHex(channel(0))}${channelHex(channel(8))}${channelHex(channel(4))}`;
}

/** A CSS variable's raw value ("#3987e5" or "213 76% 56%") as "#rrggbb"; anything else throws. */
export function themeHex(name: string, raw: string): string {
  const value = raw.trim();
  if (HEX_PATTERN.test(value)) return value.toLowerCase();
  const match = HSL_PATTERN.exec(value);
  if (!match) throw new ThemeColorError(`theme variable ${name} is not a colour: "${value}"`);
  return hslToHex(Number(match[1]), Number(match[2]), Number(match[3]));
}

/** "#rrggbb" plus an opacity in [0, 1] as "#rrggbbaa", which Sigma reads as a transparent colour. */
export function withAlpha(hex: string, opacity: number): string {
  return `${hex}${channelHex(Math.min(Math.max(opacity, 0), 1))}`;
}
