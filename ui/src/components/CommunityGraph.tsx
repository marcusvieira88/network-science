import { Suspense, lazy, useMemo, useState } from "react";

import { RenderFallback } from "@/components/RenderFallback";
import { TimeSlider } from "@/components/TimeSlider";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { type NetworkMode, type Point, NETWORK_MODES, anonymousPoints } from "@/lib/cells";
import type { CommunityEdgeRow, CommunityGroupRow, Period, PublicEvent } from "@/lib/data";
import { formatNumber } from "@/lib/format";
import {
  type GroupTie,
  type PlacedGroup,
  type WeekGraph,
  MEMBRANE_OPACITY,
  NETWORK_HEIGHT,
  OTHER_GROUP,
  groupColor,
  groupRadius,
  layoutGroups,
  maxWeeklyTie,
  namedGroups,
  publishedTies,
  weekGraph,
} from "@/lib/network";
import {
  OUTSIDE_SHORT,
  outsideExplanation,
  outsideLabel,
  outsidePeople,
  outsideTies,
  outsideWeekCaption,
  outsideWeekShare,
} from "@/lib/outside";
import { weekInPlainWords } from "@/lib/plainLanguage";
import { supportsWebGL } from "@/lib/webgl";

const SigmaNetwork = lazy(() => import("@/components/SigmaNetwork"));

const WIDTH = 640;
const HEIGHT = 420;
const MAX_EDGE_WIDTH = 14;
const TOP_TIES = 8;
const POINT_RADIUS = 1.6;

const MODE_LABELS: Record<NetworkMode, string> = {
  groups: "Groups",
  individuals: "Individuals (anonymous)",
  overlap: "Overlap",
};

function isNetworkMode(value: string): value is NetworkMode {
  return (NETWORK_MODES as readonly string[]).includes(value);
}

