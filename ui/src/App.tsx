import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { ClusterView } from "@/components/ClusterView";
import { CommunityGraph } from "@/components/CommunityGraph";
import { HypothesesTable } from "@/components/HypothesesTable";
import { Limits } from "@/components/Limits";
import { MetricChart } from "@/components/MetricChart";
import { Overview } from "@/components/Overview";
import { QualityPanel } from "@/components/QualityPanel";
import { RiskPanel } from "@/components/RiskPanel";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { driftCheckPasses } from "@/lib/clusters";
import { type LoadResult, type ReleaseData, loadRelease } from "@/lib/data";
import { STATED, allHypotheses, countByKind } from "@/lib/hypotheses";
import { minimumGroupSize } from "@/lib/privacy";
import { analysisWeeks, baselinePeriod, headline } from "@/lib/series";
import type { ViewId } from "@/lib/views";

interface ViewProps {
  view: ViewId;
  data: ReleaseData;
  onSelect: (view: ViewId) => void;
}

export function View({ view, data, onSelect }: ViewProps) {
  const { tables } = data;
  switch (view) {
    case "overview":
      return <Overview data={data} />;
    case "metrics": {
      const main = headline(tables.hypotheses);
      return (
        <MetricChart
          rows={tables.weekly_metrics}
          hypotheses={tables.hypotheses}
          events={data.events}
          baseline={baselinePeriod(data)}
          initialMetric={main?.metric}
          initialScope={main?.scope}
        />
      );
    }
    case "network":
      return (
        <CommunityGraph
          groups={tables.community_groups}
          edges={tables.community_graph}
          weeks={analysisWeeks(tables.weekly_metrics)}
          events={data.events}
          minGroupSize={minimumGroupSize(data)}
          seed={data.run.seed}
        />
      );
    case "clusters": {
      const baseline = baselinePeriod(data);
      if (baseline === null) {
        return (
          <p role="alert" className="text-sm text-destructive">
            The run parameters lack the baseline period, so the clusters cannot be compared over time.
          </p>
        );
      }
      return (
        <ClusterView
          groups={tables.community_groups}
          edges={tables.community_graph}
          periods={{ baseline, crisis: data.windows.crisis }}
          minGroupSize={minimumGroupSize(data)}
          driftCheck={driftCheckPasses(tables.artifact_checks)}
          onShowHypotheses={() => onSelect("hypotheses")}
        />
      );
    }
    case "hypotheses": {
      const entries = allHypotheses(tables.hypotheses, tables.exploratory, tables.artifact_checks);
      const counts = countByKind(entries);
      return (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Hypotheses</CardTitle>
            <CardDescription className="space-y-2">
              <span className="block">
                One list, ordered by number. {counts.preregistered} were stated {STATED.preregistered} and{" "}
                {counts.exploratory} {STATED.exploratory}; Holm&apos;s correction runs within each of those two sets.
                Each hypothesis stated {STATED.exploratory} compares every custodian with themselves, crisis window
                against the same weeks a year earlier.
              </span>
              <span className="block">
                &ldquo;Held true&rdquo; marks what the analysis holds to be true: the headline among the hypotheses
                stated {STATED.preregistered}, or a confident outcome among those stated {STATED.exploratory}. A
                hypothesis stated {STATED.preregistered} carries its check against a known artifact of the data under
                its row; a supported one whose check fails or cannot run is capped at low confidence and is not
                claimed as a finding.
              </span>
            </CardDescription>
          </CardHeader>
          <CardContent>
            <HypothesesTable entries={entries} />
          </CardContent>
        </Card>
      );
    }
    case "quality":
      return (
        <QualityPanel
          steps={tables.data_quality}
          headerFields={tables.header_fields}
          degrees={tables.degree_distribution}
        />
      );
    case "risk":
      return <RiskPanel rows={tables.risk} />;
    case "limits":
      return <Limits sample={data.run.sample} />;
  }
}

export function App({ load = loadRelease }: { load?: () => Promise<LoadResult> }) {
  const [result, setResult] = useState<LoadResult | null>(null);
  const [view, setView] = useState<ViewId>("overview");

  useEffect(() => {
    let live = true;
    void load().then((loaded) => {
      if (live) setResult(loaded);
    });
    return () => {
      live = false;
    };
  }, [load]);

  if (result === null) {
    return <p className="p-8 text-sm text-muted-foreground">Loading release data…</p>;
  }
  if (result.status === "error") {
    return (
      <div role="alert" className="mx-auto mt-24 max-w-lg rounded-xl border border-destructive/40 p-6">
        <h1 className="font-semibold">The release data could not be loaded</h1>
        <p className="mt-2 text-sm text-muted-foreground">{result.message}</p>
      </div>
    );
  }
  return (
    <AppShell
      active={view}
      onSelect={setView}
      run={result.data.run}
      contractVersion={result.data.contract_version}
      source={result.source}
    >
      <View view={view} data={result.data} onSelect={setView} />
    </AppShell>
  );
}
