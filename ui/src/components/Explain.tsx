import { CircleHelp } from "lucide-react";
import { useId, useState } from "react";

import { glossaryMeaning } from "@/lib/glossary";

/**
 * A "?" next to a technical term: it opens the term's one-line glossary meaning in place. The
 * button carries no visible text, so the label it sits in reads exactly as before.
 */
export function Explain({ term }: { term: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        aria-label={`What does “${term}” mean?`}
        onClick={() => setOpen((value) => !value)}
        className="ml-1 inline-flex h-5 w-5 items-center justify-center rounded-full align-middle text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring print:hidden"
      >
        <CircleHelp className="h-4 w-4" aria-hidden />
      </button>
      <span
        id={id}
        role="note"
        hidden={!open}
        // A display class would override the hidden attribute, so the box only gets one while open.
        className={
          open
            ? "mt-1 block max-w-prose rounded-md border bg-muted/50 px-2.5 py-1.5 text-left text-xs font-normal normal-case leading-relaxed tracking-normal text-foreground"
            : "hidden"
        }
      >
        {glossaryMeaning(term)}
      </span>
    </>
  );
}
