/**
 * A stand-in for @sigma/layer-webgl (its layers need WebGL2, which jsdom lacks). It records every
 * bind and every cleanup, so tests can check that no layer outlives its view, and hands back the
 * program class, which tests instantiate against a fake WebGL context to read the uploaded data.
 * Use with `vi.mock("@sigma/layer-webgl", () => import("@/test/layerWebgl"))`.
 */

/** What a test needs of the contour program: the per-render upload. */
export interface ContourProgram {
  setCameraUniforms(params: object, programInfo: object): void;
}

export type ContourProgramClass = new (gl: object, pickingBuffer: null, renderer: object) => ContourProgram;

export interface BoundLayer {
  id: string;
  renderer: object;
  program: ContourProgramClass;
}

export const layerStub: { binds: BoundLayer[]; cleanups: number } = { binds: [], cleanups: 0 };

export function resetLayerStub(): void {
  layerStub.binds = [];
  layerStub.cleanups = 0;
}

export class WebGLLayerProgram {
  renderer: object;
  constructor(_gl: object, _pickingBuffer: null, renderer: object) {
    this.renderer = renderer;
  }
}

export function bindWebGLLayer(id: string, renderer: object, program: ContourProgramClass): () => void {
  layerStub.binds.push({ id, renderer, program });
  return () => {
    layerStub.cleanups += 1;
  };
}
