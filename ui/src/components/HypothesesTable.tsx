import { ConfidenceBadge } from "@/components/FindingCard";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { HypothesisRow } from "@/lib/data";
import { formatFloat, formatInterval, formatP, metricLabel } from "@/lib/format";

const SUPPORT_VARIANT = { yes: "default", no: "outline", inconclusive: "secondary" } as const;

export function HypothesesTable({ hypotheses }: { hypotheses: HypothesisRow[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Hypothesis</TableHead>
          <TableHead>Metric</TableHead>
          <TableHead>Scope</TableHead>
          <TableHead>Change week</TableHead>
          <TableHead className="text-right">p</TableHead>
          <TableHead className="text-right">p (Holm)</TableHead>
          <TableHead className="text-right">Effect</TableHead>
          <TableHead>95% interval</TableHead>
          <TableHead className="text-right">Robustness</TableHead>
          <TableHead>Supported</TableHead>
          <TableHead>Confidence</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {hypotheses.map((row) => (
          <TableRow key={row.hypothesis}>
            <TableCell className="font-medium">
              {row.hypothesis}
              {row.is_headline && <span className="ml-2 text-xs text-primary">headline</span>}
            </TableCell>
            <TableCell>{metricLabel(row.metric)}</TableCell>
            <TableCell>{row.scope}</TableCell>
            <TableCell className="font-mono">{row.change_week ?? "none"}</TableCell>
            <TableCell className="text-right font-mono tabular-nums">{formatP(row.p_perm)}</TableCell>
            <TableCell className="text-right font-mono tabular-nums">{formatP(row.p_holm)}</TableCell>
            <TableCell className="text-right font-mono tabular-nums">{formatFloat(row.effect)}</TableCell>
            <TableCell className="font-mono tabular-nums">{formatInterval(row.ci_low, row.ci_high)}</TableCell>
            <TableCell className="text-right font-mono tabular-nums">
              {row.robust_variants_passed}/{row.robust_variants_total}
            </TableCell>
            <TableCell>
              <Badge variant={SUPPORT_VARIANT[row.supported]}>{row.supported}</Badge>
            </TableCell>
            <TableCell>
              <ConfidenceBadge confidence={row.confidence} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
