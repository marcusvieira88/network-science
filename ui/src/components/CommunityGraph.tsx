import { Suspense, lazy, useMemo, useState } from "react";

import { RenderFallback } from "@/components/RenderFallback";
import { TimeSlider } from "@/components/TimeSlider";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { CommunityEdgeRow, CommunityGroupRow, PublicEvent } from "@/lib/data";
import { formatNumber } from "@/lib/format";
import { type PlacedGroup, type WeekGraph, groupColor, layoutGroups, maxWeeklyTie, weekGraph } from "@/lib/network";
import { graphNodes, layoutLinks, weekLinks } from "@/lib/network3d";
import { supportsWebGL } from "@/lib/webgl";

const CommunityGraph3D = lazy(() => import("@/components/CommunityGraph3D"));

const WIDTH = 640;
const HEIGHT = 420;
const MAX_EDGE_WIDTH = 14;
const TOP_TIES = 8;

interface CommunityGraphProps {
  groups: CommunityGroupRow[];
  edges: CommunityEdgeRow[];
  weeks: string[];
  events: PublicEvent[];
  minGroupSize: number;
  /** Draw the 3D view; defaults to whether the browser has WebGL. */
  webgl?: boolean;
}

interface Network2DProps {
  placed: PlacedGroup[];
  graph: WeekGraph;
  week: string | null;
  maxTie: number;
}

/** The flat network: the fallback where WebGL is unavailable. */
function Network2D({ placed, graph, week, maxTie }: Network2DProps) {
  const order = placed.map((g) => g.group);
  const position = new Map(placed.map((g) => [g.group, g]));
  const edgeScale = MAX_EDGE_WIDTH / maxTie;
  return (
    <TooltipProvider delayDuration={100}>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-auto w-full rounded-lg border bg-background/60"
        role="img"
        aria-label={`Group network for the week of ${week ?? "none"}`}
      >
        {graph.ties.map((tie) => {
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
              strokeOpacity={0.55}
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
                  stroke="hsl(var(--background))"
                  strokeWidth={2}
                />
                <text
                  x={node.x}
                  y={node.y}
                  dy="0.35em"
                  textAnchor="middle"
                  className="pointer-events-none fill-foreground text-[11px] font-semibold"
                >
                  {node.group}
                </text>
              </g>
            </TooltipTrigger>
            <TooltipContent>
              <div className="font-semibold">Group {node.group}</div>
              <div>{node.nPersons} people</div>
              <div>Weight within the group this week: {formatNumber(graph.internal[node.group] ?? 0)}</div>
            </TooltipContent>
          </Tooltip>
        ))}
      </svg>
    </TooltipProvider>
  );
}

function Loading3D() {
  return (
    <div className="flex h-[460px] items-center justify-center rounded-lg border bg-background/60 text-sm text-muted-foreground">
      Loading the 3D view…
    </div>
  );
}

export function CommunityGraph({ groups, edges, weeks, events, minGroupSize, webgl }: CommunityGraphProps) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [use3D] = useState(() => webgl ?? supportsWebGL());
  const placed = useMemo(() => layoutGroups(groups, edges, WIDTH, HEIGHT), [groups, edges]);
  const nodes = useMemo(() => graphNodes(groups), [groups]);
  const allTies = useMemo(() => layoutLinks(groups, edges), [groups, edges]);
  // One scale for all weeks, so a thicker line always means a heavier tie.
  const maxTie = useMemo(() => maxWeeklyTie(edges, weeks), [edges, weeks]);
  const week = weeks[index] ?? null;
  const graph = useMemo(() => weekGraph(edges, week), [edges, week]);
  const links = useMemo(() => weekLinks(edges, week, maxTie, nodes.map((n) => n.id)), [edges, week, maxTie, nodes]);
  const swatch = useMemo(() => {
    const order = placed.map((g) => g.group);
    const accent = new Map(nodes.map((n) => [n.id, n.color]));
    return (group: string) => (use3D ? (accent.get(group) ?? "") : groupColor(group, order));
  }, [placed, nodes, use3D]);
  const shape = use3D ? "sphere" : "circle";
  const sizeRule = use3D ? "sphere volume" : "circle area";
  const flat = <Network2D placed={placed} graph={graph} week={week} maxTie={maxTie} />;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Ties between groups, week by week</CardTitle>
        <CardDescription>
          Each {shape} is a group of at least {minGroupSize} people, never an individual. Groups are fixed in the
          baseline period; {sizeRule} follows group size and line width follows the weekly weight of messages
          between groups. Group membership is not published.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {use3D ? (
          <div className="space-y-2">
            <RenderFallback fallback={flat}>
              <Suspense fallback={<Loading3D />}>
                <CommunityGraph3D nodes={nodes} links={links} layout={allTies} week={week} />
              </Suspense>
            </RenderFallback>
            <p className="text-xs text-muted-foreground">
              Drag to rotate, scroll to zoom, right-drag to pan. Hover a sphere for its group label and size.
            </p>
          </div>
        ) : (
          flat
        )}
        <TimeSlider
          weeks={weeks}
          index={index}
          onIndexChange={setIndex}
          playing={playing}
          onPlayingChange={setPlaying}
          events={events}
        />
        <div className="grid gap-6 md:grid-cols-2">
          <div>
            <h3 className="mb-2 text-sm font-medium">Strongest ties this week</h3>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Groups</TableHead>
                  <TableHead className="text-right">Weight</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {graph.ties.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={2} className="text-muted-foreground">
                      No published tie between groups this week.
                    </TableCell>
                  </TableRow>
                )}
                {graph.ties.slice(0, TOP_TIES).map((tie) => (
                  <TableRow key={`${tie.a}-${tie.b}`}>
                    <TableCell>
                      {tie.a} ↔ {tie.b}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">{formatNumber(tie.total)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div>
            <h3 className="mb-2 text-sm font-medium">Groups</h3>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Group</TableHead>
                  <TableHead className="text-right">People</TableHead>
                  <TableHead className="text-right">Within-group weight</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {placed.map((node) => (
                  <TableRow key={node.group}>
                    <TableCell className="flex items-center gap-2">
                      <span className="h-2.5 w-2.5 rounded-full" style={{ background: swatch(node.group) }} aria-hidden />
                      {node.group}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">{node.nPersons}</TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {formatNumber(graph.internal[node.group] ?? 0)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
