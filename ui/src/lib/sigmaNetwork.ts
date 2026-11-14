/**
 * Data mapping for the WebGL group network (Sigma.js): pure functions from release rows to the
 * graphology graph Sigma draws, its one-off layout, the hover focus and the legend.
 *
 * Every size is in layout units, the same units as the positions (Sigma's `itemSizesReference:
 * "positions"`), so a group's disc, the anonymous points inside it and the ties all zoom together.
 * Nodes carry only what is drawn: position, size, colour, the group label (groups only), a kind
 * and a drawing order. Anonymous points have opaque keys (`point:<group index>-<index>`) and no
 * label, so nothing about a single point can be shown, searched or hovered.
 */
import forceAtlas2, { type ForceAtlas2Settings } from "graphology-layout-forceatlas2";
import { UndirectedGraph } from "graphology";
import type { NodeHoverDrawingFunction } from "sigma/rendering";
import type { EdgeDisplayData, NodeDisplayData } from "sigma/types";

import { type Point, sortedGroups } from "@/lib/cells";
import { themeHex, withAlpha } from "@/lib/color";
import type { CommunityEdgeRow, CommunityGroupRow } from "@/lib/data";
import { type GroupTie, MEMBRANE_OPACITY, groupColor, publishedTies } from "@/lib/network";

/** Disc radius = square root of group size times this, so disc area is proportional to size. */
export const NODE_RADIUS_PER_SQRT_PERSON = 1;
/** An anonymous point's radius, in layout units; a group of 5 has a disc of radius about 2.2. */
export const POINT_RADIUS = 0.3;
/** Tie width in layout units, from the lightest to the heaviest weekly tie. */
export const EDGE_MIN_WIDTH = 0.1;
export const EDGE_MAX_WIDTH = 1.2;
/** Ties are drawn translucent so crossings stay readable. */
export const TIE_OPACITY = 0.55;
/** ForceAtlas2 runs this many iterations once, over the ties of all weeks; positions then stay. */
export const LAYOUT_ITERATIONS = 500;
/**
 * Fixed ForceAtlas2 settings (no randomness in the algorithm, fixed initial ring): the same data
 * always gives the same picture. `adjustSizes` keeps discs from overlapping.
 */
export const LAYOUT_SETTINGS: ForceAtlas2Settings = {
  adjustSizes: true,
  barnesHutOptimize: false,
  strongGravityMode: true,
  gravity: 0.05,
  scalingRatio: 10,
  slowDown: 10,
};
/** Points are drawn above the group disc they sit in. */
const GROUP_Z = 0;
const POINT_Z = 1;
const FULL_TURN = 2 * Math.PI;
/** Space between a hovered disc, its label box and the label text, in pixels. */
const HOVER_PADDING = 4;

export interface Position {
  x: number;
  y: number;
}

export type NodeKind = "group" | "point";

export type NetworkNode = {
  x: number;
  y: number;
  size: number;
  color: string;
  label: string | null;
  kind: NodeKind;
  zIndex: number;
};

export type NetworkEdge = {
  size: number;
  color: string;
  weight: number;
};

export type NetworkGraph = UndirectedGraph<NetworkNode, NetworkEdge>;

/** Theme colours as hex (Sigma cannot read CSS variables). */
export interface NetworkPalette {
  groups: ReadonlyMap<string, string>;
  tie: string;
  point: string;
  dimmed: string;
  label: string;
  hoverBackground: string;
}

export function groupNodeRadius(nPersons: number): number {
  return NODE_RADIUS_PER_SQRT_PERSON * Math.sqrt(nPersons);
}

export function groupKey(label: string): string {
  return `group:${label}`;
}

export function pointKey(groupIndex: number, index: number): string {
  return `point:${groupIndex}-${index}`;
}

/** Share of the heaviest weekly tie, clamped to [0, 1]. */
function tieShare(weight: number, maxTie: number): number {
  return Math.min(Math.max(weight / Math.max(maxTie, 1), 0), 1);
}

/** Tie width: `maxTie` is the heaviest tie of any week, so a wider line always means a heavier tie. */
export function edgeWidth(weight: number, maxTie: number): number {
  return EDGE_MIN_WIDTH + tieShare(weight, maxTie) * (EDGE_MAX_WIDTH - EDGE_MIN_WIDTH);
}

const VARIABLE_PATTERN = /^var\((--[\w-]+)\)$/;

function variableName(reference: string): string {
  const match = VARIABLE_PATTERN.exec(reference);
  if (!match?.[1]) throw new Error(`not a CSS variable reference: ${reference}`);
  return match[1];
}

