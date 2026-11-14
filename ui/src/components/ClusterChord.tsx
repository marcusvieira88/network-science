import { type Chord, type ChordGroup, type ChordSubgroup, chord, ribbon } from "d3-chord";
import { arc } from "d3-shape";
import { useMemo, useState } from "react";

import type { ClusterMatrix, GroupSummary } from "@/lib/clusters";
import { formatNumber, formatShare } from "@/lib/format";
import { groupColor } from "@/lib/network";

const SIZE = 440;
const OUTER_RADIUS = 180;
const ARC_WIDTH = 14;
const INNER_RADIUS = OUTER_RADIUS - ARC_WIDTH;
const LABEL_OFFSET = 12;
const PAD_ANGLE = 0.04;
/** Arcs narrower than this (radians) are left unlabelled; they are still in the table. */
const MIN_LABEL_ANGLE = 0.12;
const RIBBON_OPACITY = { rest: 0.65, highlighted: 0.9, dimmed: 0.08 } as const;

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

function FocusText({ focus, matrix, summaries }: { focus: Focus; matrix: ClusterMatrix; summaries: GroupSummary[] }) {
  if (focus === null) return <>Hover or focus a group arc or a ribbon for its numbers.</>;
  if (focus.kind === "group") {
    const summary = summaries[focus.index];
    if (!summary) return null;
    return (
      <>
        <span className="font-semibold text-foreground">Group {summary.group}</span> · {summary.nPersons} people ·
        total weight {formatNumber(summary.total)} · {formatShare(summary.withinShare)} stays within the group
      </>
    );
  }
  const a = matrix.groups[focus.source] ?? "";
  const b = matrix.groups[focus.target] ?? "";
  const ab = matrix.directed[focus.source]?.[focus.target] ?? 0;
  const ba = matrix.directed[focus.target]?.[focus.source] ?? 0;
  if (focus.source === focus.target) {
    return (
      <>
        <span className="font-semibold text-foreground">Within group {a}</span> · weight {formatNumber(ab)}
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
}

/** Chord diagram of group-to-group weight: arcs are groups, ribbons both directions summed. */
export function ClusterChord({ matrix, summaries, label }: ClusterChordProps) {
  const [focus, setFocus] = useState<Focus>(null);
  const chords = useMemo(() => layout(matrix.symmetric), [matrix]);
  const color = (index: number) => groupColor(matrix.groups[index] ?? "", matrix.groups);
  const clear = () => setFocus(null);

  return (
    <div className="space-y-2">
      <svg
        viewBox={`${-SIZE / 2} ${-SIZE / 2} ${SIZE} ${SIZE}`}
        className="mx-auto h-auto w-full max-w-[460px]"
        role="img"
        aria-label={label}
      >
        <g>
          {chords.map((link) => {
            const source = link.source.index;
            const target = link.target.index;
            const names = `${matrix.groups[source] ?? ""} and ${matrix.groups[target] ?? ""}`;
            return (
              <path
                key={`${source}-${target}`}
                data-testid="ribbon"
                d={ribbonPath(link) ?? undefined}
                fill={color(source)}
                fillOpacity={ribbonOpacity(focus, link)}
                stroke="hsl(var(--background))"
                strokeWidth={0.5}
                tabIndex={0}
                aria-label={source === target ? `Within ${matrix.groups[source] ?? ""}` : `Between ${names}`}
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
                aria-label={`Group ${name}`}
                className="cursor-default outline-none"
                onMouseEnter={() => setFocus({ kind: "group", index: group.index })}
                onFocus={() => setFocus({ kind: "group", index: group.index })}
                onMouseLeave={clear}
                onBlur={clear}
              >
                <path d={arcPath(group) ?? undefined} fill={color(group.index)} stroke="hsl(var(--background))" />
                {group.endAngle - group.startAngle >= MIN_LABEL_ANGLE && (
                  <text
                    x={position.x}
                    y={position.y}
                    dy="0.35em"
                    textAnchor={position.anchor}
                    className="pointer-events-none fill-foreground text-[11px] font-semibold"
                  >
                    {name}
                  </text>
                )}
              </g>
            );
          })}
      </svg>
      <p role="status" className="min-h-10 text-center text-xs text-muted-foreground">
        <FocusText focus={focus} matrix={matrix} summaries={summaries} />
      </p>
    </div>
  );
}
