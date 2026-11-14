/**
 * The Overlap mode's contour layer: a WebGL program on @sigma/layer-webgl's `WebGLLayerProgram`,
 * bound under Sigma's edges with `bindWebGLLayer`. The data mapping is in lib/overlapContours.ts.
 *
 * One layer draws every group. The package's `createContoursProgram` draws one colour per layer,
 * so it would need a layer per group, and every layer is its own WebGL context: with the
 * release's 23 drawn groups plus Sigma's 3 contexts that passes the browsers' cap of 16 live contexts
 * (Chrome then drops the oldest, Sigma's own). Contours are therefore drawn by this one program,
 * with the same look: the group's colour, a solid border and a translucent fill.
 */
import { WebGLLayerProgram, type WebGLLayerDefinition, type WebGLLayerProgramType, bindWebGLLayer } from "@sigma/layer-webgl";
import type Sigma from "sigma";
import type { ProgramInfo } from "sigma/rendering";
import type { RenderParams } from "sigma/types";

import { CONTOUR_LAYER_ID, type ContourStyle, type DrawnDisc, contourFragmentShader, contourUniforms } from "@/lib/overlapContours";

const CONTOUR_UNIFORMS = ["u_circles", "u_fills", "u_borders", "u_height", "u_pixelRatio"];

export class ContourLayerError extends Error {
  override name = "ContourLayerError";
}

function uniformLocation(programInfo: ProgramInfo, name: string): WebGLUniformLocation {
  const location = programInfo.uniformLocations[name];
  if (!location) throw new ContourLayerError(`the contour shader has no uniform ${name}`);
  return location;
}

/**
 * The program class for `groups` contours; `styles` is read on every render. The definition
 * comes from this closure because the base class asks for it from its constructor.
 */
function groupContoursProgram(groups: number, styles: () => readonly ContourStyle[]): WebGLLayerProgramType {
  return class GroupContoursProgram extends WebGLLayerProgram {
    getCustomLayerDefinition(): WebGLLayerDefinition {
      return { FRAGMENT_SHADER_SOURCE: contourFragmentShader(groups), DATA_UNIFORMS: [], CAMERA_UNIFORMS: CONTOUR_UNIFORMS };
    }

    cacheDataUniforms(): void {
      // Nothing is cached per graph process: the contours are in viewport pixels, which change
      // with every camera move and animation frame, so setCameraUniforms uploads them per render.
    }

    setCameraUniforms(params: RenderParams, programInfo: ProgramInfo): void {
      const uniforms = contourUniforms(styles(), (key) => this.drawnDisc(key));
      const { gl } = programInfo;
      gl.uniform4fv(uniformLocation(programInfo, "u_circles"), uniforms.circles);
      gl.uniform4fv(uniformLocation(programInfo, "u_fills"), uniforms.fills);
      gl.uniform4fv(uniformLocation(programInfo, "u_borders"), uniforms.borders);
      gl.uniform1f(uniformLocation(programInfo, "u_height"), params.height * params.pixelRatio);
      gl.uniform1f(uniformLocation(programInfo, "u_pixelRatio"), params.pixelRatio);
    }

    /** The disc exactly as Sigma draws and hovers it: same centre, same scaled size. */
    private drawnDisc(key: string): DrawnDisc {
      const data = this.renderer.getNodeDisplayData(key);
      if (!data) throw new ContourLayerError(`no drawn node for the contour ${key}`);
      const { x, y } = this.renderer.framedGraphToViewport(data);
      return { x, y, radius: this.renderer.scaleSize(data.size) };
    }
  };
}

/** Binds the contour layer under Sigma's edges; returns the cleanup that removes it. */
export function bindGroupContours(renderer: Sigma, groups: number, styles: () => readonly ContourStyle[]): () => void {
  return bindWebGLLayer(CONTOUR_LAYER_ID, renderer, groupContoursProgram(groups, styles));
}
