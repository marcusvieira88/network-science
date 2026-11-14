import { useMemo, useState } from "react";

import { TimeSlider } from "@/components/TimeSlider";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { CommunityEdgeRow, CommunityGroupRow, PublicEvent } from "@/lib/data";
import { formatNumber } from "@/lib/format";
import { groupColor, layoutGroups, weekGraph } from "@/lib/network";

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
}

export function CommunityGraph({ groups, edges, weeks, events, minGroupSize }: CommunityGraphProps) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const placed = useMemo(() => layoutGroups(groups, edges, WIDTH, HEIGHT), [groups, edges]);
  const order = useMemo(() => placed.map((g) => g.group), [placed]);
  const position = useMemo(() => new Map(placed.map((g) => [g.group, g])), [placed]);
  // One width scale for all weeks, so a thicker line always means a heavier tie.
  const maxWeeklyTie = useMemo(
    () => Math.max(1, ...weeks.map((w) => weekGraph(edges, w).ties[0]?.total ?? 0)),
    [edges, weeks],
  );
  const week = weeks[index] ?? null;
  const graph = useMemo(() => weekGraph(edges, week), [edges, week]);
  const edgeScale = MAX_EDGE_WIDTH / maxWeeklyTie;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Ties between groups, week by week</CardTitle>
        <CardDescription>
          Each circle is a group of at least {minGroupSize} people, never an individual. Groups are fixed in the
          baseline period; circle area follows group size and line width follows the weekly weight of messages
          between groups. Group membership is not published.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
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
                      <span
                        className="h-2.5 w-2.5 rounded-full"
                        style={{ background: groupColor(node.group, order) }}
                        aria-hidden
                      />
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
