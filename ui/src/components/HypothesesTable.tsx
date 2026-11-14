import { Fragment } from "react";

import { ConfidenceBadge } from "@/components/FindingCard";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ArtifactCheckRow, ExploratoryRow, HypothesisRow } from "@/lib/data";
import { type Departure, isSignificant, pText, periodRow, ruledVariants, shareText } from "@/lib/departures";
import { formatFloat, formatInterval, formatNumber, formatP, metricLabel } from "@/lib/format";
import { type HypothesisEntry, STATED, equalisedEstimate, formatEstimate, retentionCheck } from "@/lib/hypotheses";
import { cn } from "@/lib/utils";

const SUPPORT_VARIANT = { yes: "default", no: "outline", inconclusive: "secondary" } as const;
const OUTCOME_VARIANT = { confident: "default", inconclusive: "secondary", "not supported": "outline" } as const;
const DEPARTURE_OUTCOME_VARIANT = { high: "default", moderate: "default", low: "secondary", "not established": "outline" } as const;
const DIRECTION_ARROW = { up: "↑", down: "↓" } as const;
const COLUMN_COUNT = 8;

export const HELD_TRUE = "Held true";
/** Shown where a comparison covers fewer than k custodians and the release suppresses it. */
const SUPPRESSED = "suppressed";
/** H1–H4 state their direction in docs/hypotheses.md; the release tables do not carry it. */
const DIRECTION_NOT_PUBLISHED = "not in the release data; see docs/hypotheses.md";

function flag(value: boolean | null, yes: string, no: string): string {
  return value === null ? SUPPRESSED : value ? yes : no;
}

function checkResult(passes: boolean | null): string {
  return passes === null ? "not run" : passes ? "passes" : "fails";
}

function Muted({ children }: { children: React.ReactNode }) {
  return <div className="mt-1 text-xs text-muted-foreground">{children}</div>;
}

function PreregisteredCells({ row }: { row: HypothesisRow }) {
  return (
    <>
      <TableCell className="max-w-xs">
        <div>
          {metricLabel(row.metric)}, {row.scope} network
        </div>
        <Muted>change week {row.change_week ?? "none"}</Muted>
      </TableCell>
      <TableCell>
        <span title={DIRECTION_NOT_PUBLISHED}>—</span>
      </TableCell>
      <TableCell className="font-mono tabular-nums">
        <div>{formatEstimate(row.effect, row.ci_low, row.ci_high)}</div>
        <Muted>standardised effect</Muted>
      </TableCell>
      <TableCell className="text-right font-mono tabular-nums">{formatP(row.p_holm)}</TableCell>
      <TableCell className="text-sm">
        <div>
          leave-one-out {formatFloat(row.loo_min_effect)} to {formatFloat(row.loo_max_effect)}
        </div>
        <div>null model z {formatFloat(row.null_z)}</div>
        <div>
          variants {row.robust_variants_passed}/{row.robust_variants_total}
        </div>
      </TableCell>
      <TableCell>
        <div className="flex flex-wrap gap-1">
          <Badge variant={SUPPORT_VARIANT[row.supported]}>supported: {row.supported}</Badge>
          <ConfidenceBadge confidence={row.confidence} />
        </div>
      </TableCell>
    </>
  );
}

function ExploratoryCells({ row, heldTrue }: { row: ExploratoryRow; heldTrue: boolean }) {
  const equalised = equalisedEstimate(row);
  const retention = retentionCheck(row);
  return (
    <>
      <TableCell className="max-w-xs">
        <div>{row.measure}</div>
        <Muted>{row.custodians === null ? `custodians ${SUPPRESSED}` : `${formatNumber(row.custodians)} custodians`}</Muted>
        {equalised !== null && (
          <div className={cn("mt-1 font-mono text-xs tabular-nums", heldTrue ? "text-primary" : "text-muted-foreground")}>
            volume-equalised: {equalised}
          </div>
        )}
        {retention !== null && (
          <div className="mt-1 font-mono text-xs tabular-nums text-muted-foreground">
            retention check (custodian contacts only): {retention}
          </div>
        )}
        {row.caveat !== "" && <Muted>{row.caveat}</Muted>}
      </TableCell>
      <TableCell>
        <span aria-hidden>{DIRECTION_ARROW[row.direction]} </span>
        <span>{row.direction}</span>
      </TableCell>
      <TableCell className="font-mono tabular-nums">
        <div>{formatEstimate(row.median_change, row.ci_low, row.ci_high)}</div>
        <Muted>median change</Muted>
      </TableCell>
      <TableCell className="text-right font-mono tabular-nums">{formatP(row.p_holm)}</TableCell>
      <TableCell className="text-sm">
        <div>placebo {flag(row.placebo_passes, "passes", "fails")}</div>
        <Muted>{formatEstimate(row.placebo_median, row.placebo_ci_low, row.placebo_ci_high)}</Muted>
        <div>leave-one-out {flag(row.loo_stable, "stable", "unstable")}</div>
      </TableCell>
      <TableCell>
        {row.outcome === null ? (
          <span className="text-muted-foreground">{SUPPRESSED}</span>
        ) : (
          <Badge variant={OUTCOME_VARIANT[row.outcome]} className="whitespace-nowrap">
            {row.outcome}
          </Badge>
        )}
      </TableCell>
    </>
  );
}

