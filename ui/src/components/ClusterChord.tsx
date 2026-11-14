import { type Chord, type ChordGroup, type ChordSubgroup, chord, ribbon } from "d3-chord";
import { arc } from "d3-shape";
import { useId, useMemo, useState } from "react";

import type { ClusterMatrix, GroupSummary } from "@/lib/clusters";
import { formatNumber, formatShare } from "@/lib/format";
import { OTHER_GROUP, groupColor } from "@/lib/network";
import { OUTSIDE_SHORT } from "@/lib/outside";

const SIZE = 440;
const OUTER_RADIUS = 180;
const ARC_WIDTH = 14;
const INNER_RADIUS = OUTER_RADIUS - ARC_WIDTH;
const LABEL_OFFSET = 12;
const PAD_ANGLE = 0.04;
/** Arcs narrower than this (radians) are left unlabelled; they are still in the table. */
const MIN_LABEL_ANGLE = 0.12;
const RIBBON_OPACITY = { rest: 0.65, highlighted: 0.9, dimmed: 0.08 } as const;
/** The outside bucket's arc: grey hatching, so it never reads as one more group. */
const HATCH_SIZE = 6;
const HATCH_BACKGROUND_OPACITY = 0.3;
const OUTSIDE_COLOR = "var(--chart-other)";

type Focus = { kind: "group"; index: number } | { kind: "ribbon"; source: number; target: number } | null;

const arcPath = arc<ChordGroup>().innerRadius(INNER_RADIUS).outerRadius(OUTER_RADIUS);
const ribbonPath = ribbon<Chord, ChordSubgroup>().radius(INNER_RADIUS - 1);
const layout = chord().padAngle(PAD_ANGLE);

function ribbonOpacity(focus: Focus, link: Chord): number {
  if (focus === null) return RIBBON_OPACITY.rest;
  const ends = [link.source.index, link.target.index];
  const lit =
    focus.kind === "group"
      ? ends.includes(focus.index)
      : link.source.index === focus.source && link.target.index === focus.target;
  return lit ? RIBBON_OPACITY.highlighted : RIBBON_OPACITY.dimmed;
}

function labelPosition(group: ChordGroup): { x: number; y: number; anchor: "start" | "end" } {
  const mid = (group.startAngle + group.endAngle) / 2;
  const radius = OUTER_RADIUS + LABEL_OFFSET;
  return { x: Math.sin(mid) * radius, y: -Math.cos(mid) * radius, anchor: mid < Math.PI ? "start" : "end" };
}

/** A label in a chord's short texts: the short form for the outside bucket. */
function shortName(group: string): string {
  return group === OTHER_GROUP ? OUTSIDE_SHORT : group;
}

interface FocusTextProps {
  focus: Focus;
  matrix: ClusterMatrix;
  summaries: GroupSummary[];
  outsideName: string;
}

function FocusText({ focus, matrix, summaries, outsideName }: FocusTextProps) {
  if (focus === null) return <>Hover or focus a group arc or a ribbon for its numbers.</>;
  if (focus.kind === "group") {
    const summary = summaries[focus.index];
    if (!summary) return null;
    if (summary.group === OTHER_GROUP) {
      return (
        <>
          <span className="font-semibold text-foreground">{outsideName}</span> · {formatNumber(summary.nPersons)} people
          · total weight {formatNumber(summary.total)} · not a community
        </>
      );
    }
    return (
      <>
        <span className="font-semibold text-foreground">Group {summary.group}</span> · {summary.nPersons} people ·
        total weight {formatNumber(summary.total)} · {formatShare(summary.withinShare)} stays within the group
      </>
    );
  }
  const a = shortName(matrix.groups[focus.source] ?? "");
  const b = shortName(matrix.groups[focus.target] ?? "");
  const ab = matrix.directed[focus.source]?.[focus.target] ?? 0;
  const ba = matrix.directed[focus.target]?.[focus.source] ?? 0;
  if (focus.source === focus.target) {
    return (
      <>
        <span className="font-semibold text-foreground">{matrix.groups[focus.source] === OTHER_GROUP ? `Among people ${outsideName.toLowerCase()}` : `Within group ${a}`}</span> · weight {formatNumber(ab)}
      </>
    );
  }
  return (
    <>
      <span className="font-semibold text-foreground">
        {a} ↔ {b}
      </span>{" "}
      · {a} → {b}: {formatNumber(ab)} · {b} → {a}: {formatNumber(ba)}
    </>
  );
}

