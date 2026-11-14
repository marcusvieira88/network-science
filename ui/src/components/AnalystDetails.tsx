import { ChevronRight } from "lucide-react";
import type { ReactNode } from "react";

/** The full statistics, folded under one line so leaders read the plain answer first. */
export function AnalystDetails({ children }: { children: ReactNode }) {
  return (
    <details className="group rounded-xl border bg-card print:hidden">
      <summary className="flex cursor-pointer list-none items-center gap-2 rounded-xl px-5 py-3 text-sm font-medium hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
        <ChevronRight className="h-4 w-4 transition-transform group-open:rotate-90" aria-hidden />
        Details for analysts
      </summary>
      <div className="space-y-6 border-t p-5">{children}</div>
    </details>
  );
}
