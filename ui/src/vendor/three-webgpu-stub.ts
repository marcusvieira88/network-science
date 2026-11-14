/**
 * Build-time stand-in for `three/webgpu` (aliased in vite.config.ts). three-render-objects imports
 * the WebGPU renderer eagerly but constructs it only when asked for WebGPU, which the explorer never
 * does; the stub keeps that renderer, its shader library and the URLs in its comments out of the
 * bundle. Calling or constructing it is a programming error, so it throws.
 */
export function WebGPURenderer(): never {
  throw new Error("The WebGPU renderer is not bundled; the explorer renders with WebGL.");
}
