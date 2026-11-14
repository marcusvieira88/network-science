import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ArtifactCheckRow } from "@/lib/data";
import { formatFloat, formatInterval, formatNumber } from "@/lib/format";

function result(passes: boolean | null): { label: string; variant: "default" | "outline" | "secondary" } {
  if (passes === null) return { label: "not run", variant: "secondary" };
  return passes ? { label: "passes", variant: "default" } : { label: "fails", variant: "outline" };
}

export function ArtifactChecksTable({ checks }: { checks: ArtifactCheckRow[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Hypothesis</TableHead>
          <TableHead>Check</TableHead>
          <TableHead className="text-right">Statistic</TableHead>
          <TableHead>95% interval</TableHead>
          <TableHead className="text-right">Units</TableHead>
          <TableHead>Result</TableHead>
          <TableHead>Reading</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {checks.map((row) => {
          const { label, variant } = result(row.passes);
          return (
            <TableRow key={row.hypothesis}>
              <TableCell className="font-medium">{row.hypothesis}</TableCell>
              <TableCell>{row.check.replaceAll("_", " ")}</TableCell>
              <TableCell className="text-right font-mono tabular-nums">{formatFloat(row.statistic)}</TableCell>
              <TableCell className="font-mono tabular-nums">{formatInterval(row.ci_low, row.ci_high)}</TableCell>
              <TableCell className="text-right font-mono tabular-nums">{formatNumber(row.n_units)}</TableCell>
              <TableCell>
                <Badge variant={variant}>{label}</Badge>
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">{row.note}</TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
