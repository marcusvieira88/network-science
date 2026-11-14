import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { type ChartConfig, ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { METRICS, type Period, type PublicEvent, SCOPES, type HypothesisRow, type Scope, type WeeklyMetricRow } from "@/lib/data";
import { formatNumber, metricLabel } from "@/lib/format";
import {
  DEFAULT_VARIANT,
  analysisWeeks,
  hypothesisFor,
  metricSeries,
  snapToWeek,
  variants,
} from "@/lib/series";

interface MetricChartProps {
  rows: WeeklyMetricRow[];
  hypotheses: HypothesisRow[];
  events: PublicEvent[];
  baseline: Period | null;
  initialMetric?: string;
  initialScope?: Scope;
}

const SCOPE_LABELS: Record<Scope, string> = { core: "Core (custodians)", observed: "Observed network" };

function isScope(value: string): value is Scope {
  return (SCOPES as readonly string[]).includes(value);
}

export function MetricChart({ rows, hypotheses, events, baseline, initialMetric, initialScope }: MetricChartProps) {
  const [metric, setMetric] = useState<string>(initialMetric ?? METRICS[0]);
  const [scope, setScope] = useState<Scope>(initialScope ?? "core");
  const variantOptions = useMemo(() => variants(rows), [rows]);
  const [variant, setVariant] = useState<string>(variantOptions[0] ?? DEFAULT_VARIANT);
  const weeks = useMemo(() => analysisWeeks(rows), [rows]);
  const series = useMemo(() => metricSeries(rows, { metric, scope, variant }), [rows, metric, scope, variant]);
  const tested = hypothesisFor(hypotheses, metric, scope);
  const changeWeek = tested?.change_week ? snapToWeek(weeks, tested.change_week) : null;
  const eventMarkers = events
    .map((event, index) => ({ ...event, number: index + 1, week: snapToWeek(weeks, event.date) }))
    .filter((event): event is PublicEvent & { number: number; week: string } => event.week !== null);
  const baselineStart = baseline ? snapToWeek(weeks, baseline.start) ?? weeks[0] : null;
  const baselineEnd = baseline ? snapToWeek(weeks, baseline.end) : null;
  const suppressed = series.filter((point) => point.value === null).length;
  const config: ChartConfig = { value: { label: metricLabel(metric), color: "var(--chart-1)" } };

  return (
    <Card>
      <CardHeader className="gap-4 space-y-0 md:flex-row md:items-start md:justify-between">
        <div className="space-y-1.5">
          <CardTitle>{metricLabel(metric)}</CardTitle>
          <CardDescription>
            Weekly value, {SCOPE_LABELS[scope].toLowerCase()}, variant <span className="font-mono">{variant}</span>.
            {suppressed > 0 && ` ${suppressed} weeks below the minimum group size are shown as gaps.`}
          </CardDescription>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select value={metric} onValueChange={setMetric}>
            <SelectTrigger className="w-60" aria-label="Metric">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {METRICS.map((name) => (
                <SelectItem key={name} value={name}>
                  {metricLabel(name)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Tabs value={scope} onValueChange={(value) => isScope(value) && setScope(value)}>
            <TabsList aria-label="Scope">
              {SCOPES.map((name) => (
                <TabsTrigger key={name} value={name}>
                  {name}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <Select value={variant} onValueChange={setVariant}>
            <SelectTrigger className="w-40" aria-label="Sensitivity variant">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {variantOptions.map((name) => (
                <SelectItem key={name} value={name}>
                  {name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent>
        <ChartContainer config={config} className="aspect-auto h-[340px] w-full">
          <LineChart data={series} margin={{ top: 16, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
            <XAxis dataKey="week" tickLine={false} axisLine={false} minTickGap={48} tickMargin={8} />
            <YAxis tickLine={false} axisLine={false} width={56} tickFormatter={(v: number) => formatNumber(v)} />
            {baselineStart && baselineEnd && (
              <ReferenceArea x1={baselineStart} x2={baselineEnd} fill="hsl(var(--muted-foreground))" fillOpacity={0.08} />
            )}
            {eventMarkers.map((event) => (
              <ReferenceLine
                key={event.date}
                x={event.week}
                stroke="var(--chart-marker)"
                strokeDasharray="2 4"
                label={{ value: String(event.number), position: "top", fill: "var(--chart-marker)", fontSize: 11 }}
              />
            ))}
            {changeWeek && (
              <ReferenceLine
                x={changeWeek}
                stroke="hsl(var(--primary))"
                strokeWidth={1.5}
                strokeDasharray="6 3"
                label={{ value: "change", position: "insideTopLeft", fill: "hsl(var(--primary))", fontSize: 11 }}
              />
            )}
            <ChartTooltip content={<ChartTooltipContent />} />
            <Line
              dataKey="value"
              type="linear"
              stroke="var(--color-value)"
              strokeWidth={2}
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ChartContainer>
        <ul aria-label="Chart markers" className="mt-4 grid gap-1.5 text-xs text-muted-foreground sm:grid-cols-2">
          {baseline && (
            <li className="flex items-center gap-2">
              <span className="h-3 w-5 rounded-sm bg-muted-foreground/15" aria-hidden />
              Baseline {baseline.start} to {baseline.end}
            </li>
          )}
          <li className="flex items-center gap-2">
            <span className="w-5 border-t-2 border-dashed border-primary" aria-hidden />
            {changeWeek
              ? `Estimated change point: week of ${changeWeek} (${tested?.hypothesis})`
              : tested
                ? `No change point estimated (${tested.hypothesis})`
                : "This metric is not a pre-registered hypothesis in this scope"}
          </li>
          {eventMarkers.map((event) => (
            <li key={event.date} className="flex items-center gap-2">
              <span className="w-5 text-center font-mono" aria-hidden>
                {event.number}
              </span>
              Public event {event.date}: {event.label}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
