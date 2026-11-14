import { afterEach, describe, expect, it, vi } from "vitest";

describe("supportsWebGL", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    vi.resetModules();
  });

  it("probes once per page and releases the probe context", async () => {
    const loseContext = vi.fn();
    const context = { getExtension: vi.fn(() => ({ loseContext })) };
    vi.stubGlobal("WebGLRenderingContext", function WebGLRenderingContext() {});
    const create = vi
      .spyOn(document, "createElement")
      .mockReturnValue({ getContext: vi.fn(() => context) } as unknown as HTMLCanvasElement);
    const { supportsWebGL } = await import("@/lib/webgl");
    expect(supportsWebGL()).toBe(true);
    expect(supportsWebGL()).toBe(true);
    expect(create).toHaveBeenCalledTimes(1);
    expect(loseContext).toHaveBeenCalledTimes(1);
  });

  it("is false without WebGL", async () => {
    vi.stubGlobal("WebGLRenderingContext", undefined);
    const { supportsWebGL } = await import("@/lib/webgl");
    expect(supportsWebGL()).toBe(false);
  });
});
