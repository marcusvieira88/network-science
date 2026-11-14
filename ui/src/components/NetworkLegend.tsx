/** The WebGL network's legend: circle area, line width and, per mode, what a dot or overlap means. */
import type { NetworkMode } from "@/lib/cells";
import type { CommunityGroupRow } from "@/lib/data";
import { formatNumber } from "@/lib/format";
import { OVERLAP_PAIRS } from "@/lib/overlap";
import { legendSizes, legendWeights } from "@/lib/sigmaNetwork";

const LEGEND_MAX_RADIUS = 10;
const LEGEND_MAX_WIDTH = 5;
const LEGEND_LINE_LENGTH = 24;

interface LegendProps {
  groups: CommunityGroupRow[];
  maxTie: number;
  mode: NetworkMode;
}

export function NetworkLegend({ groups, maxTie, mode }: LegendProps) {
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
      {mode === "individuals" && <div>Each small dot: one anonymous person (illustrative position)</div>}
      {mode === "overlap" && (
        <>
          <div>Overlap = mail between two groups, not shared members — each person is in exactly one group.</div>
          <div>The week&apos;s {OVERLAP_PAIRS} heaviest pairs overlap; depth: shared ÷ (own within-group + shared) messages.</div>
        </>
      )}
    </div>
  );
}

