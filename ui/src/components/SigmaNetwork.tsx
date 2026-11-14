/**
 * The WebGL group network (Sigma.js via React Sigma). Loaded on demand (React.lazy) so Sigma and
 * graphology stay out of the bundle the other views load. All data mapping lives in
 * lib/sigmaNetwork.ts; this file wires it to Sigma: loading the week's graph, hover and search
 * focus, zoom and fullscreen controls, and the legend.
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
import { type FormEvent, useEffect, useId, useMemo, useState } from "react";
import type { Settings } from "sigma/settings";

import { type NetworkMode, anonymousPoints } from "@/lib/cells";
import type { CommunityEdgeRow, CommunityGroupRow } from "@/lib/data";
import { formatNumber } from "@/lib/format";
import { NETWORK_HEIGHT, publishedTies } from "@/lib/network";
import {
  type NetworkEdge,
  type NetworkGraph,
  type NetworkNode,
  type NetworkPalette,
  edgeAppearance,
  findGroup,
  focusOn,
  groupHoverDrawer,
  groupKey,
  groupNodeRadius,
  layoutPositions,
  legendSizes,
  legendWeights,
  networkGraph,
  networkPalette,
  nodeAppearance,
} from "@/lib/sigmaNetwork";

const LABEL_SIZE = 12;
const LABEL_WEIGHT = "600";
const LABEL_FONT = "'Inter Variable', ui-sans-serif, system-ui, sans-serif";
const ZOOM_DURATION_MS = 300;
const LEGEND_MAX_RADIUS = 10;
const LEGEND_MAX_WIDTH = 5;
const LEGEND_LINE_LENGTH = 24;
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

function GraphLoader({ graph }: { graph: NetworkGraph }) {
  const loadGraph = useLoadGraph<NetworkNode, NetworkEdge>();
  useEffect(() => loadGraph(graph), [loadGraph, graph]);
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

/** The focused group's published facts: label, size and how many groups it has a tie with. */
function FocusSummary({ graph, focusKey, people }: { graph: NetworkGraph; focusKey: string | null; people: ReadonlyMap<string, number> }) {
  const focus = focusOn(graph, focusKey);
  if (!focus) return null;
  const label = graph.getNodeAttribute(focus.key, "label") ?? "";
  return (
    <p role="status" className="absolute right-12 top-2 z-[101] rounded-md border bg-card px-2 py-1 text-xs">
      Group {label} · {people.get(label)} people · tied to {focus.neighbours.size}{" "}
      {focus.neighbours.size === 1 ? "group" : "groups"} this week
    </p>
  );
}

function Legend({ groups, maxTie, individuals }: { groups: CommunityGroupRow[]; maxTie: number; individuals: boolean }) {
  const sizes = legendSizes(groups, LEGEND_MAX_RADIUS);
  const weights = legendWeights(maxTie, LEGEND_MAX_WIDTH);
  return (
    <div
      data-testid="network-legend"
      className="absolute bottom-2 left-2 z-[101] space-y-1 rounded-md border bg-card/90 px-2 py-1.5 text-xs text-muted-foreground"
    >
      <div className="flex items-center gap-2">
        <span>Circle area: people</span>
        {sizes.map((sample) => (
          <span key={sample.people} className="flex items-center gap-1">
            <svg width={2 * LEGEND_MAX_RADIUS} height={2 * LEGEND_MAX_RADIUS} aria-hidden>
              <circle cx={LEGEND_MAX_RADIUS} cy={LEGEND_MAX_RADIUS} r={sample.radius} fill="hsl(var(--muted-foreground))" />
            </svg>
            {sample.people}
          </span>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <span>Line width: weekly weight</span>
        {weights.map((sample) => (
          <span key={sample.weight} className="flex items-center gap-1">
            <svg width={LEGEND_LINE_LENGTH} height={LEGEND_MAX_WIDTH} aria-hidden>
              <line
                x1={0}
                x2={LEGEND_LINE_LENGTH}
                y1={LEGEND_MAX_WIDTH / 2}
                y2={LEGEND_MAX_WIDTH / 2}
                stroke="hsl(var(--muted-foreground))"
                strokeWidth={sample.width}
              />
            </svg>
            {formatNumber(sample.weight)}
          </span>
        ))}
      </div>
      {individuals && <div>Each small dot: one anonymous person (illustrative position)</div>}
    </div>
  );
}

export default function SigmaNetwork({ groups, edges, week, maxTie, mode, seed }: SigmaNetworkProps) {
  const palette = useMemo(() => networkPalette(groups, readThemeVariable), [groups]);
  const settings = useMemo(() => sigmaSettings(palette), [palette]);
  const positions = useMemo(() => layoutPositions(groups, edges), [groups, edges]);
  const points = useMemo(() => anonymousPoints(groups, seed, groupNodeRadius), [groups, seed]);
  const individuals = mode === "individuals";
  const graph = useMemo(
    () =>
      networkGraph({
        groups,
        positions,
        ties: publishedTies(edges, week, positions.keys()),
        maxTie,
        palette,
        points: individuals ? points : null,
      }),
    [groups, positions, edges, week, maxTie, palette, individuals, points],
  );
  const labels = useMemo(() => [...positions.keys()], [positions]);
  const people = useMemo(() => new Map(groups.map((g) => [g.group, g.n_persons])), [groups]);
  const [hovered, setHovered] = useState<string | null>(null);
  const [searched, setSearched] = useState<string | null>(null);
  const focusKey = hovered ?? searched;

  return (
    <div role="group" aria-label={`Group network for the week of ${week ?? "none"}`} data-mode={mode}>
      <SigmaContainer<NetworkNode, NetworkEdge>
        graph={UndirectedGraph}
        settings={settings}
        className="overflow-hidden rounded-lg border"
        style={{ height: NETWORK_HEIGHT }}
      >
        <GraphLoader graph={graph} />
        <FocusHighlight graph={graph} focusKey={focusKey} onHover={setHovered} dimmed={palette.dimmed} />
        <GroupSearch labels={labels} onSelect={setSearched} />
        <FocusSummary graph={graph} focusKey={focusKey} people={people} />
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
        <Legend groups={groups} maxTie={maxTie} individuals={individuals} />
      </SigmaContainer>
    </div>
  );
}
