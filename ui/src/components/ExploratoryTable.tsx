import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ExploratoryRow } from "@/lib/data";
import { byOrder, equalisedEstimate, formatEstimate, hasEqualisedResult } from "@/lib/exploratory";
import { formatNumber, formatP } from "@/lib/format";
import { cn } from "@/lib/utils";

const OUTCOME_VARIANT = { confident: "default", inconclusive: "secondary", "not supported": "outline" } as const;
const DIRECTION_ARROW = { up: "↑", down: "↓" } as const;

export const EXPLORATORY_TITLE = "Exploratory hypotheses E1–E20 (stated before computing; Holm across all twenty)";

/** Shown where a comparison covers fewer than k custodians and the release suppresses it. */
const SUPPRESSED = "suppressed";

function flag(value: boolean | null, yes: string, no: string): string {
  return value === null ? SUPPRESSED : value ? yes : no;
}

function ExploratoryRowView({ row }: { row: ExploratoryRow }) {
  const confident = row.outcome === "confident";
  return (
    <TableRow data-confident={confident} className={cn(confident && "bg-primary/10 hover:bg-primary/15")}>
      <TableCell className={cn("font-medium", confident && "text-primary")}>
        <span>{row.hypothesis}</span>
        {row.family === "second" && (
          <Badge variant="outline" className="ml-2 px-1.5 py-0 text-[10px] font-normal text-muted-foreground">
            second family
          </Badge>
        )}
      </TableCell>
      <TableCell className="max-w-xs">
        <div>{row.measure}</div>
        {hasEqualisedResult(row) && (
          <div className={cn("mt-1 font-mono text-xs tabular-nums", confident ? "text-primary" : "text-muted-foreground")}>
            volume-equalised: {equalisedEstimate(row)}
          </div>
        )}
        {row.caveat !== "" && <div className="mt-1 text-xs text-muted-foreground">{row.caveat}</div>}
      </TableCell>
      <TableCell>
        <span aria-hidden>{DIRECTION_ARROW[row.direction]} </span>
        <span>{row.direction}</span>
      </TableCell>
      <TableCell className="text-right font-mono tabular-nums">{formatNumber(row.custodians)}</TableCell>
      <TableCell className="font-mono tabular-nums">{formatEstimate(row.median_change, row.ci_low, row.ci_high)}</TableCell>
      <TableCell className="text-right font-mono tabular-nums">{formatP(row.p_holm)}</TableCell>
      <TableCell>
        <div>{flag(row.placebo_passes, "passes", "fails")}</div>
        <div className="font-mono text-xs tabular-nums text-muted-foreground">
          {formatEstimate(row.placebo_median, row.placebo_ci_low, row.placebo_ci_high)}
        </div>
      </TableCell>
      <TableCell>{flag(row.loo_stable, "stable", "unstable")}</TableCell>
      <TableCell>
        {row.outcome === null ? (
          <span className="text-muted-foreground">{SUPPRESSED}</span>
        ) : (
          <Badge variant={OUTCOME_VARIANT[row.outcome]} className="whitespace-nowrap">
            {row.outcome}
          </Badge>
        )}
      </TableCell>
    </TableRow>
  );
}

export function ExploratoryTable({ rows }: { rows: ExploratoryRow[] }) {
  return (
    <div className="space-y-3">
      <h3 className="text-base font-semibold leading-none tracking-tight">{EXPLORATORY_TITLE}</h3>
      <p className="text-sm text-muted-foreground">
        This family is exploratory, not pre-registered: it was stated after H1–H4 gave no finding, before any of it was
        computed. Each measure compares every custodian with themselves, crisis window against the same weeks a year
        earlier. A confident result is a lead to confirm on other data, not a finding.
      </p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Hypothesis</TableHead>
            <TableHead>Measure</TableHead>
            <TableHead>Predicted</TableHead>
            <TableHead className="text-right">Custodians</TableHead>
            <TableHead>Median change (95% interval)</TableHead>
            <TableHead className="text-right">p (Holm)</TableHead>
            <TableHead>Placebo</TableHead>
            <TableHead>Leave one out</TableHead>
            <TableHead>Outcome</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {byOrder(rows).map((row) => (
            <ExploratoryRowView key={row.hypothesis} row={row} />
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
