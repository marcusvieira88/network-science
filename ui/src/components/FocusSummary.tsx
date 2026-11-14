/** The WebGL network's status line: what the focused (hovered or searched) group publishes. */
import { formatNumber } from "@/lib/format";
import { type Overlap, overlapsOf } from "@/lib/overlap";
import { type NetworkGraph, focusOn } from "@/lib/sigmaNetwork";

const PERCENT = 100;

function percent(share: number): string {
  return `${Math.round(share * PERCENT)}%`;
}

interface SummaryProps {
  graph: NetworkGraph;
  focusKey: string | null;
  people: ReadonlyMap<string, number>;
  /** The week's overlaps in the Overlap mode; null in the other modes. */
  overlaps: readonly Overlap[] | null;
}

/**
 * The focused group's published facts: label, size and how many groups it has a tie with; in the
 * Overlap mode also each overlap's message count and both sides' shares.
 */
export function FocusSummary({ graph, focusKey, people, overlaps }: SummaryProps) {
  const focus = focusOn(graph, focusKey);
  if (!focus) return null;
  const label = graph.getNodeAttribute(focus.key, "label") ?? "";
  return (
    <div role="status" className="absolute right-12 top-2 z-[101] rounded-md border bg-card px-2 py-1 text-xs">
      <p>
        Group {label} · {people.get(label)} people · tied to {focus.neighbours.size}{" "}
        {focus.neighbours.size === 1 ? "group" : "groups"} this week
      </p>
      {overlapsOf(overlaps ?? [], label).map((o) => (
        <p key={o.partner}>
          {o.group} ↔ {o.partner} · {formatNumber(o.messages)} messages · {percent(o.share)} of {o.group}&apos;s mail ·{" "}
          {percent(o.partnerShare)} of {o.partner}&apos;s mail
        </p>
      ))}
    </div>
  );
}
