import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { ArtifactChecksTable } from "@/components/ArtifactChecksTable";
import { CommunityGraph } from "@/components/CommunityGraph";
import { ExploratoryTable } from "@/components/ExploratoryTable";
import { HypothesesTable } from "@/components/HypothesesTable";
import { Limits } from "@/components/Limits";
import { MetricChart } from "@/components/MetricChart";
import { Overview } from "@/components/Overview";
import { QualityPanel } from "@/components/QualityPanel";
import { RiskPanel } from "@/components/RiskPanel";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { type LoadResult, type ReleaseData, loadRelease } from "@/lib/data";
import { minimumGroupSize } from "@/lib/privacy";
import { analysisWeeks, baselinePeriod, headline } from "@/lib/series";
import type { ViewId } from "@/lib/views";

export function View({ view, data }: { view: ViewId; data: ReleaseData }) {
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
        />
      );
    case "hypotheses":
      return (
        <div className="space-y-6">
          <Card>
            <CardContent className="pt-6">
              <HypothesesTable hypotheses={tables.hypotheses} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Checks against known artifacts</CardTitle>
              <CardDescription>
                Added after the first real-data run. A supported hypothesis whose check fails or cannot run is capped
                at low confidence and is not claimed as a finding.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ArtifactChecksTable checks={tables.artifact_checks} />
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <ExploratoryTable rows={tables.exploratory} />
            </CardContent>
          </Card>
        </div>
      );
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
      <View view={view} data={result.data} />
    </AppShell>
  );
}
