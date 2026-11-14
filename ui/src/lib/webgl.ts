/** Whether this browser can draw the 3D view; without WebGL the explorer shows the 2D network. */
export function supportsWebGL(): boolean {
  if (typeof WebGLRenderingContext === "undefined") return false;
  const canvas = document.createElement("canvas");
  return (canvas.getContext("webgl2") ?? canvas.getContext("webgl")) !== null;
}
