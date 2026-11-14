/**
 * three.js objects for the cell network: glowing cell bodies in the Groups mode, and a faint
 * membrane holding anonymous points in the Individuals mode. Imported only by the lazily loaded
 * CommunityGraph3D chunk. No object is named or given user data: a point is a vertex, nothing more.
 */
import {
  AdditiveBlending,
  BufferGeometry,
  DataTexture,
  Float32BufferAttribute,
  Group,
  LinearFilter,
  Mesh,
  MeshBasicMaterial,
  type Object3D,
  Points,
  PointsMaterial,
  SphereGeometry,
  Sprite,
  SpriteMaterial,
  type Texture,
} from "three";

import { type NetworkMode, type Point, glowPixels } from "@/lib/cells";
import type { GraphNode } from "@/lib/network3d";

const GLOW_TEXTURE_SIZE = 64;
const SPHERE_SEGMENTS = 24;
/** Halo diameter as a multiple of the cell radius. */
const HALO_SCALE = 4.5;
const BODY_OPACITY = 0.85;
const HALO_OPACITY = 0.55;
const MEMBRANE_OPACITY = 0.06;
const NUCLEUS_HALO_OPACITY = 0.25;
const POINT_SIZE = 1.1;
const POINT_OPACITY = 0.9;

export function glowTexture(): Texture {
  const texture = new DataTexture(glowPixels(GLOW_TEXTURE_SIZE), GLOW_TEXTURE_SIZE, GLOW_TEXTURE_SIZE);
  texture.magFilter = LinearFilter;
  texture.minFilter = LinearFilter;
  texture.needsUpdate = true;
  return texture;
}

function halo(node: GraphNode, glow: Texture, opacity: number): Sprite {
  const sprite = new Sprite(
    new SpriteMaterial({
      map: glow,
      color: node.color,
      transparent: true,
      opacity,
      blending: AdditiveBlending,
      depthWrite: false,
    }),
  );
  sprite.scale.setScalar(node.radius * HALO_SCALE);
  return sprite;
}

function sphere(node: GraphNode, opacity: number): Mesh {
  return new Mesh(
    new SphereGeometry(node.radius, SPHERE_SEGMENTS, SPHERE_SEGMENTS),
    new MeshBasicMaterial({ color: node.color, transparent: true, opacity, depthWrite: false }),
  );
}

/** All of a group's points as one vertex cloud: no per-point object exists to carry data. */
function pointCloud(node: GraphNode, points: Point[], glow: Texture): Points {
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute(points.flat(), 3));
  return new Points(
    geometry,
    new PointsMaterial({
      map: glow,
      color: node.color,
      size: POINT_SIZE,
      transparent: true,
      opacity: POINT_OPACITY,
      blending: AdditiveBlending,
      depthWrite: false,
    }),
  );
}

/** The object drawn for one group: a glowing cell, or a membrane of anonymous points. */
export function cellObject(node: GraphNode, mode: NetworkMode, points: Point[], glow: Texture): Object3D {
  const cell = new Group();
  if (mode === "groups") {
    cell.add(sphere(node, BODY_OPACITY), halo(node, glow, HALO_OPACITY));
  } else {
    cell.add(sphere(node, MEMBRANE_OPACITY), halo(node, glow, NUCLEUS_HALO_OPACITY), pointCloud(node, points, glow));
  }
  return cell;
}