/**
 * The palette from the theme: each group keeps the colour the tables and the 2D view give it
 * (groupColor), and the rest comes from the shared tokens. `read` returns a CSS variable's raw value.
 */
export function networkPalette(groups: CommunityGroupRow[], read: (variable: string) => string): NetworkPalette {
  const order = sortedGroups(groups).map((g) => g.group);
  const hex = (variable: string): string => themeHex(variable, read(variable));
  return {
    groups: new Map(order.map((group) => [group, hex(variableName(groupColor(group, order)))])),
    tie: withAlpha(hex("--muted-foreground"), TIE_OPACITY),
    point: hex("--foreground"),
    dimmed: hex("--muted"),
    label: hex("--foreground"),
    hoverBackground: hex("--popover"),
  };
}

/**
 * Group positions from ForceAtlas2 over the ties of all weeks (weights scaled to the heaviest),
 * computed once, so a group never moves while the week changes. Groups start on a ring in label
 * order whose circumference is about the sum of their diameters.
 */
export function layoutPositions(groups: CommunityGroupRow[], edges: CommunityEdgeRow[]): Map<string, Position> {
  const ordered = sortedGroups(groups);
  const graph = new UndirectedGraph<Position & { size: number }, { weight: number }>();
  const ring = ordered.reduce((sum, g) => sum + groupNodeRadius(g.n_persons), 0) / Math.PI;
  ordered.forEach((g, index) => {
    const angle = (FULL_TURN * index) / ordered.length;
    graph.addNode(g.group, { x: ring * Math.cos(angle), y: ring * Math.sin(angle), size: groupNodeRadius(g.n_persons) });
  });
  const ties = publishedTies(edges, null, graph.nodes());
  const heaviest = Math.max(1, ...ties.map((tie) => tie.total));
  for (const tie of ties) graph.addEdge(tie.a, tie.b, { weight: tie.total / heaviest });
  const mapping = forceAtlas2(graph, { iterations: LAYOUT_ITERATIONS, getEdgeWeight: "weight", settings: LAYOUT_SETTINGS });
  return new Map(
    ordered.map((g) => {
      const position = mapping[g.group];
      if (!position) throw new Error(`layout lost group ${g.group}`);
      return [g.group, { x: position.x, y: position.y }];
    }),
  );
}

export interface NetworkInput {
  groups: CommunityGroupRow[];
  positions: ReadonlyMap<string, Position>;
  /** The selected week's ties between published groups. */
  ties: GroupTie[];
  maxTie: number;
  palette: NetworkPalette;
  /** Anonymous points per group label, relative to the group's centre; null in the Groups mode. */
  points: ReadonlyMap<string, readonly Point[]> | null;
}

/**
 * The graph for one week: a disc per published group, the week's ties between groups and, in the
 * Individuals mode, the group's anonymous points inside a translucent disc. Ties join groups only.
 */
export function networkGraph({ groups, positions, ties, maxTie, palette, points }: NetworkInput): NetworkGraph {
  const graph: NetworkGraph = new UndirectedGraph();
  sortedGroups(groups).forEach((g, groupIndex) => {
    const centre = positions.get(g.group);
    const color = palette.groups.get(g.group);
    if (!centre || !color) throw new Error(`no position or colour for group ${g.group}`);
    graph.addNode(groupKey(g.group), {
      x: centre.x,
      y: centre.y,
      size: groupNodeRadius(g.n_persons),
      color: points ? withAlpha(color, MEMBRANE_OPACITY) : color,
      label: g.group,
      kind: "group",
      zIndex: GROUP_Z,
    });
    (points?.get(g.group) ?? []).forEach(([dx = 0, dy = 0], index) => {
      graph.addNode(pointKey(groupIndex, index), {
        x: centre.x + dx,
        y: centre.y + dy,
        size: POINT_RADIUS,
        color: palette.point,
        label: null,
        kind: "point",
        zIndex: POINT_Z,
      });
    });
  });
  for (const tie of ties) {
    const a = groupKey(tie.a);
    const b = groupKey(tie.b);
    if (!graph.hasNode(a) || !graph.hasNode(b)) continue;
    graph.addEdgeWithKey(`${a}|${b}`, a, b, { size: edgeWidth(tie.total, maxTie), color: palette.tie, weight: tie.total });
  }
  return graph;
}

/** A hovered or searched group and the groups it has a tie with this week. */
export interface Focus {
  key: string;
  neighbours: ReadonlySet<string>;
}