/** H26: departures of the custodians at risk, crisis against the same weeks a year earlier. */
function DepartureCells({ departure }: { departure: Departure }) {
  const { primary, settings } = departure;
  const ruled = ruledVariants(departure);
  const significant = ruled.filter((row) => isSignificant(row.p_band)).length;
  return (
    <>
      <TableCell className="max-w-xs">
        <div>custodians who stopped sending while their mailbox kept receiving mail (departures)</div>
        <Muted>post hoc; one-sided Fisher exact test, no Holm correction</Muted>
      </TableCell>
      <TableCell>
        <span aria-hidden>{DIRECTION_ARROW.up} </span>
        <span>up</span>
      </TableCell>
      <TableCell className="text-sm">
        <div>crisis {shareText(periodRow(departure, "crisis"), settings.k)}</div>
        <Muted>a year earlier {shareText(periodRow(departure, "reference"), settings.k)}</Muted>
      </TableCell>
      <TableCell className="text-right text-sm">{pText(primary.p, primary.p_band, settings)}</TableCell>
      <TableCell className="text-sm">
        <div>placebo {pText(primary.placebo_p, primary.placebo_p_band, settings)}</div>
        <div>above every earlier window {flag(primary.above_rolling, "yes", "no")}</div>
        <div>
          variants significant {significant}/{ruled.length}
        </div>
      </TableCell>
      <TableCell>
        {primary.outcome === null ? (
          <span className="text-muted-foreground">{SUPPRESSED}</span>
        ) : (
          <Badge variant={DEPARTURE_OUTCOME_VARIANT[primary.outcome]} className="whitespace-nowrap">
            {primary.outcome}
          </Badge>
        )}
      </TableCell>
    </>
  );
}

/** The artifact check of a hypothesis stated before any data, as a detail line under its row. */
function CheckDetail({ check, heldTrue }: { check: ArtifactCheckRow; heldTrue: boolean }) {
  return (
    <TableRow data-testid="artifact-check" className={cn("border-t-0", heldTrue && "bg-primary/10")}>
      <TableCell />
      <TableCell colSpan={COLUMN_COUNT - 1} className="pt-0 text-xs text-muted-foreground">
        Artifact check ({check.check.replaceAll("_", " ")}): statistic {formatFloat(check.statistic)}, 95% interval{" "}
        {formatInterval(check.ci_low, check.ci_high)}, {formatNumber(check.n_units)} units —{" "}
        <span className="font-medium text-foreground">{checkResult(check.passes)}</span>. {check.note}
      </TableCell>
    </TableRow>
  );
}

function EntryRow({ entry }: { entry: HypothesisEntry }) {
  const { heldTrue } = entry;
  return (
    <TableRow data-held-true={heldTrue} className={cn(heldTrue && "bg-primary/10 hover:bg-primary/15")}>
      <TableCell className={cn("font-medium", heldTrue && "text-primary")}>
        <span>{entry.id}</span>
        {heldTrue && <Badge className="ml-2 whitespace-nowrap px-1.5 py-0 text-[10px]">{HELD_TRUE}</Badge>}
      </TableCell>
      {entry.kind === "preregistered" && <PreregisteredCells row={entry.row} />}
      {entry.kind === "exploratory" && <ExploratoryCells row={entry.row} heldTrue={heldTrue} />}
      {entry.kind === "departure" && <DepartureCells departure={entry.departure} />}
      <TableCell className="whitespace-nowrap text-sm text-muted-foreground">{STATED[entry.kind]}</TableCell>
    </TableRow>
  );
}

export function HypothesesTable({ entries }: { entries: HypothesisEntry[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Hypothesis</TableHead>
          <TableHead>Claim / measure</TableHead>
          <TableHead>Predicted</TableHead>
          <TableHead>Effect or median change (95% interval)</TableHead>
          <TableHead className="text-right">p (Holm)</TableHead>
          <TableHead>Robustness</TableHead>
          <TableHead>Outcome</TableHead>
          <TableHead>Stated</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {entries.map((entry) => (
          <Fragment key={`${entry.kind}-${entry.id}`}>
            <EntryRow entry={entry} />
            {entry.kind === "preregistered" &&
              entry.checks.map((check) => <CheckDetail key={check.check} check={check} heldTrue={entry.heldTrue} />)}
          </Fragment>
        ))}
      </TableBody>
    </Table>
  );
}
