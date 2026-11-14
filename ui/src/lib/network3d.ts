/**
 * Data mapping for the 3D group network: pure functions from release rows to the nodes and links
 * the force graph draws. Nothing here imports the 3D library, so it stays out of the main bundle.
 */
import { cellRadius, particleCount, particleSpeed, sortedGroups } from "@/lib/cells";
import type { CommunityEdgeRow, CommunityGroupRow } from "@/lib/data";
import { publishedTies } from "@/lib/network";

/** Accent hue and saturation (--primary in index.css: 213 76% 56%). */
const ACCENT_HUE = 213;
const ACCENT_SATURATION = 76;
export const NODE_MIN_LIGHTNESS = 40;
export const NODE_MAX_LIGHTNESS = 72;
/** Axon tone: the accent at a pale lightness (hsl(213, 76%, 78%)), so ties glow like the cells. */
const EDGE_RGB = "157, 194, 242";
/** Signals travelling along a tie: a near-white accent so bloom makes them spark. */
export const PARTICLE_COLOR = "hsl(213, 90%, 88%)";
export const EDGE_MIN_WIDTH = 0.4;
export const EDGE_MAX_WIDTH = 3;
export const EDGE_MIN_OPACITY = 0.2;
export const EDGE_MAX_OPACITY = 0.85;
/** Near-black canvas (--background in index.css: 240 6% 4%). */
export const BACKGROUND_COLOR = "#0a0a0c";
/** Ties bend slightly, like dendrites rather than wires. */
export const LINK_CURVATURE = 0.25;
/** Force ticks run before the first frame; the layout is then frozen. */
export const LAYOUT_TICKS = 300;

export interface GraphNode {
  id: string;
  nPersons: number;
  /** Cell volume, proportional to group size. */
  val: number;
  /** Cell radius in scene units (cellRadius in lib/cells.ts), so volume follows `val`. */
  radius: number;
  color: string;
}

export interface GraphLink {
  source: string;
  target: string;
  weight: number;
  width: number;
  color: string;
  /** Signal particles travelling along the tie this week, and their speed. */
  particles: number;
  particleSpeed: number;
}

function lerp(low: number, high: number, share: number): number {
  return low + share * (high - low);
}

function nodeColor(nPersons: number, smallest: number, largest: number): string {
  const span = Math.cbrt(largest) - Math.cbrt(smallest);
  const share = span > 0 ? (Math.cbrt(nPersons) - Math.cbrt(smallest)) / span : 0.5;
  const lightness = lerp(NODE_MIN_LIGHTNESS, NODE_MAX_LIGHTNESS, share);
  return `hsl(${ACCENT_HUE}, ${ACCENT_SATURATION}%, ${lightness.toFixed(1)}%)`;
}

/** One cell per published group, sorted by label; lightness rises with size on a cube-root scale. */
export function graphNodes(groups: CommunityGroupRow[]): GraphNode[] {
  const sizes = groups.map((g) => g.n_persons);
  const smallest = Math.min(...sizes);
  const largest = Math.max(...sizes);
  return sortedGroups(groups).map((g) => ({
    id: g.group,
    nPersons: g.n_persons,
    val: g.n_persons,
    radius: cellRadius(g.n_persons),
    color: nodeColor(g.n_persons, smallest, largest),
  }));
}

function link(a: string, b: string, weight: number, maxTie: number): GraphLink {
  const share = Math.min(weight / Math.max(maxTie, 1), 1);
  const opacity = lerp(EDGE_MIN_OPACITY, EDGE_MAX_OPACITY, share);
  return {
    source: a,
    target: b,
    weight,
    width: lerp(EDGE_MIN_WIDTH, EDGE_MAX_WIDTH, share),
    color: `rgba(${EDGE_RGB}, ${opacity.toFixed(3)})`,
    particles: particleCount(weight, maxTie),
    particleSpeed: particleSpeed(weight, maxTie),
  };
}

/**
 * Ties between distinct groups in one week. `maxTie` is the heaviest tie of any week, so a wider,
 * brighter line with more, faster particles always means a heavier tie. Ties to an unpublished
 * group are dropped.
 */
export function weekLinks(edges: CommunityEdgeRow[], week: string | null, maxTie: number, groupIds: string[]): GraphLink[] {
  return publishedTies(edges, week, groupIds).map((tie) => link(tie.a, tie.b, tie.total, maxTie));
}

/** Ties summed over all weeks: what the one-off layout is computed on. */
export function layoutLinks(groups: CommunityGroupRow[], edges: CommunityEdgeRow[]): GraphLink[] {
  const ids = groups.map((g) => g.group);
  const all = weekLinks(edges, null, 1, ids);
  return all.sort((x, y) => x.source.localeCompare(y.source) || x.target.localeCompare(y.target));
}

const HTML_ESCAPES: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

/** Hover label; the library inserts it as HTML, so the group label is escaped. */
export function nodeLabel(node: GraphNode): string {
  const label = node.id.replace(/[&<>"']/g, (char) => HTML_ESCAPES[char] ?? char);
  return `Group ${label} · ${node.nPersons} people`;
}