interface ClusterChordProps {
  matrix: ClusterMatrix;
  summaries: GroupSummary[];
  label: string;
  /** The outside bucket's name on screen ("Outside the 2000 groups"). */
  outsideName: string;
}

/**
 * Chord diagram of group-to-group weight: arcs are groups, ribbons both directions summed. The
 * outside bucket stays last as a hatched grey arc with grey ribbons: it is not a group.
 */
export function ClusterChord({ matrix, summaries, label, outsideName }: ClusterChordProps) {
  const [focus, setFocus] = useState<Focus>(null);
  const chords = useMemo(() => layout(matrix.symmetric), [matrix]);
  const hatchId = `outside-hatch-${useId().replace(/:/g, "")}`;
  const isOutside = (index: number) => matrix.groups[index] === OTHER_GROUP;
  const color = (index: number) => groupColor(matrix.groups[index] ?? "", matrix.groups);
  const fullName = (index: number) => (isOutside(index) ? outsideName : (matrix.groups[index] ?? ""));
  const clear = () => setFocus(null);

  return (
    <div className="space-y-2">
      <svg
        viewBox={`${-SIZE / 2} ${-SIZE / 2} ${SIZE} ${SIZE}`}
        className="mx-auto h-auto w-full max-w-[460px]"
        role="img"
        aria-label={label}
      >
        <defs>
          <pattern id={hatchId} patternUnits="userSpaceOnUse" width={HATCH_SIZE} height={HATCH_SIZE} patternTransform="rotate(45)">
            <rect width={HATCH_SIZE} height={HATCH_SIZE} fill={OUTSIDE_COLOR} fillOpacity={HATCH_BACKGROUND_OPACITY} />
            <line x1={0} y1={0} x2={0} y2={HATCH_SIZE} stroke={OUTSIDE_COLOR} strokeWidth={HATCH_SIZE / 2} />
          </pattern>
        </defs>
        <g>
          {chords.map((link) => {
            const source = link.source.index;
            const target = link.target.index;
            const names = `${fullName(source)} and ${fullName(target)}`;
            const outsideRibbon = isOutside(source) || isOutside(target);
            return (
              <path
                key={`${source}-${target}`}
                data-testid="ribbon"
                d={ribbonPath(link) ?? undefined}
                fill={outsideRibbon ? OUTSIDE_COLOR : color(source)}
                fillOpacity={ribbonOpacity(focus, link)}
                stroke="hsl(var(--background))"
                strokeWidth={0.5}
                tabIndex={0}
                aria-label={source === target ? `Within ${fullName(source)}` : `Between ${names}`}
                className="outline-none transition-[fill-opacity]"
                onMouseEnter={() => setFocus({ kind: "ribbon", source, target })}
                onFocus={() => setFocus({ kind: "ribbon", source, target })}
                onMouseLeave={clear}
                onBlur={clear}
              />
            );
          })}
        </g>
        {chords.groups
          .filter((group) => group.value > 0)
          .map((group) => {
            const name = matrix.groups[group.index] ?? "";
            const position = labelPosition(group);
            return (
              <g
                key={name}
                data-testid="group-arc"
                data-group={name}
                tabIndex={0}
                aria-label={isOutside(group.index) ? outsideName : `Group ${name}`}
                className="cursor-default outline-none"
                onMouseEnter={() => setFocus({ kind: "group", index: group.index })}
                onFocus={() => setFocus({ kind: "group", index: group.index })}
                onMouseLeave={clear}
                onBlur={clear}
              >
                <path
                  d={arcPath(group) ?? undefined}
                  fill={isOutside(group.index) ? `url(#${hatchId})` : color(group.index)}
                  stroke="hsl(var(--background))"
                />
                {group.endAngle - group.startAngle >= MIN_LABEL_ANGLE && (
                  <text
                    x={position.x}
                    y={position.y}
                    dy="0.35em"
                    textAnchor={position.anchor}
                    className="pointer-events-none fill-foreground text-[11px] font-semibold"
                  >
                    {shortName(name)}
                  </text>
                )}
              </g>
            );
          })}
      </svg>
      <p role="status" className="min-h-10 text-center text-xs text-muted-foreground">
        <FocusText focus={focus} matrix={matrix} summaries={summaries} outsideName={outsideName} />
      </p>
    </div>
  );
}
