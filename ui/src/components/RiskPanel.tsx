import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import { AnalystDetails } from "@/components/AnalystDetails";
import { ChartHeadline } from "@/components/ChartHeadline";
import { Explain } from "@/components/Explain";
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
import { formatFloat, formatShare } from "@/lib/format";
import { riskHeadline } from "@/lib/executive";
import { ATTACKER_LABELS, VARIANT_LABELS, reidByVariant } from "@/lib/risk";

const RISK_CAPTION =
  "Each group of bars is one release, each bar one simulated attacker; a taller bar means more people correctly identified. " +
  "R0 is person-level data under pseudonyms and was never published; R1 holds only group totals and is what is published; " +
  "R2 adds random noise to R1.";

const config: ChartConfig = {
  A1: { label: ATTACKER_LABELS.A1, color: "var(--chart-1)" },
  A2: { label: ATTACKER_LABELS.A2, color: "var(--chart-2)" },
  A3: { label: ATTACKER_LABELS.A3, color: "var(--chart-3)" },
};

export function RiskPanel({ rows }: { rows: RiskRow[] }) {
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Re-identification rate by release</CardTitle>
          <CardDescription>
            Share of people an attacker re-identifies correctly (top-1) from each release
            <Explain term="Re-identification" />. Releases
            <Explain term="Releases R0, R1, R2" /> and attackers
            <Explain term="Attackers A1, A2, A3" /> in plain words.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <ChartHeadline headline={riskHeadline(rows)} caption={RISK_CAPTION} />
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
      <AnalystDetails>
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
                <TableHead className="text-right">
                  Median anonymity set
                  <Explain term="Anonymity set and unique share" />
                </TableHead>
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
                    {formatFloat(row.median_anonymity_set)}
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums">{formatShare(row.reid_top1)}</TableCell>
                  <TableCell className="font-mono tabular-nums">
                    [{formatShare(row.reid_ci_low)}, {formatShare(row.reid_ci_high)}]
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {formatFloat(row.utility_effect_ratio)}
                  </TableCell>
                  <TableCell>{row.finding_survives === null ? "n/a" : row.finding_survives ? "yes" : "no"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      </AnalystDetails>
    </div>
  );
}
