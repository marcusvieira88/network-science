import { Badge } from "@/components/ui/badge";
import type { HypothesisEntry } from "@/lib/hypotheses";
import { type PlainVerdict, type Verdict, plainVerdict } from "@/lib/plainLanguage";
import { cn } from "@/lib/utils";

const VERDICT_VARIANT: Record<Verdict, "default" | "secondary" | "outline" | "destructive"> = {
  held: "default",
  artifact: "destructive",
  weak: "secondary",
  unclear: "secondary",
  untestable: "outline",
  none: "outline",
  withheld: "outline",
};

/** The common outcomes, folded under one line so the noteworthy ones are read first. */
const FOLDED: ReadonlySet<Verdict> = new Set<Verdict>(["none", "withheld"]);

interface Reading {
  entry: HypothesisEntry;
  plain: PlainVerdict;
}

function ReadingItem({ entry, plain }: Reading) {
  return (
    <li
      data-verdict={plain.verdict}
      className={cn("rounded-lg border bg-card p-3", plain.verdict === "held" && "border-primary/50 bg-primary/10")}
    >
      <div className="mb-1 flex items-center gap-2">
        <span className="font-medium">{entry.id}</span>
        <Badge variant={VERDICT_VARIANT[plain.verdict]}>{plain.label}</Badge>
      </div>
      <p className="text-sm text-muted-foreground">{plain.sentence}</p>
    </li>
  );
}

/** Every hypothesis in one plain sentence: noteworthy outcomes first, the rest folded. */
export function PlainHypotheses({ entries }: { entries: HypothesisEntry[] }) {
  const readings = entries.map((entry) => ({ entry, plain: plainVerdict(entry) }));
  const shown = readings.filter((r) => !FOLDED.has(r.plain.verdict));
  const folded = readings.filter((r) => FOLDED.has(r.plain.verdict));
  return (
    <section aria-label="Hypotheses in plain words" className="space-y-3">
      <ul className="grid gap-3 md:grid-cols-2">
        {shown.map((reading) => (
          <ReadingItem key={`${reading.entry.kind}-${reading.entry.id}`} {...reading} />
        ))}
      </ul>
      {folded.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-muted-foreground">
            {folded.length} more with no reliable change or withheld — show them
          </summary>
          <ul className="mt-3 grid gap-3 md:grid-cols-2">
            {folded.map((reading) => (
              <ReadingItem key={`${reading.entry.kind}-${reading.entry.id}`} {...reading} />
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
