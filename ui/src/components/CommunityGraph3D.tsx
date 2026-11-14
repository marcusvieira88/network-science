/**
 * The WebGL canvas of the group network. Loaded on demand (React.lazy) so that three.js stays out
 * of the bundle the other views load. All data mapping lives in lib/network3d.ts.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ForceGraph3D, { type ForceGraphMethods } from "react-force-graph-3d";

import type { GraphLink, GraphNode } from "@/lib/network3d";
import { BACKGROUND_COLOR, LAYOUT_TICKS, NODE_RELATIVE_SIZE, nodeLabel } from "@/lib/network3d";

const CANVAS_HEIGHT = 460;
const FIT_DURATION_MS = 600;
const FIT_PADDING = 40;
const NODE_RESOLUTION = 24;
const NODE_OPACITY = 0.95;
/** Per-link opacity comes from each link's rgba colour (lib/network3d.ts); this multiplies it. */
const LINK_OPACITY = 1;

export interface CommunityGraph3DProps {
  nodes: GraphNode[];
  /** Ties of the selected week. */
  links: GraphLink[];
  /** Ties of all weeks, the layout's only input. */
  layout: GraphLink[];
  week: string | null;
}

type Placed = GraphNode & { x?: number; y?: number; z?: number; fx?: number; fy?: number; fz?: number };

function useContainerWidth(): [React.RefObject<HTMLDivElement>, number] {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const element = ref.current;
    if (!element) return undefined;
    setWidth(element.clientWidth);
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(entry.contentRect.width);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

/** Freeze every node where the layout left it, so changing the week never moves a group. */
function fixPositions(nodes: Placed[]): void {
  for (const node of nodes) {
    node.fx = node.x;
    node.fy = node.y;
    node.fz = node.z;
  }
}

export default function CommunityGraph3D({ nodes, links, layout, week }: CommunityGraph3DProps) {
  const [containerRef, width] = useContainerWidth();
  const graphRef = useRef<ForceGraphMethods<Placed, GraphLink>>();
  // The engine adds positions to these objects; keep the same objects for the life of the view.
  const placed = useMemo<Placed[]>(() => nodes.map((node) => ({ ...node })), [nodes]);
  const [frozen, setFrozen] = useState(false);
  // Links are copied because the engine replaces source and target ids with node objects.
  const graphData = useMemo(
    () => ({ nodes: placed, links: (frozen ? links : layout).map((tie) => ({ ...tie })) }),
    [placed, frozen, links, layout],
  );

  const onEngineStop = useCallback(() => {
    if (frozen) return;
    fixPositions(placed);
    setFrozen(true);
    graphRef.current?.zoomToFit(FIT_DURATION_MS, FIT_PADDING);
  }, [frozen, placed]);

  return (
    <div
      ref={containerRef}
      className="overflow-hidden rounded-lg border"
      style={{ height: CANVAS_HEIGHT, background: BACKGROUND_COLOR }}
      role="img"
      aria-label={`3D group network for the week of ${week ?? "none"}`}
    >
      {width > 0 && (
        <ForceGraph3D<Placed, GraphLink>
          ref={graphRef}
          graphData={graphData}
          width={width}
          height={CANVAS_HEIGHT}
          backgroundColor={BACKGROUND_COLOR}
          showNavInfo={false}
          nodeId="id"
          nodeVal="val"
          nodeRelSize={NODE_RELATIVE_SIZE}
          nodeColor="color"
          nodeOpacity={NODE_OPACITY}
          nodeResolution={NODE_RESOLUTION}
          nodeLabel={(node) => nodeLabel(node)}
          linkWidth="width"
          linkColor="color"
          linkOpacity={LINK_OPACITY}
          linkVisibility={frozen}
          enableNodeDrag={false}
          warmupTicks={frozen ? 0 : LAYOUT_TICKS}
          cooldownTicks={0}
          onEngineStop={onEngineStop}
        />
      )}
    </div>
  );
}
