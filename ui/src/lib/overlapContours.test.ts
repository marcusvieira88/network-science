import { describe, expect, it } from "vitest";

import {
  CONTOUR_BORDER_PX,
  CONTOUR_DIMMED_OPACITY,
  CONTOUR_FILL_OPACITY,
  CONTOUR_FOCUS_BORDER_PX,
  contourFragmentShader,
  contourRadius,
  contourStyles,
  contourUniforms,
} from "@/lib/overlapContours";
import { targetDistance } from "@/lib/overlap";

const colors = new Map([
  ["G01", "#ff0000"],
  ["G02", "#00ff00"],
  ["G03", "#0000ff"],
]);
const order = ["G01", "G02", "G03"];

describe("contourRadius", () => {
  it("is the disc's own radius, so the outline is the disc the solver placed", () => {
    expect(contourRadius(7.5)).toBe(7.5);
    expect(contourRadius(0)).toBe(0);
  });

  it("shows the solver's depth: two contours at the target distance overlap by depth × smaller diameter", () => {
    const [a, b, depth] = [4, 3, 0.5];
    const lens = contourRadius(a) + contourRadius(b) - targetDistance(a, b, depth);
    // Hand-computed: 4 + 3 - (4 + 3 - 0.5 * 2 * 3) = 3.
    expect(lens).toBeCloseTo(3, 10);
  });
});

describe("contourStyles", () => {
  it("gives every group its own colour: a solid border and a translucent fill (premultiplied)", () => {
    const styles = contourStyles(order, colors, null);
    expect(styles.map((s) => s.key)).toEqual(["group:G01", "group:G02", "group:G03"]);
    expect(styles[0]?.border).toEqual([1, 0, 0, 1]);
    expect(styles[1]?.fill).toEqual([0, CONTOUR_FILL_OPACITY, 0, CONTOUR_FILL_OPACITY]);
    expect(styles.every((s) => s.borderWidth === CONTOUR_BORDER_PX)).toBe(true);
  });

  it("under a focus thickens the focused border, keeps its partners and dims every other group", () => {
    const focus = { key: "group:G01", neighbours: new Set(["group:G02"]) };
    const [g1, g2, g3] = contourStyles(order, colors, focus);
    expect(g1?.borderWidth).toBe(CONTOUR_FOCUS_BORDER_PX);
    expect(g2).toEqual(contourStyles(order, colors, null)[1]);
    expect(g3?.borderWidth).toBe(CONTOUR_BORDER_PX);
    expect(g3?.border).toEqual([0, 0, CONTOUR_DIMMED_OPACITY, CONTOUR_DIMMED_OPACITY]);
    expect(g3?.fill[3]).toBeCloseTo(CONTOUR_FILL_OPACITY * CONTOUR_DIMMED_OPACITY, 10);
  });

  it("refuses a group without a colour", () => {
    expect(() => contourStyles(["G09"], colors, null)).toThrow("G09");
  });
});

describe("contourUniforms", () => {
  it("packs each group's circle (centre, radius, border width) and colours in the styles' order", () => {
    const styles = contourStyles(["G01", "G02"], colors, null);
    const discs = new Map([
      ["group:G01", { x: 10, y: 20, radius: 5 }],
      ["group:G02", { x: 30, y: 40, radius: 2 }],
    ]);
    const uniforms = contourUniforms(styles, (key) => {
      const disc = discs.get(key);
      if (!disc) throw new Error(key);
      return disc;
    });
    expect([...uniforms.circles]).toEqual([10, 20, 5, CONTOUR_BORDER_PX, 30, 40, 2, CONTOUR_BORDER_PX]);
    expect([...uniforms.borders]).toEqual([1, 0, 0, 1, 0, 1, 0, 1]);
    expect(uniforms.fills).toHaveLength(8);
  });
});

describe("contourFragmentShader", () => {
  it("is sized for the number of groups and is the same for the same count", () => {
    expect(contourFragmentShader(24)).toContain("#define GROUPS 24");
    expect(contourFragmentShader(24)).toBe(contourFragmentShader(24));
  });

  it("refuses an empty layer, which GLSL cannot declare", () => {
    expect(() => contourFragmentShader(0)).toThrow();
  });
});
