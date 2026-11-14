import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/** The limits of release/report.md: `plain` says what each means for a reader, `text` explains it. */
export const LIMITS = [
  {
    title: "Who is in the data",
    plain: "It describes the mailboxes that were kept, mostly of senior staff, not the whole company.",
    text: "The corpus holds about 150 mailboxes, mostly of senior staff, as retained and later published. It is not a sample of the organisation: what people deleted, and everyone without a mailbox in the set, is missing.",
  },
  {
    title: "Headers only",
    plain: "It says nothing about what was discussed.",
    text: "Only who wrote to whom and when is analysed. No subject, body or attachment is read, so the analysis says nothing about what was discussed. Without content, deduplication also merges distinct messages from one sender to the same recipients in the same second.",
  },
  {
    title: "Groups, not people",
    plain: "It cannot tell you anything about one individual.",
    text: "Every number here describes groups of at least the minimum size. Group membership is never published, and no view can show an individual.",
  },
  {
    title: "Association, not cause",
    plain: "It cannot tell you why something changed, or what people knew.",
    text: "A change in the network around a public event is consistent with many explanations, including changes in retention or in who was still employed. Hypotheses were fixed before results; each outcome is reported, supported or not.",
  },
  {
    title: "Identity resolution",
    plain: "Counts of people are close, not exact.",
    text: "Addresses are merged into people by documented rules whose precision and recall were measured, not assumed. Errors remain and move counts slightly.",
  },
  {
    title: "Risk is measured against three attackers",
    plain: "It does not prove that no one could ever re-identify anyone.",
    text: "The re-identification figures come from three concrete attacks. A stronger or better-informed attacker could do better; the noisy release R2 is a sketch, not a formal privacy guarantee.",
  },
  {
    title: "Small p-values are weak evidence here",
    plain: "A small p-value alone does not make a change real.",
    text: "The weekly tests of H1–H4 treat weeks as interchangeable, but weekly network measures follow on from one another; a calibration test shows such tests reject far more often than their nominal level. Their intervals are also optimistic, because the change week is chosen from the same data.",
  },
  {
    title: "The group tables were not attacked",
    plain: "The risk of the published group tables is limited by design, not measured.",
    text: "No attack on the published group-to-group tables was run. An attacker who knows some group members could try to infer ties or membership from them; that risk is bounded only by the rule that every published tie has at least k distinct senders.",
  },
] as const;

export function Limits({ sample }: { sample: boolean }) {
  return (
    <div className="space-y-4">
      {sample && (
        <p className="rounded-lg border border-amber-500/40 bg-amber-500/5 px-4 py-3 text-sm text-amber-200">
          These numbers come from the synthetic sample corpus, not from the Enron data.
        </p>
      )}
      <p className="max-w-prose text-base text-muted-foreground">
        What this analysis cannot tell you. Each limit opens with what it means for a reader, then explains why.
      </p>
      <div className="grid gap-4 md:grid-cols-2">
        {LIMITS.map((limit) => (
          <Card key={limit.title}>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">{limit.title}</CardTitle>
              <CardDescription className="text-base text-foreground">{limit.plain}</CardDescription>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">{limit.text}</CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
