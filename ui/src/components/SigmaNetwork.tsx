/**
 * The WebGL group network (Sigma.js via React Sigma). Loaded on demand (React.lazy) so Sigma and
 * graphology stay out of the bundle the other views load. All data mapping lives in
 * lib/sigmaNetwork.ts; this file wires it to Sigma: loading the week's graph, hover and search
 * focus, the Overlap mode's contour layer, and zoom and fullscreen controls; the legend and the
 * focused group's summary are their own components.
 */
import "@react-sigma/core/lib/style.css";

import {
  ControlsContainer,
  FullScreenControl,
  SigmaContainer,
  ZoomControl,
  useCamera,
  useLoadGraph,
  useRegisterEvents,
  useSetSettings,
  useSigma,
} from "@react-sigma/core";
import { UndirectedGraph } from "graphology";
import { Maximize, Maximize2, Minimize2, Search, X, ZoomIn, ZoomOut } from "lucide-react";
import { type FormEvent, useEffect, useId, useMemo, useRef, useState } from "react";
import type { Settings } from "sigma/settings";
import { animateNodes } from "sigma/utils";

import { FocusSummary } from "@/components/FocusSummary";
import { NetworkLegend } from "@/components/NetworkLegend";
import { type NetworkMode, anonymousPoints } from "@/lib/cells";
import { bindGroupContours } from "@/lib/contourLayer";
import type { CommunityEdgeRow, CommunityGroupRow } from "@/lib/data";
import { type GroupTie, NETWORK_HEIGHT, publishedTies } from "@/lib/network";
import {
  OVERLAP_DISC_COLOR,
  type WeekOverlaps,
  relaxPositions,
  weekOverlaps,
} from "@/lib/overlap";
import { type ContourStyle, contourStyles } from "@/lib/overlapContours";
import {
  type NetworkEdge,
  type NetworkGraph,
  type NetworkNode,
  type NetworkPalette,
  type Position,
  edgeAppearance,
  findGroup,
  focusOn,
  groupHoverDrawer,
  groupKey,
  groupNodeRadius,
  layoutPositions,
  networkGraph,
  networkPalette,
  nodeAppearance,
} from "@/lib/sigmaNetwork";

const LABEL_SIZE = 12;
const LABEL_WEIGHT = "600";
const LABEL_FONT = "'Inter Variable', ui-sans-serif, system-ui, sans-serif";
const ZOOM_DURATION_MS = 300;
/** Duration of the Overlap mode's move from one week's layout to the next. */
const WEEK_MOTION_MS = 400;
const NO_OVERLAPS: WeekOverlaps = { overlaps: [], lines: [] };
const NO_CONTOURS: readonly ContourStyle[] = [];
/** Sizes are in layout units and grow with the zoom, so a group's points stay inside its disc. */
const zoomWithPositions = (ratio: number): number => ratio;

export interface SigmaNetworkProps {
  groups: CommunityGroupRow[];
  edges: CommunityEdgeRow[];
  week: string | null;
  /** The heaviest tie of any week: one width scale for every week. */
  maxTie: number;
  mode: NetworkMode;
  /** The run seed: scatters the illustrative points of the Individuals mode. */
  seed: number;
}

/** A theme variable's raw value; index.css is where the colours live. */
function readThemeVariable(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name);
}

function sigmaSettings(palette: NetworkPalette): Partial<Settings<NetworkNode, NetworkEdge>> {
  return {
    itemSizesReference: "positions",
    zoomToSizeRatioFunction: zoomWithPositions,
    zIndex: true,
    labelColor: { color: palette.label },
    labelFont: LABEL_FONT,
    labelSize: LABEL_SIZE,
    labelWeight: LABEL_WEIGHT,
    labelRenderedSizeThreshold: 0,
    defaultDrawNodeHover: groupHoverDrawer(palette),
    enableEdgeEvents: false,
    renderEdgeLabels: false,
  };
}

type NodePositions = ReadonlyMap<string, Position>;

function nodePositions(graph: NetworkGraph): NodePositions {
  return new Map(graph.mapNodes((key, node): [string, Position] => [key, { x: node.x, y: node.y }]));
}

/**
 * Loads the week's graph. With `animate` (the Overlap mode), groups start where they are drawn and
 * Sigma moves them to the new week's positions. A week change mid-move cancels the running move
 * (the effect's cleanup) and starts from where the groups are drawn at that instant, not from
 * where the cut-off move was heading, so the groups do not jump.
 */