/** Focus on a group node; null for anything else (an anonymous point or an unknown key). */
export function focusOn(graph: NetworkGraph, key: string | null): Focus | null {
  if (key === null || !graph.hasNode(key) || graph.getNodeAttribute(key, "kind") !== "group") return null;
  return { key, neighbours: new Set(graph.neighbors(key)) };
}

/**
 * What Sigma draws for a node under the focus: the focused group highlighted, its tied groups as
 * they are, every other group dimmed without its label. Points never get a label.
 */
export function nodeAppearance(key: string, node: NetworkNode, focus: Focus | null, dimmed: string): Partial<NodeDisplayData> {
  if (node.kind === "point") return { ...node, label: null };
  if (!focus) return node;
  if (key === focus.key) return { ...node, highlighted: true };
  if (focus.neighbours.has(key)) return node;
  return { ...node, color: dimmed, label: null };
}

/** Under a focus only the focused group's ties stay visible. */
export function edgeAppearance(edge: NetworkEdge, ends: readonly string[], focus: Focus | null): Partial<EdgeDisplayData> {
  if (!focus || ends.includes(focus.key)) return edge;
  return { ...edge, hidden: true };
}

/** The group whose label matches the query: exact (ignoring case) first, else the first containing it. */
export function findGroup(labels: readonly string[], query: string): string | null {
  const needle = query.trim().toLowerCase();
  if (needle === "") return null;
  const lower = labels.map((label) => label.toLowerCase());
  const index = lower.indexOf(needle);
  if (index >= 0) return labels[index] ?? null;
  return labels.find((_, i) => lower[i]?.includes(needle)) ?? null;
}

export interface SizeSample {
  people: number;
  /** Legend circle radius in pixels; area proportional to `people`. */
  radius: number;
}

/** Legend circles for the smallest and the largest published group (one if they are equal). */
export function legendSizes(groups: CommunityGroupRow[], maxRadius: number): SizeSample[] {
  const sizes = [...new Set(groups.map((g) => g.n_persons))].sort((a, b) => a - b);
  const largest = sizes[sizes.length - 1];
  if (largest === undefined) return [];
  const shown = sizes.length > 1 ? [sizes[0] ?? largest, largest] : [largest];
  return shown.map((people) => ({ people, radius: maxRadius * Math.sqrt(people / largest) }));
}

export interface WeightSample {
  weight: number;
  /** Legend line width in pixels, in proportion to the tie width drawn. */
  width: number;
}

/** Legend lines for half the heaviest weekly tie and the heaviest. */
export function legendWeights(maxTie: number, maxWidth: number): WeightSample[] {
  return [maxTie / 2, maxTie].map((weight) => ({ weight, width: (maxWidth * edgeWidth(weight, maxTie)) / EDGE_MAX_WIDTH }));
}

/** The part of a 2D canvas context the hover label uses. */
export interface LabelCanvas {
  font: string;
  fillStyle: string | CanvasGradient | CanvasPattern;
  measureText(text: string): { width: number };
  fillRect(x: number, y: number, width: number, height: number): void;
  fillText(text: string, x: number, y: number): void;
}

export interface LabelFont {
  labelSize: number;
  labelFont: string;
  labelWeight: string;
}

type HoverData = { x: number; y: number; size: number; label: string | null };

/**
 * The hover label on the dark theme: the group label in a box beside the disc. A node without a
 * label (an anonymous point) draws nothing, so hovering a point shows nothing.
 */
export function drawGroupHover(context: LabelCanvas, data: HoverData, font: LabelFont, palette: NetworkPalette): void {
  if (!data.label) return;
  const size = font.labelSize;
  context.font = `${font.labelWeight} ${size}px ${font.labelFont}`;
  const x = data.x + data.size + HOVER_PADDING;
  const width = context.measureText(data.label).width;
  context.fillStyle = palette.hoverBackground;
  context.fillRect(x - HOVER_PADDING, data.y - size / 2 - HOVER_PADDING, width + 2 * HOVER_PADDING, size + 2 * HOVER_PADDING);
  context.fillStyle = palette.label;
  context.fillText(data.label, x, data.y + size / 3);
}

/** `drawGroupHover` as Sigma's `defaultDrawNodeHover` setting. */
export function groupHoverDrawer(palette: NetworkPalette): NodeHoverDrawingFunction<NetworkNode, NetworkEdge> {
  return (context, data, settings) => drawGroupHover(context, data, settings, palette);
}