interface CommunityGraphProps {
  groups: CommunityGroupRow[];
  edges: CommunityEdgeRow[];
  weeks: string[];
  events: PublicEvent[];
  minGroupSize: number;
  /** The run seed: scatters the illustrative points of the Individuals mode. */
  seed: number;
  /** The baseline the groups were fixed on; names the outside bucket ("Outside the 2000 groups"). */
  baseline: Period | null;
  /** Draw the WebGL (Sigma.js) view; defaults to whether the browser has WebGL. */
  webgl?: boolean;
}

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
function Network2D({ placed, graph, ties, week, maxTie, points }: Network2DProps) {
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

function LoadingNetwork() {
  return (
    <div
      className="flex items-center justify-center rounded-lg border bg-background/60 text-sm text-muted-foreground"
      style={{ height: NETWORK_HEIGHT }}
    >
      Loading the network view…
    </div>
  );
}

interface OutsideCaptionProps {
  edges: CommunityEdgeRow[];
  week: string | null;
  people: number;
  minGroupSize: number;
  baseline: Period | null;
}

/** Above the graph: how much of the week's mail involves the outside bucket, and what it is. */
function OutsideCaption({ edges, week, people, minGroupSize, baseline }: OutsideCaptionProps) {
  return (
    <div data-testid="outside-caption" className="space-y-1 rounded-lg border border-dashed px-3 py-2 text-sm">
      <p className="font-medium">{outsideWeekCaption(outsideWeekShare(edges, week), baseline)}</p>
      <p className="text-muted-foreground">
        {outsideLabel(baseline)}: {outsideExplanation(people, minGroupSize, baseline)} They are not drawn.
      </p>
    </div>
  );
}

export function CommunityGraph({ groups, edges, weeks, events, minGroupSize, seed, baseline, webgl }: CommunityGraphProps) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [mode, setMode] = useState<NetworkMode>("groups");
  // Starts from WebGL support; turns false if the WebGL view fails, so the hint follows.
  const [useWebGL, setUseWebGL] = useState(() => webgl ?? supportsWebGL());
  // The outside bucket is not a group: it is never drawn, laid out or sized, only described.
  const named = useMemo(() => namedGroups(groups), [groups]);
  const outside = outsidePeople(groups);
  const labels = useMemo(() => named.map((g) => g.group), [named]);
  const placed = useMemo(() => layoutGroups(named, edges, WIDTH, HEIGHT), [named, edges]);
  // One scale for all weeks, so a thicker line always means a heavier tie.
  const maxTie = useMemo(() => maxWeeklyTie(edges, weeks, labels), [edges, weeks, labels]);
  const week = weeks[index] ?? null;
  const graph = useMemo(() => weekGraph(edges, week), [edges, week]);
  const ties = useMemo(() => publishedTies(edges, week, labels), [edges, week, labels]);
  const toOutside = useMemo(() => outsideTies(edges, week), [edges, week]);
  const order = useMemo(() => placed.map((g) => g.group), [placed]);
  const individuals = mode === "individuals";
  const points2D = useMemo(() => anonymousPoints(named, seed, groupRadius), [named, seed]);
  const flat = (
    <Network2D placed={placed} graph={graph} ties={ties} week={week} maxTie={maxTie} points={individuals ? points2D : null} />
  );

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
        <details className="rounded-lg border bg-background/40 px-4 py-3 text-sm" open>
          <summary className="cursor-pointer font-medium">How to read this</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-muted-foreground">
            <li>Each circle is a group of people who mostly email each other; bigger circles are bigger groups.</li>
            <li>A line between two circles means the groups exchanged mail that week; a thicker line means more mail.</li>
            <li>Move the slider (or press play) to watch the pattern change week by week; marks on it are known events.</li>
            <li>Hover a circle, or search for its label, to see only that group&apos;s links.</li>
            {outside !== null && (
              <li>
                People {outsideLabel(baseline).toLowerCase()} are not a group and are not drawn; the box above the
                graph says how much of the week&apos;s mail involves them.
              </li>
            )}
          </ul>
        </details>
        <p data-testid="week-summary" className="text-sm font-medium">
          {weekInPlainWords(week, ties)}
        </p>
        {outside !== null && (
          <OutsideCaption edges={edges} week={week} people={outside} minGroupSize={minGroupSize} baseline={baseline} />
        )}
        <div className="space-y-2">
          <Tabs value={mode} onValueChange={(value) => isNetworkMode(value) && setMode(value)}>
            <TabsList aria-label="Draw">
              {NETWORK_MODES.map((value) => (
                <TabsTrigger key={value} value={value} disabled={value === "overlap" && !useWebGL}>
                  {MODE_LABELS[value]}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          {individuals && (
            <p className="text-sm text-muted-foreground">
              Each point stands for one person in a group of at least {minGroupSize}; points are anonymous and their
              positions and links are illustrative, not individual data. Ties are measured between groups only.
            </p>
          )}
          {useWebGL && mode === "overlap" && (
            <p className="text-sm text-muted-foreground">
              Overlap = mail between two groups, not shared members — each person is in exactly one group. The
              week&apos;s heaviest ties by message count are drawn as overlapping circles; the others stay lines.
            </p>
          )}
          {!useWebGL && (
            <p className="text-sm text-muted-foreground">
              The Overlap mode needs WebGL; this browser shows the plain group network instead.
            </p>
          )}
        </div>
        {useWebGL ? (
          <div className="space-y-2">
            <RenderFallback fallback={flat} onFailure={() => setUseWebGL(false)}>
              <Suspense fallback={<LoadingNetwork />}>
                <SigmaNetwork groups={named} edges={edges} week={week} maxTie={maxTie} mode={mode} seed={seed} />
              </Suspense>
            </RenderFallback>
            <p className="text-xs text-muted-foreground">
              Scroll or use the buttons to zoom, drag to pan. Hover a group, or search for its label, to highlight
              its ties this week.
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
            <h3 id="strongest-ties" className="mb-2 text-sm font-medium">
              Strongest ties this week
            </h3>
            <Table aria-labelledby="strongest-ties">
              <TableHeader>
                <TableRow>
                  <TableHead>Groups</TableHead>
                  <TableHead className="text-right">Weight</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {ties.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={2} className="text-muted-foreground">
                      No published tie between groups this week.
                    </TableCell>
                  </TableRow>
                )}
                {ties.slice(0, TOP_TIES).map((tie) => (
                  <TableRow key={`${tie.a}-${tie.b}`}>
                    <TableCell>
                      {tie.a} ↔ {tie.b}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">{formatNumber(tie.total)}</TableCell>
                  </TableRow>
                ))}
                {toOutside.groups > 0 && (
                  <TableRow data-outside="true" className="text-muted-foreground">
                    <TableCell>
                      Any group ↔ {OUTSIDE_SHORT} ({toOutside.groups} {toOutside.groups === 1 ? "group" : "groups"})
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">{formatNumber(toOutside.weight)}</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
          <div>
            <h3 id="network-groups" className="mb-2 text-sm font-medium">
              Groups
            </h3>
            <Table aria-labelledby="network-groups">
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
                      <span className="h-2.5 w-2.5 rounded-full" style={{ background: groupColor(node.group, order) }} aria-hidden />
                      {node.group}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">{formatNumber(node.nPersons)}</TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {formatNumber(graph.internal[node.group] ?? 0)}
                    </TableCell>
                  </TableRow>
                ))}
                {outside !== null && (
                  <TableRow data-outside="true" className="text-muted-foreground">
                    <TableCell className="flex items-center gap-2">
                      <span className="h-2.5 w-2.5 rounded-full border border-dashed border-muted-foreground" aria-hidden />
                      {outsideLabel(baseline)}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">{formatNumber(outside)}</TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {formatNumber(graph.internal[OTHER_GROUP] ?? 0)}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
