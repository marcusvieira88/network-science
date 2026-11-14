import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { DataQualityRow, DegreeRow, HeaderFieldRow } from "@/lib/data";
import { formatNumber, formatShare } from "@/lib/format";

const RULING_VARIANT: Record<string, "default" | "secondary" | "outline"> = {
  usable: "default",
  identifier: "secondary",
};

interface QualityPanelProps {
  steps: DataQualityRow[];
  headerFields: HeaderFieldRow[];
  degrees: DegreeRow[];
}

function FunnelStep({ step }: { step: DataQualityRow }) {
  const kept = step.count_in > 0 ? step.count_out / step.count_in : 0;
  return (
    <li className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-4 text-sm">
        <span className="font-medium">
          {step.order}. {step.step}
          {step.rule && <span className="ml-2 font-mono text-xs text-muted-foreground">{step.rule}</span>}
        </span>
        <span className="font-mono tabular-nums text-muted-foreground">
          {step.count_in.toLocaleString("en-US")} → {step.count_out.toLocaleString("en-US")}
          <span className="ml-2">(−{step.removed.toLocaleString("en-US")})</span>
        </span>
      </div>
      <div
        className="h-2 overflow-hidden rounded-full bg-muted"
        role="meter"
        aria-label={`${step.step}: share kept`}
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={kept}
      >
        <div className="h-full rounded-full bg-primary" style={{ width: `${kept * 100}%` }} />
      </div>
      {(step.precision !== null || step.recall !== null) && (
        <div className="text-xs text-muted-foreground">
          Precision {formatShare(step.precision)} · recall {formatShare(step.recall)} (measured on a labelled or
          synthetic set)
        </div>
      )}
    </li>
  );
}

export function QualityPanel({ steps, headerFields, degrees }: QualityPanelProps) {
  const periods = [...new Set(degrees.map((row) => row.period))];
  // Buckets are labels such as "1", "2-4", "10+"; order them by their lower bound.
  const buckets = [...new Set(degrees.map((row) => row.degree_bucket))].sort(
    (a, b) => Number.parseInt(a, 10) - Number.parseInt(b, 10) || a.localeCompare(b),
  );
  const persons = new Map(degrees.map((row) => [`${row.period}|${row.degree_bucket}`, row.persons]));
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Cleaning funnel</CardTitle>
          <CardDescription>Counts in and out of each step; the bar shows the share kept.</CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="space-y-5">
            {steps.map((step) => (
              <FunnelStep key={step.order} step={step} />
            ))}
          </ol>
        </CardContent>
      </Card>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Header ruling</CardTitle>
            <CardDescription>
              Every header field seen, and what the parser does with it. Content fields are dropped unread.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Field</TableHead>
                  <TableHead className="text-right">Occurrences</TableHead>
                  <TableHead>Ruling</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {headerFields.map((row) => (
                  <TableRow key={row.field}>
                    <TableCell className="font-mono">{row.field}</TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {row.occurrences.toLocaleString("en-US")}
                    </TableCell>
                    <TableCell>
                      <Badge variant={RULING_VARIANT[row.ruling] ?? "outline"}>{row.ruling}</Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Degree distribution</CardTitle>
            <CardDescription>People per degree bucket and half-year; cells under the minimum group size are suppressed.</CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Degree</TableHead>
                  {periods.map((period) => (
                    <TableHead key={period} className="text-right">
                      {period}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {buckets.map((bucket) => (
                  <TableRow key={bucket}>
                    <TableCell className="font-mono">{bucket}</TableCell>
                    {periods.map((period) => {
                      const count = persons.get(`${period}|${bucket}`);
                      return (
                        <TableCell key={period} className="text-right font-mono tabular-nums text-muted-foreground">
                          {count === undefined ? "–" : formatNumber(count)}
                        </TableCell>
                      );
                    })}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
