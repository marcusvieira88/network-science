import { describe, expect, it } from "vitest";

import { WebGPURenderer } from "@/vendor/three-webgpu-stub";

describe("three/webgpu stand-in", () => {
  it("fails loudly if anything ever asks for the WebGPU renderer", () => {
    expect(() => WebGPURenderer()).toThrow(/not bundled/);
  });
});
