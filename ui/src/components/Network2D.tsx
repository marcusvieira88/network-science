/** The SVG group network: the fallback where WebGL is unavailable or the WebGL view fails. */
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { Point } from "@/lib/cells";
import { formatNumber } from "@/lib/format";
import { type GroupTie, type PlacedGroup, type WeekGraph, MEMBRANE_OPACITY, TIE_OPACITY, groupColor } from "@/lib/network";

/** The SVG's view box; the layout places groups inside it. */
export const SVG_WIDTH = 640;
export const SVG_HEIGHT = 420;
const MAX_EDGE_WIDTH = 14;
const POINT_RADIUS = 1.6;

interface Network2DProps {
  placed: PlacedGroup[];
  graph: WeekGraph;
  /** The week's ties between real groups. */
  ties: GroupTie[];
  week: string | null;
  maxTie: number;
  /** Anonymous points per group label, relative to the group's centre; null in the Groups mode. */
  points: Map<string, Point[]> | null;
}

/**
 * Every anonymous point as a bare circle: no key in the DOM, no label, no title, no tooltip and no
 * pointer events, so nothing can be learned from or attached to a single point.
 */
function AnonymousPoints({ placed, points }: { placed: PlacedGroup[]; points: Map<string, Point[]> }) {
  return (
    <g data-testid="anonymous-points" aria-hidden="true" pointerEvents="none">
      {placed.flatMap((node) =>
        (points.get(node.group) ?? []).map(([dx = 0, dy = 0], index) => (
          <circle
            key={`${node.group}-${index}`}
            cx={node.x + dx}
            cy={node.y + dy}
            r={POINT_RADIUS}
            fill="hsl(var(--foreground))"
          />
        )),
      )}
    </g>
  );
}

/** The SVG network: the fallback where WebGL is unavailable or the WebGL view fails. */
export function Network2D({ placed, graph, ties, week, maxTie, points }: Network2DProps) {
  const order = placed.map((g) => g.group);
  const position = new Map(placed.map((g) => [g.group, g]));
  const edgeScale = MAX_EDGE_WIDTH / maxTie;
  return (
    <TooltipProvider delayDuration={100}>
      <svg
        viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
        className="h-auto w-full rounded-lg border bg-background/60"
        role="img"
        aria-label={`Group network for the week of ${week ?? "none"}`}
      >
        {ties.map((tie) => {
          const a = position.get(tie.a);
          const b = position.get(tie.b);
          if (!a || !b) return null;
          return (
            <line
              key={`${tie.a}-${tie.b}`}
              data-testid="tie"
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke="hsl(var(--muted-foreground))"
              strokeOpacity={TIE_OPACITY}
              strokeLinecap="round"
              strokeWidth={Math.max(1, tie.total * edgeScale)}
            />
          );
        })}
        {placed.map((node) => (
          <Tooltip key={node.group}>
            <TooltipTrigger asChild>
              <g data-testid="group-node" tabIndex={0} className="cursor-default outline-none focus-visible:opacity-80">
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={node.radius}
                  fill={groupColor(node.group, order)}
                  fillOpacity={points ? MEMBRANE_OPACITY : 1}
                  stroke="hsl(var(--background))"
                  strokeWidth={2}
                />
                {!points && (
                  <text
                    x={node.x}
                    y={node.y}
                    dy="0.35em"
                    textAnchor="middle"
                    className="pointer-events-none fill-foreground text-[11px] font-semibold"
                  >
                    {node.group}
                  </text>
                )}
              </g>
            </TooltipTrigger>
            <TooltipContent>
              <div className="font-semibold">Group {node.group}</div>
              <div>{node.nPersons} people</div>
              <div>Weight within the group this week: {formatNumber(graph.internal[node.group] ?? 0)}</div>
            </TooltipContent>
          </Tooltip>
        ))}
        {points && <AnonymousPoints placed={placed} points={points} />}
      </svg>
    </TooltipProvider>
  );
}
