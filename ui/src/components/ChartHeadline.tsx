/** What a chart shows, in one sentence from the data, and how to read it. */
export function ChartHeadline({ headline, caption }: { headline: string | null; caption: string }) {
  return (
    <div className="space-y-1">
      {headline !== null && <p className="text-base font-medium leading-snug text-foreground">{headline}</p>}
      <p className="text-sm text-muted-foreground">
        <span className="font-medium text-foreground/80">How to read it: </span>
        {caption}
      </p>
    </div>
  );
}