function GraphLoader({ graph, animate }: { graph: NetworkGraph; animate: boolean }) {
  const loadGraph = useLoadGraph<NetworkNode, NetworkEdge>();
  const sigma = useSigma<NetworkNode, NetworkEdge>();
  useEffect(() => {
    const drawnBefore = nodePositions(sigma.getGraph());
    loadGraph(graph);
    if (!animate) return;
    // Sigma's graph is its own copy of `graph`: moving its nodes leaves the week's graph intact.
    const drawn = sigma.getGraph();
    const targets: Record<string, Record<string, number>> = {};
    for (const [key, from] of drawnBefore) {
      if (!graph.hasNode(key) || !drawn.hasNode(key)) continue;
      targets[key] = { x: graph.getNodeAttribute(key, "x"), y: graph.getNodeAttribute(key, "y") };
      drawn.mergeNodeAttributes(key, from);
    }
    if (Object.keys(targets).length === 0) return;
    return animateNodes(drawn, targets, { duration: WEEK_MOTION_MS });
  }, [loadGraph, sigma, graph, animate]);
  return null;
}

interface FocusProps {
  graph: NetworkGraph;
  focusKey: string | null;
  onHover: (key: string | null) => void;
  dimmed: string;
}

/** Hovering a group (never a point) focuses it: its ties stay, every other group and tie fades. */
function FocusHighlight({ graph, focusKey, onHover, dimmed }: FocusProps) {
  const sigma = useSigma<NetworkNode, NetworkEdge>();
  const registerEvents = useRegisterEvents();
  const setSettings = useSetSettings<NetworkNode, NetworkEdge>();
  useEffect(() => {
    registerEvents({
      enterNode: ({ node }) => {
        if (focusOn(graph, node)) onHover(node);
      },
      leaveNode: () => onHover(null),
    });
  }, [registerEvents, graph, onHover]);
  useEffect(() => {
    const focus = focusOn(graph, focusKey);
    // Ends come from Sigma's own copy of the graph, which may already hold the next week's ties.
    const drawn = sigma.getGraph();
    setSettings({
      nodeReducer: (key, node) => nodeAppearance(key, node, focus, dimmed),
      edgeReducer: (edge, data) => edgeAppearance(data, drawn.extremities(edge), focus),
    });
  }, [sigma, setSettings, graph, focusKey, dimmed]);
  return null;
}

/**
 * The Overlap mode's contour layer, one per view. It is bound once and removed on mode change and
 * unmount; it is not rebound when the week or the focus changes: it reads the groups' drawn
 * positions on every render (so it follows Sigma's week animation frame by frame) and the latest
 * styles from a ref, and a rebind per frame would create a WebGL context per frame.
 */
function OverlapContours({ styles }: { styles: readonly ContourStyle[] }) {
  // The layer reads only display data (position and size), so the untyped instance is enough.
  const sigma = useSigma();
  const latest = useRef(styles);
  const groups = styles.length;
  useEffect(() => {
    latest.current = styles;
    sigma.scheduleRender();
  }, [sigma, styles]);
  useEffect(() => {
    if (groups === 0) return;
    return bindGroupContours(sigma, groups, () => latest.current);
  }, [sigma, groups]);
  return null;
}

/** Search by group label: the match is focused and the camera moves to it. */
function GroupSearch({ labels, onSelect }: { labels: string[]; onSelect: (key: string | null) => void }) {
  const [query, setQuery] = useState("");
  const [missing, setMissing] = useState(false);
  const { gotoNode } = useCamera({ duration: ZOOM_DURATION_MS });
  const listId = useId();
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const label = findGroup(labels, query);
    setMissing(label === null);
    onSelect(label === null ? null : groupKey(label));
    if (label !== null) gotoNode(groupKey(label));
  };
  const clear = () => {
    setQuery("");
    setMissing(false);
    onSelect(null);
  };
  return (
    <form role="search" onSubmit={submit} className="absolute left-2 top-2 z-[101] flex items-center gap-1">
      <input
        type="search"
        list={listId}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search a group"
        aria-label="Search a group by label"
        className="h-8 w-40 rounded-md border bg-card px-2 text-sm text-foreground placeholder:text-muted-foreground"
      />
      <datalist id={listId}>
        {labels.map((label) => (
          <option key={label} value={label} />
        ))}
      </datalist>
      <button type="submit" title="Find group" className="rounded-md border bg-card p-1.5 hover:bg-accent">
        <Search className="h-4 w-4" aria-hidden />
      </button>
      {query !== "" && (
        <button type="button" title="Clear search" onClick={clear} className="rounded-md border bg-card p-1.5 hover:bg-accent">
          <X className="h-4 w-4" aria-hidden />
        </button>
      )}
      {missing && <span className="text-xs text-muted-foreground">No group matches.</span>}
    </form>
  );
}

