import { ExecutiveSummary } from "@/components/ExecutiveSummary";
import { FindingCard } from "@/components/FindingCard";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { ReleaseData } from "@/lib/data";
import { heldTrueLines, releaseHypotheses } from "@/lib/hypotheses";
import { keyNumbers } from "@/lib/overview";
import type { ViewId } from "@/lib/views";

export function Overview({ data, onSelect }: { data: ReleaseData; onSelect?: (view: ViewId) => void }) {
  const { hypotheses, artifact_checks: checks } = data.tables;
  const leads = heldTrueLines(releaseHypotheses(data));
  return (
    <div className="space-y-6">
      <ExecutiveSummary data={data} onSelect={onSelect} />
      <div className="space-y-2">
        <FindingCard hypotheses={hypotheses} artifactChecks={checks} />
        {leads.map((lead) => (
          <p key={lead} className="px-1 text-sm text-primary">
            {lead}
          </p>
        ))}
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {keyNumbers(data).map((item) => (
          <Card key={item.label}>
            <CardHeader className="pb-2">
              <CardDescription>{item.label}</CardDescription>
              <CardTitle className="text-2xl tabular-nums">{item.value}</CardTitle>
            </CardHeader>
            <CardContent className="text-xs text-muted-foreground">{item.note}</CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
