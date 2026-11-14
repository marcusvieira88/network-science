/**
 * The WebGL canvas of the group network, drawn as glowing cells with signals travelling along the
 * ties. Loaded on demand (React.lazy) so that three.js stays out of the bundle the other views
 * load. All data mapping lives in lib/network3d.ts and lib/cells.ts.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ForceGraph3D, { type ForceGraphMethods } from "react-force-graph-3d";
import { Vector2 } from "three";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";

import { cellObject, glowTexture } from "@/components/cellObjects";
import type { NetworkMode, Point } from "@/lib/cells";
import type { GraphLink, GraphNode } from "@/lib/network3d";
import { BACKGROUND_COLOR, LAYOUT_TICKS, LINK_CURVATURE, PARTICLE_COLOR, nodeLabel } from "@/lib/network3d";

const CANVAS_HEIGHT = 460;
const FIT_DURATION_MS = 600;
const FIT_PADDING = 40;
/** Per-link opacity comes from each link's rgba colour (lib/network3d.ts); this multiplies it. */
const LINK_OPACITY = 1;
const PARTICLE_WIDTH = 1.2;
/** Bloom makes the cells and signals glow; a low threshold lets the dim axons bloom too. */
const BLOOM_STRENGTH = 1.1;
const BLOOM_RADIUS = 0.6;
const BLOOM_THRESHOLD = 0.1;

export interface CommunityGraph3DProps {
  nodes: GraphNode[];
  /** Ties of the selected week. */
  links: GraphLink[];
  /** Ties of all weeks, the layout's only input. */
  layout: GraphLink[];
  week: string | null;
  mode: NetworkMode;
  /** Anonymous points per group label, drawn in the Individuals mode only. */
  points: Map<string, Point[]>;
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

/** Add the bloom pass once the graph exists; it stays for the life of the canvas. */
function useBloom(graphRef: React.MutableRefObject<ForceGraphMethods<Placed, GraphLink> | undefined>, width: number): void {
  const added = useRef(false);
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph || added.current) return;
    graph
      .postProcessingComposer()
      .addPass(new UnrealBloomPass(new Vector2(width, CANVAS_HEIGHT), BLOOM_STRENGTH, BLOOM_RADIUS, BLOOM_THRESHOLD));
    added.current = true;
  }, [graphRef, width]);
}

export default function CommunityGraph3D({ nodes, links, layout, week, mode, points }: CommunityGraph3DProps) {
  const [containerRef, width] = useContainerWidth();
  const graphRef = useRef<ForceGraphMethods<Placed, GraphLink>>();
  useBloom(graphRef, width);
  const glow = useMemo(() => glowTexture(), []);
  useEffect(() => () => glow.dispose(), [glow]);
  const drawCell = useCallback(
    (node: Placed) => cellObject(node, mode, points.get(node.id) ?? [], glow),
    [mode, points, glow],
  );
  // Points carry no label: in the Individuals mode nothing is shown on hover.
  const label = useCallback((node: Placed) => (mode === "groups" ? nodeLabel(node) : ""), [mode]);
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
      data-mode={mode}
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
          nodeThreeObject={drawCell}
          nodeLabel={label}
          linkWidth="width"
          linkColor="color"
          linkOpacity={LINK_OPACITY}
          linkCurvature={LINK_CURVATURE}
          linkDirectionalParticles="particles"
          linkDirectionalParticleSpeed="particleSpeed"
          linkDirectionalParticleWidth={PARTICLE_WIDTH}
          linkDirectionalParticleColor={() => PARTICLE_COLOR}
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