export default function SigmaNetwork({ groups, edges, week, maxTie, mode, seed }: SigmaNetworkProps) {
  const palette = useMemo(() => networkPalette(groups, readThemeVariable), [groups]);
  const settings = useMemo(() => sigmaSettings(palette), [palette]);
  const positions = useMemo(() => layoutPositions(groups, edges), [groups, edges]);
  const points = useMemo(() => anonymousPoints(groups, seed, groupNodeRadius), [groups, seed]);
  const individuals = mode === "individuals";
  const overlapMode = mode === "overlap";
  const radii = useMemo(() => new Map(groups.map((g) => [g.group, groupNodeRadius(g.n_persons)])), [groups]);
  const weekly = useMemo(
    () => (overlapMode && week !== null ? weekOverlaps(edges, week, positions.keys()) : NO_OVERLAPS),
    [overlapMode, edges, week, positions],
  );
  const graph = useMemo(() => {
    const ties: GroupTie[] = overlapMode ? weekly.lines : publishedTies(edges, week, positions.keys());
    return networkGraph({
      groups,
      positions: overlapMode ? relaxPositions(positions, radii, weekly.overlaps) : positions,
      ties,
      maxTie,
      palette,
      points: individuals ? points : null,
      overlaps: overlapMode ? weekly.overlaps : undefined,
    });
  }, [groups, positions, radii, edges, week, maxTie, palette, individuals, points, overlapMode, weekly]);
  const labels = useMemo(() => [...positions.keys()], [positions]);
  const people = useMemo(() => new Map(groups.map((g) => [g.group, g.n_persons])), [groups]);
  const [hovered, setHovered] = useState<string | null>(null);
  const [searched, setSearched] = useState<string | null>(null);
  const focusKey = hovered ?? searched;
  const contours = useMemo(
    () => (overlapMode ? contourStyles(labels, palette.groups, focusOn(graph, focusKey)) : NO_CONTOURS),
    [overlapMode, labels, palette, graph, focusKey],
  );
  // In the Overlap mode the contours do the dimming; a dimmed disc stays as transparent as the rest.
  const dimmed = overlapMode ? OVERLAP_DISC_COLOR : palette.dimmed;

  return (
    <div role="group" aria-label={`Group network for the week of ${week ?? "none"}`} data-mode={mode}>
      <SigmaContainer<NetworkNode, NetworkEdge>
        graph={UndirectedGraph}
        settings={settings}
        className="overflow-hidden rounded-lg border"
        style={{ height: NETWORK_HEIGHT }}
      >
        <GraphLoader graph={graph} animate={overlapMode} />
        <FocusHighlight graph={graph} focusKey={focusKey} onHover={setHovered} dimmed={dimmed} />
        {overlapMode && <OverlapContours styles={contours} />}
        <GroupSearch labels={labels} onSelect={setSearched} />
        <FocusSummary graph={graph} focusKey={focusKey} people={people} overlaps={overlapMode ? weekly.overlaps : null} />
        <ControlsContainer position="top-right">
          <ZoomControl animationDuration={ZOOM_DURATION_MS} labels={{ zoomIn: "Zoom in", zoomOut: "Zoom out", reset: "Show the whole network" }}>
            <ZoomIn className="h-4 w-4" aria-hidden />
            <ZoomOut className="h-4 w-4" aria-hidden />
            <Maximize className="h-4 w-4" aria-hidden />
          </ZoomControl>
          <FullScreenControl labels={{ enter: "Full screen", exit: "Leave full screen" }}>
            <Maximize2 className="h-4 w-4" aria-hidden />
            <Minimize2 className="h-4 w-4" aria-hidden />
          </FullScreenControl>
        </ControlsContainer>
        <NetworkLegend groups={groups} maxTie={maxTie} mode={mode} />
      </SigmaContainer>
    </div>
  );
}
