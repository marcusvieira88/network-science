import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ATTACKERS, type RiskRow } from "@/lib/data";
import { formatNumber, formatShare } from "@/lib/format";
import { ATTACKER_LABELS, VARIANT_LABELS, reidByVariant } from "@/lib/risk";

const config: ChartConfig = {
  A1: { label: ATTACKER_LABELS.A1, color: "var(--chart-1)" },
  A2: { label: ATTACKER_LABELS.A2, color: "var(--chart-2)" },
};

export function RiskPanel({ rows }: { rows: RiskRow[] }) {
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Re-identification rate by release</CardTitle>
          <CardDescription>
            Share of people an attacker re-identifies correctly (top-1) from each release. R0 is the naive
            pseudonymised output, kept in the restricted zone; R1 is what is published.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ChartContainer config={config} className="aspect-auto h-[280px] w-full">
            <BarChart data={reidByVariant(rows)} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barGap={2}>
              <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
              <XAxis dataKey="variant" tickLine={false} axisLine={false} tickMargin={8} />
              <YAxis
                domain={[0, 1]}
                tickLine={false}
                axisLine={false}
                width={48}
                tickFormatter={(v: number) => formatShare(v)}
              />
              <ChartTooltip content={<ChartTooltipContent formatValue={formatShare} />} />
              <ChartLegend content={<ChartLegendContent />} />
              {ATTACKERS.map((attacker) => (
                <Bar
                  key={attacker}
                  dataKey={attacker}
                  fill={`var(--color-${attacker})`}
                  radius={[4, 4, 0, 0]}
                  maxBarSize={48}
                  isAnimationActive={false}
                />
              ))}
            </BarChart>
          </ChartContainer>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Risk and analytical cost side by side</CardTitle>
          <CardDescription>
            Utility is the headline effect under the release divided by the effect on restricted data.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Release</TableHead>
                <TableHead>Attacker</TableHead>
                <TableHead className="text-right">Targets</TableHead>
                <TableHead className="text-right">Unique share</TableHead>
                <TableHead className="text-right">Median anonymity set</TableHead>
                <TableHead className="text-right">Re-identified</TableHead>
                <TableHead>95% interval</TableHead>
                <TableHead className="text-right">Utility</TableHead>
                <TableHead>Finding survives</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={`${row.release_variant}-${row.attacker}`}>
                  <TableCell>{VARIANT_LABELS[row.release_variant]}</TableCell>
                  <TableCell>{ATTACKER_LABELS[row.attacker]}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">{row.n_targets}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">{formatShare(row.unique_share)}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {formatNumber(row.median_anonymity_set)}
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums">{formatShare(row.reid_top1)}</TableCell>
                  <TableCell className="font-mono tabular-nums">
                    [{formatShare(row.reid_ci_low)}, {formatShare(row.reid_ci_high)}]
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {formatNumber(row.utility_effect_ratio)}
                  </TableCell>
                  <TableCell>{row.finding_survives === null ? "n/a" : row.finding_survives ? "yes" : "no"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
