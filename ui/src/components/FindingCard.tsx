import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { HypothesisRow } from "@/lib/data";
import { formatInterval, formatNumber, formatP, metricLabel } from "@/lib/format";
import { headline } from "@/lib/series";

export function ConfidenceBadge({ confidence }: { confidence: HypothesisRow["confidence"] }) {
  const variant = confidence === "high" ? "default" : confidence === "moderate" ? "secondary" : "outline";
  return <Badge variant={variant}>{confidence} confidence</Badge>;
}

export function FindingCard({ hypotheses }: { hypotheses: HypothesisRow[] }) {
  const finding = headline(hypotheses);
  if (!finding) {
    return (
      <Card>
        <CardHeader>
          <CardDescription>Headline finding</CardDescription>
          <CardTitle className="text-xl">No hypothesis supported</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          None of the pre-registered hypotheses H1–H4 passed the test after correction for multiple testing.
          This is reported as a result, not hidden: see the Hypotheses view for every outcome.
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
            <dt className="text-xs text-muted-foreground">Effect (standardised)</dt>
            <dd className="text-2xl font-semibold tabular-nums">{formatNumber(finding.effect)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">95% interval</dt>
            <dd className="text-2xl font-semibold tabular-nums">{formatInterval(finding.ci_low, finding.ci_high)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">p (Holm-adjusted)</dt>
            <dd className="text-2xl font-semibold tabular-nums">{formatP(finding.p_holm)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Robust variants</dt>
            <dd className="text-2xl font-semibold tabular-nums">
              {finding.robust_variants_passed} / {finding.robust_variants_total}
            </dd>
          </div>
        </dl>
        <p className="mt-4 text-sm text-muted-foreground">
          Leaving out any single mailbox moves the effect between {formatNumber(finding.loo_min_effect)} and{" "}
          {formatNumber(finding.loo_max_effect)}.
        </p>
      </CardContent>
    </Card>
  );
}
