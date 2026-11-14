import { ArrowRight, Printer } from "lucide-react";
import type { ReactNode } from "react";

import { LIMITS } from "@/components/Limits";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type { ReleaseData } from "@/lib/data";
import { type SummaryCard, summaryCards, whatItMeans } from "@/lib/executive";
import type { ViewId } from "@/lib/views";

interface SummaryViewProps {
  data: ReleaseData;
  onSelect: (view: ViewId) => void;
}

function EvidenceLink({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <Button variant="link" className="h-auto self-start px-0 text-sm print:hidden" onClick={onClick}>
      {label} <ArrowRight className="h-4 w-4" aria-hidden />
    </Button>
  );
}

function SummaryCardView({ card, onSelect }: { card: SummaryCard; onSelect: (view: ViewId) => void }) {
  const headingId = `summary-${card.key}`;
  return (
    <Card role="article" aria-labelledby={headingId} className="flex flex-col break-inside-avoid print:shadow-none">
      <CardHeader className="space-y-2 pb-3 print:space-y-0.5 print:p-2 print:pb-1">
        <p className="text-xs font-medium uppercase tracking-wider text-primary print:text-[6pt]">{card.eyebrow}</p>
        <h2 id={headingId} className="text-xl font-semibold leading-snug tracking-tight print:text-[9pt]">
          {card.title}
        </h2>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col justify-between gap-3 print:p-2 print:pt-0">
        <ul className="list-disc space-y-1.5 pl-5 text-base leading-relaxed text-muted-foreground print:space-y-0 print:text-[7.5pt] print:leading-tight">
          {card.points.map((point) => (
            <li key={point}>{point}</li>
          ))}
        </ul>
        <EvidenceLink label={card.linkLabel} onClick={() => onSelect(card.view)} />
      </CardContent>
    </Card>
  );
}

function Panel({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="rounded-xl border bg-card p-6 break-inside-avoid print:p-2">
      <h2 id={id} className="mb-3 text-lg font-semibold tracking-tight print:mb-1 print:text-[9pt]">
        {title}
      </h2>
      {children}
    </section>
  );
}

/** The landing view: the study in six plain cards, what it means, and what it cannot tell. */
export function SummaryView({ data, onSelect }: SummaryViewProps) {
  return (
    <div className="space-y-6 print:space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <p className="max-w-prose text-base text-muted-foreground print:hidden">
          The study in plain words. Every number and verdict below is read from the published release; each card links to
          its evidence.
        </p>
        <Button variant="outline" onClick={() => window.print()} className="print:hidden">
          <Printer className="h-4 w-4" aria-hidden /> Print this summary
        </Button>
      </div>
      {data.run.sample && (
        <p className="rounded-lg border border-amber-500/40 bg-amber-500/5 px-4 py-3 text-sm text-amber-200 print:text-[8pt] print:text-black">
          These numbers come from the synthetic sample corpus, not from the Enron data.
        </p>
      )}
      <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3 print:grid-cols-3 print:gap-2">
        {summaryCards(data).map((card) => (
          <SummaryCardView key={card.key} card={card} onSelect={onSelect} />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2 print:grid-cols-2 print:gap-2">
        <Panel id="summary-means" title="What this means for a real organisation">
          <ul className="list-disc space-y-2 pl-5 text-base leading-relaxed text-muted-foreground print:space-y-0 print:text-[7.5pt] print:leading-tight">
            {whatItMeans(data).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </Panel>
        <Panel id="summary-cannot" title="What this cannot tell you">
          <ul className="space-y-2 text-base leading-relaxed print:space-y-0 print:text-[7.5pt] print:leading-tight">
            {LIMITS.map((limit) => (
              <li key={limit.title}>
                <span className="font-medium text-foreground">{limit.title}: </span>
                <span className="text-muted-foreground">{limit.plain}</span>
              </li>
            ))}
          </ul>
          <EvidenceLink label="All limits, explained" onClick={() => onSelect("limits")} />
        </Panel>
      </div>
    </div>
  );
}
