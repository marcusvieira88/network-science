let cached: boolean | undefined;

/**
 * Whether this browser can draw the 3D view; without WebGL the explorer shows the 2D network.
 * Probed once per page: the probe context is released at once, because browsers cap live WebGL
 * contexts and would otherwise start dropping the real renderer's.
 */
export function supportsWebGL(): boolean {
  if (cached !== undefined) return cached;
  if (typeof WebGLRenderingContext === "undefined") return (cached = false);
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
  context?.getExtension("WEBGL_lose_context")?.loseContext();
  return (cached = context !== null);
}
