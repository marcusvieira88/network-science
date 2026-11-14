import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export const LIMITS = [
  {
    title: "Who is in the data",
    text: "The corpus holds about 150 mailboxes, mostly of senior staff, as retained and later published. It is not a sample of the organisation: what people deleted, and everyone without a mailbox in the set, is missing.",
  },
  {
    title: "Headers only",
    text: "Only who wrote to whom and when is analysed. No subject, body or attachment is read, so the analysis says nothing about what was discussed.",
  },
  {
    title: "Groups, not people",
    text: "Every number here describes groups of at least the minimum size. Group membership is never published, and no view can show an individual.",
  },
  {
    title: "Association, not cause",
    text: "A change in the network around a public event is consistent with many explanations, including changes in retention or in who was still employed. Hypotheses were fixed before results; each outcome is reported, supported or not.",
  },
  {
    title: "Identity resolution",
    text: "Addresses are merged into people by documented rules whose precision and recall were measured, not assumed. Errors remain and move counts slightly.",
  },
  {
    title: "Risk is measured against two attackers",
    text: "The re-identification figures come from two concrete attacks. A stronger or better-informed attacker could do better; the noisy release R2 is a sketch, not a formal privacy guarantee.",
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
      <div className="grid gap-4 md:grid-cols-2">
        {LIMITS.map((limit) => (
          <Card key={limit.title}>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">{limit.title}</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">{limit.text}</CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
