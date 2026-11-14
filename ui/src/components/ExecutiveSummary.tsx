import { ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { ReleaseData } from "@/lib/data";
import { formatShare } from "@/lib/format";
import { allHypotheses } from "@/lib/hypotheses";
import { worstReid } from "@/lib/overview";
import { executiveSummary } from "@/lib/plainLanguage";
import { minimumGroupSize } from "@/lib/privacy";
import type { ViewId } from "@/lib/views";

/** The privacy result in one sentence, or null when the risk table lacks either release. */
function privacyLine(data: ReleaseData): string | null {
  const naive = worstReid(data, "R0");
  const published = worstReid(data, "R1");
  if (naive === null || published === null) return null;
  return (
    `Publishing groups of at least ${minimumGroupSize(data)} people instead of individuals cuts the strongest ` +
    `attacker's re-identification rate from ${formatShare(naive)} to ${formatShare(published)}.`
  );
}

/** The answer first, in plain words, for readers who will not read the tables. */
export function ExecutiveSummary({ data, onSelect }: { data: ReleaseData; onSelect?: (view: ViewId) => void }) {
  const { hypotheses, exploratory, artifact_checks: checks } = data.tables;
  const { answer, points } = executiveSummary(allHypotheses(hypotheses, exploratory, checks));
  const privacy = privacyLine(data);
  return (
    <Card className="border-primary/40">
      <CardHeader>
        <CardDescription>In short</CardDescription>
        <CardTitle className="text-2xl leading-snug">{answer}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
          {points.map((point) => (
            <li key={point}>{point}</li>
          ))}
          {privacy !== null && <li>{privacy}</li>}
        </ul>
        {onSelect && (
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => onSelect("hypotheses")}>
              Every hypothesis in plain words <ArrowRight className="ml-1 h-4 w-4" aria-hidden />
            </Button>
            <Button variant="outline" size="sm" onClick={() => onSelect("network")}>
              See how the groups talk, week by week <ArrowRight className="ml-1 h-4 w-4" aria-hidden />
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
