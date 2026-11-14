import { useMemo, useState } from "react";

import { ClusterChord } from "@/components/ClusterChord";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  type ClusterPeriods,
  PERIOD_OPTIONS,
  type PeriodId,
  type ShareChange,
  clusterMatrix,
  groupSummaries,
  largestCrossShareChange,
  periodRange,
  periodWeeks,
} from "@/lib/clusters";
import type { CommunityEdgeRow, CommunityGroupRow } from "@/lib/data";
import { formatNumber, formatShare } from "@/lib/format";
import { groupColor } from "@/lib/network";

const DEFAULT_PERIOD: PeriodId = "all";
const PERCENT = 100;
const POINT_DECIMALS = 1;

interface ClusterViewProps {
  groups: CommunityGroupRow[];
  edges: CommunityEdgeRow[];
  periods: ClusterPeriods;
  minGroupSize: number;
  /** The H2 baseline placebo result in this release; null when it could not run. */
  driftCheck: boolean | null;
  onShowHypotheses: () => void;
}

const DRIFT_RESULT = {
  failed: "The H2 artifact check (baseline placebo) found this drift large enough to explain H2, and the same caveat applies here",
  passed:
    "In this release the H2 artifact check (baseline placebo) did not find drift that large, but the caveat still applies to any comparison with the baseline year",
  unknown: "The H2 artifact check (baseline placebo) did not run in this release, so the size of this drift is not known",
} as const;

function driftText(passes: boolean | null): string {
  if (passes === null) return DRIFT_RESULT.unknown;
  return passes ? DRIFT_RESULT.passed : DRIFT_RESULT.failed;
}

function isPeriodId(value: string): value is PeriodId {
  return PERIOD_OPTIONS.some((option) => option.id === value);
}

function periodLabel(id: PeriodId): string {
  return PERIOD_OPTIONS.find((option) => option.id === id)?.label ?? id;
}

function pointChange(change: number): string {
  const points = formatNumber(Math.abs(change) * PERCENT, POINT_DECIMALS);
  return `${change >= 0 ? "+" : "−"}${points} percentage points`;
}

interface WhatChangedProps {
  change: ShareChange | null;
  driftCheck: boolean | null;
  onShowHypotheses: () => void;
}

function WhatChanged({ change, driftCheck, onShowHypotheses }: WhatChangedProps) {
  return (
    <p className="text-sm text-muted-foreground" data-testid="what-changed">
      <span className="font-medium text-foreground">What changed. </span>
      {change === null ? (
        "No group has published ties in both the baseline year and the crisis weeks, so there is nothing to compare. "
      ) : (
        <>
          From the baseline year to the crisis weeks, the cross-group share of group{" "}
          <span className="text-foreground">{change.group}</span> changed most: from {formatShare(change.before)} to{" "}
          {formatShare(change.after)} ({pointChange(change.change)}). This describes the published ties; it does not
          say why they changed.{" "}
        </>
      )}
      The groups were fixed on the baseline year, and a grouping fits the period it was fitted on best, so cross-group
      share tends to rise afterwards whatever happens. {driftText(driftCheck)}; see the{" "}
      <button
        type="button"
        onClick={onShowHypotheses}
        className="text-primary underline underline-offset-2 hover:text-primary/80 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      >
        Hypotheses view
      </button>
      .
    </p>
  );
}

export function ClusterView({ groups, edges, periods, minGroupSize, driftCheck, onShowHypotheses }: ClusterViewProps) {
  const [period, setPeriod] = useState<PeriodId>(DEFAULT_PERIOD);
  const range = periodRange(period, periods);
  const matrix = useMemo(() => clusterMatrix(groups, edges, range), [groups, edges, range]);
  const summaries = useMemo(() => groupSummaries(matrix), [matrix]);
  const weeks = useMemo(() => periodWeeks(edges, range), [edges, range]);
  const change = useMemo(
    () =>
      largestCrossShareChange(
        groupSummaries(clusterMatrix(groups, edges, periods.baseline)),
        groupSummaries(clusterMatrix(groups, edges, periods.crisis)),
      ),
    [groups, edges, periods],
  );
  const hasWeight = summaries.some((summary) => summary.total > 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle>How the groups interconnect</CardTitle>
        <CardDescription>
          Each segment is a group of at least {minGroupSize} people, never an individual. Group membership is not
          published, and ties with fewer than {minGroupSize} distinct senders are suppressed before release.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <Tabs value={period} onValueChange={(value) => isPeriodId(value) && setPeriod(value)}>
            <TabsList aria-label="Period">
              {PERIOD_OPTIONS.map((option) => (
                <TabsTrigger key={option.id} value={option.id}>
                  {option.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <p className="text-xs text-muted-foreground" data-testid="period-weeks">
            {range === null ? "Every week" : `${range.start} to ${range.end}, weeks overlapping it`} ·{" "}
            {weeks.length} {weeks.length === 1 ? "week" : "weeks"} with published ties
          </p>
        </div>
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div>
            {hasWeight ? (
              <ClusterChord
                matrix={matrix}
                summaries={summaries}
                label={`Message weight between groups, ${periodLabel(period).toLowerCase()}`}
              />
            ) : (
              <p className="flex h-64 items-center justify-center rounded-lg border text-sm text-muted-foreground">
                No published tie between groups in this period.
              </p>
            )}
            <p className="mt-2 text-xs text-muted-foreground">
              Arc length is a group's total weight in the period (within the group, sent and received). A ribbon is the
              weight between two groups, both directions summed; a ribbon that returns to its own arc is weight within
              the group.
            </p>
          </div>
          <div>
            <h3 className="mb-2 text-sm font-medium">Groups in this period</h3>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Group</TableHead>
                  <TableHead className="text-right">People</TableHead>
                  <TableHead className="text-right">Within group</TableHead>
                  <TableHead>Top partner groups</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {summaries.map((summary) => (
                  <TableRow key={summary.group}>
                    <TableCell className="whitespace-nowrap">
                      <span className="flex items-center gap-2">
                        <span
                          className="h-2.5 w-2.5 rounded-full"
                          style={{ background: groupColor(summary.group, matrix.groups) }}
                          aria-hidden
                        />
                        {summary.group}
                      </span>
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums" data-testid="group-size">
                      {summary.nPersons}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {formatShare(summary.withinShare)}
                    </TableCell>
                    <TableCell className="text-xs">
                      {summary.partners.length === 0
                        ? "—"
                        : summary.partners.map((p) => `${p.group} (${formatNumber(p.weight)})`).join(", ")}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
        <WhatChanged change={change} driftCheck={driftCheck} onShowHypotheses={onShowHypotheses} />
      </CardContent>
    </Card>
  );
}
