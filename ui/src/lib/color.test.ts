import { describe, expect, it } from "vitest";

import { ThemeColorError, hexChannels, hslToHex, themeHex, withAlpha } from "@/lib/color";

describe("hslToHex", () => {
  // Expected values from Python's colorsys.hls_to_rgb, rounded to bytes.
  it.each([
    [0, 100, 50, "#ff0000"],
    [120, 100, 25, "#008000"],
    [213, 76, 56, "#3a86e4"],
    [40, 10, 93, "#efeeeb"],
    [240, 4, 13, "#202022"],
  ])("hsl(%i, %i%%, %i%%) is %s", (hue, saturation, lightness, hex) => {
    expect(hslToHex(hue, saturation, lightness)).toBe(hex);
  });
});

describe("themeHex", () => {
  it("passes hex through in lower case and converts HSL components", () => {
    expect(themeHex("--chart-1", " #3987E5 ")).toBe("#3987e5");
    expect(themeHex("--primary", "213 76% 56%")).toBe("#3a86e4");
  });

  it("refuses a value that is not a colour, naming the variable", () => {
    expect(() => themeHex("--missing", "")).toThrow(ThemeColorError);
    expect(() => themeHex("--missing", "")).toThrow("--missing");
    expect(() => themeHex("--x", "var(--y)")).toThrow(ThemeColorError);
  });
});

describe("withAlpha", () => {
  it("appends the opacity as a byte and clamps it to [0, 1]", () => {
    expect(withAlpha("#3987e5", 0.25)).toBe("#3987e540");
    expect(withAlpha("#3987e5", 0.55)).toBe("#3987e58c");
    expect(withAlpha("#3987e5", 2)).toBe("#3987e5ff");
    expect(withAlpha("#3987e5", -1)).toBe("#3987e500");
  });
});

describe("hexChannels", () => {
  it("reads #rrggbb as red, green and blue in [0, 1]", () => {
    expect(hexChannels("#ff8000")).toEqual([1, 128 / 255, 0]);
    expect(hexChannels("#3987E5")).toEqual([0x39 / 255, 0x87 / 255, 0xe5 / 255]);
  });

  it("refuses anything but #rrggbb", () => {
    expect(() => hexChannels("#fff")).toThrow(ThemeColorError);
    expect(() => hexChannels("#3987e580")).toThrow(ThemeColorError);
  });
});
