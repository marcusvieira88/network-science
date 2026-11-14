import { Explain } from "@/components/Explain";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { ArtifactCheckRow, HypothesisRow } from "@/lib/data";
import { noFindingExplanation } from "@/lib/finding";
import { formatFloat, formatInterval, formatP, metricLabel } from "@/lib/format";
import { NO_BEHAVIOURAL_FINDING } from "@/lib/record";
import { headline } from "@/lib/series";

export function ConfidenceBadge({ confidence }: { confidence: HypothesisRow["confidence"] }) {
  const variant = confidence === "high" ? "default" : confidence === "moderate" ? "secondary" : "outline";
  return <Badge variant={variant}>{confidence} confidence</Badge>;
}

export function FindingCard({
  hypotheses,
  artifactChecks,
  recordFinding = null,
}: {
  hypotheses: HypothesisRow[];
  artifactChecks: ArtifactCheckRow[];
  /** The finding about the record (lib/record.ts), stated before what is not claimed about behaviour. */
  recordFinding?: string | null;
}) {
  const finding = headline(hypotheses);
  if (!finding) {
    const { title, body } = noFindingExplanation(hypotheses, artifactChecks);
    return (
      <Card>
        <CardHeader>
          <CardDescription>Headline among the pre-registered hypotheses</CardDescription>
          <CardTitle className="text-xl">{title}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          {recordFinding !== null && (
            <p className="text-foreground">
              {recordFinding} {NO_BEHAVIOURAL_FINDING}
            </p>
          )}
          {body.map((sentence) => (
            <p key={sentence}>{sentence}</p>
          ))}
        </CardContent>
      </Card>
    );
  }
  return (
    <Card className="border-primary/30">
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <CardDescription>Headline finding · {finding.hypothesis}</CardDescription>
          <ConfidenceBadge confidence={finding.confidence} />
        </div>
        <CardTitle className="text-xl leading-snug">
          {metricLabel(finding.metric)} changed in the {finding.scope} network
          {finding.change_week ? ` from the week of ${finding.change_week}` : ""}.
        </CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div>
            <dt className="text-xs text-muted-foreground">
              Effect (standardised)
              <Explain term="Effect (standardised)" />
            </dt>
            <dd className="text-2xl font-semibold tabular-nums">{formatFloat(finding.effect)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">
              95% interval
              <Explain term="95% interval" />
            </dt>
            <dd className="text-2xl font-semibold tabular-nums">{formatInterval(finding.ci_low, finding.ci_high)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">
              p (Holm-adjusted)
              <Explain term="p (Holm)" />
            </dt>
            <dd className="text-2xl font-semibold tabular-nums">{formatP(finding.p_holm)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">
              Robust variants
              <Explain term="Robustness variants" />
            </dt>
            <dd className="text-2xl font-semibold tabular-nums">
              {finding.robust_variants_passed} / {finding.robust_variants_total}
            </dd>
          </div>
        </dl>
        <p className="mt-4 text-sm text-muted-foreground">
          Leaving out any single mailbox moves the effect between {formatFloat(finding.loo_min_effect)} and{" "}
          {formatFloat(finding.loo_max_effect)}.
        </p>
      </CardContent>
    </Card>
  );
}
