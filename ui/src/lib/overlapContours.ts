/**
 * Pure mapping for the Overlap mode's contour layer (drawn by lib/contourLayer.ts with
 * @sigma/layer-webgl): one outlined, translucent contour per published group, in the group's
 * colour and the size of its disc, so the lens where two groups were pulled together shows as
 * two intersecting outlines. Contours come from group nodes only, never from per-person points.
 */
import { hexChannels } from "@/lib/color";
import { type Focus, groupKey } from "@/lib/sigmaNetwork";

/** Id of the Sigma canvas layer that holds the contours. */
export const CONTOUR_LAYER_ID = "overlapContours";
/**
 * Contour radius ÷ the radius of the disc Sigma draws (and hovers) for the group. 1: the outline
 * is that disc, so the lens the eye sees is the depth the overlap solver computed.
 */
export const CONTOUR_RADIUS_PER_DISC_RADIUS = 1;
/** Fill opacity, as the Sigma.js highlight-group example's `color + "22"`. */
export const CONTOUR_FILL_OPACITY = 0x22 / 0xff;
/** Border widths in CSS pixels, drawn inside the contour so its outer edge stays the disc's edge. */
export const CONTOUR_BORDER_PX = 2;
export const CONTOUR_FOCUS_BORDER_PX = 4;
/** Under a focus, groups with no tie to the focused one keep this share of their opacity. */
export const CONTOUR_DIMMED_OPACITY = 0.2;
/** Values per group in each uniform array: a vec4. */
const VEC4 = 4;

/** Red, green, blue, alpha in [0, 1], premultiplied by alpha (how Sigma's canvases blend). */
export type Rgba = readonly [number, number, number, number];

export interface ContourStyle {
  /** The group's Sigma node key. */
  key: string;
  fill: Rgba;
  border: Rgba;
  /** CSS pixels. */
  borderWidth: number;
}

/** A group's disc as Sigma draws it, in viewport CSS pixels. */
export interface DrawnDisc {
  x: number;
  y: number;
  radius: number;
}

export interface ContourUniforms {
  /** Per group: centre x, centre y, radius, border width (CSS pixels). */
  circles: Float32Array;
  fills: Float32Array;
  borders: Float32Array;
}

export function contourRadius(discRadius: number): number {
  return discRadius * CONTOUR_RADIUS_PER_DISC_RADIUS;
}

function premultiplied(hex: string, opacity: number): Rgba {
  const [red, green, blue] = hexChannels(hex);
  return [red * opacity, green * opacity, blue * opacity, opacity];
}

/**
 * One style per group, in `order` (later groups are drawn over earlier ones). Under a focus the
 * focused group gets a thicker border, the groups it has a tie with stay as they are and every
 * other group is dimmed, as the nodes and ties are.
 */
export function contourStyles(order: readonly string[], colors: ReadonlyMap<string, string>, focus: Focus | null): ContourStyle[] {
  return order.map((group) => {
    const color = colors.get(group);
    if (color === undefined) throw new Error(`no colour for group ${group}`);
    const key = groupKey(group);
    const dimmed = focus !== null && key !== focus.key && !focus.neighbours.has(key);
    const opacity = dimmed ? CONTOUR_DIMMED_OPACITY : 1;
    return {
      key,
      fill: premultiplied(color, CONTOUR_FILL_OPACITY * opacity),
      border: premultiplied(color, opacity),
      borderWidth: focus?.key === key ? CONTOUR_FOCUS_BORDER_PX : CONTOUR_BORDER_PX,
    };
  });
}

/** The uniform arrays for one render, with each group's disc as Sigma currently draws it. */
export function contourUniforms(styles: readonly ContourStyle[], discOf: (key: string) => DrawnDisc): ContourUniforms {
  const circles = new Float32Array(styles.length * VEC4);
  const fills = new Float32Array(styles.length * VEC4);
  const borders = new Float32Array(styles.length * VEC4);
  styles.forEach((style, index) => {
    const disc = discOf(style.key);
    circles.set([disc.x, disc.y, contourRadius(disc.radius), style.borderWidth], index * VEC4);
    fills.set(style.fill, index * VEC4);
    borders.set(style.border, index * VEC4);
  });
  return { circles, fills, borders };
}

/**
 * The fragment shader: for each pixel, every group's contour composited over the earlier ones
 * (premultiplied "over"), a filled circle with its border inside the edge, anti-aliased over one
 * device pixel. GLSL cannot declare an empty array, so a layer needs at least one group.
 */
export function contourFragmentShader(groups: number): string {
  if (!Number.isInteger(groups) || groups < 1) throw new Error(`a contour layer needs at least one group, got ${groups}`);
  return `#version 300 es
#define GROUPS ${groups}
precision highp float;

uniform vec4 u_circles[GROUPS];
uniform vec4 u_fills[GROUPS];
uniform vec4 u_borders[GROUPS];
uniform float u_height;
uniform float u_pixelRatio;

out vec4 fragColor;

void main() {
  vec2 position = vec2(gl_FragCoord.x, u_height - gl_FragCoord.y) / u_pixelRatio;
  float pixel = 1.0 / u_pixelRatio;
  vec4 color = vec4(0.0);
  for (int i = 0; i < GROUPS; i++) {
    vec4 circle = u_circles[i];
    float distanceToCentre = distance(position, circle.xy);
    float inside = 1.0 - smoothstep(circle.z - pixel, circle.z, distanceToCentre);
    float ring = smoothstep(circle.z - circle.w - pixel, circle.z - circle.w, distanceToCentre);
    vec4 layer = mix(u_fills[i], u_borders[i], ring) * inside;
    color = layer + color * (1.0 - layer.a);
  }
  fragColor = color;
}
`;
}
