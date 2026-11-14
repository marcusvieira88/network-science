import { ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { ReleaseData } from "@/lib/data";
import { formatShare } from "@/lib/format";
import { releaseHypotheses } from "@/lib/hypotheses";
import { worstReid } from "@/lib/overview";
import { executiveSummary } from "@/lib/plainLanguage";
import { minimumGroupSize } from "@/lib/privacy";
import { recordFinding } from "@/lib/record";
import { PERSON_LEVEL, PUBLISHED } from "@/lib/risk";
import type { ViewId } from "@/lib/views";

/**
 * The privacy result, or null when the risk table lacks either release. The published rate is 0
 * by construction (R1 has no person-level record to match) and no group-level attack was run
 * (docs/architecture.md), so the text says that rather than claiming a measured protection.
 */
function privacyLine(data: ReleaseData): string | null {
  const naive = worstReid(data, PERSON_LEVEL);
  const published = worstReid(data, PUBLISHED);
  if (naive === null || published === null) return null;
  const before = `On person-level pseudonymised data, which is never published, the strongest attack re-identifies ${formatShare(naive)} of people`;
  if (published > 0) return `${before}; on the published release, ${formatShare(published)}.`;
  return (
    `${before}. ` +
    `The published release holds only groups of at least ${minimumGroupSize(data)} people, so that attack has ` +
    `no person to match there (${formatShare(published)}, by construction); no attack on the group tables was run.`
  );
}

/** The answer first, in plain words, for readers who will not read the tables. */
export function ExecutiveSummary({ data, onSelect }: { data: ReleaseData; onSelect?: (view: ViewId) => void }) {
  const { answer, points } = executiveSummary(releaseHypotheses(data));
  const privacy = privacyLine(data);
  const finding = recordFinding(data);
  return (
    <Card className="border-primary/40">
      <CardHeader>
        <CardDescription>In short</CardDescription>
        <CardTitle className="text-2xl leading-snug">{finding ?? answer}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {finding !== null && <p className="text-base">{answer}</p>}
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
