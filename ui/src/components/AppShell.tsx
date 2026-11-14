import {
  AlertTriangle,
  BarChart3,
  BookOpen,
  CheckSquare,
  ClipboardList,
  Filter,
  LayoutDashboard,
  type LucideIcon,
  Orbit,
  Share2,
  ShieldCheck,
} from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import type { RunInfo } from "@/lib/data";
import { cn } from "@/lib/utils";
import { VIEWS, type ViewId } from "@/lib/views";

const ICONS: Record<ViewId, LucideIcon> = {
  summary: ClipboardList,
  overview: LayoutDashboard,
  metrics: BarChart3,
  network: Share2,
  clusters: Orbit,
  hypotheses: CheckSquare,
  quality: Filter,
  risk: ShieldCheck,
  limits: AlertTriangle,
  glossary: BookOpen,
};

interface AppShellProps {
  active: ViewId;
  onSelect: (view: ViewId) => void;
  run: RunInfo;
  contractVersion: string;
  source: "release" | "sample";
  children: ReactNode;
}

/** The main region's id: the skip link's target, and where focus lands when a view opens from its content. */
export const MAIN_ID = "main";

function parameterText(value: unknown): string {
  return Array.isArray(value) ? value.join(", ") : String(value);
}

export function AppShell({ active, onSelect, run, contractVersion, source, children }: AppShellProps) {
  const activeLabel = VIEWS.find((view) => view.id === active)?.label ?? "";
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <a
        href={`#${MAIN_ID}`}
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-primary-foreground"
      >
        Skip to content
      </a>
      <aside className="print:hidden border-b md:sticky md:top-0 md:h-screen md:w-60 md:shrink-0 md:border-b-0 md:border-r">
        <div className="flex items-center gap-2 px-5 py-4">
          <span className="h-2.5 w-2.5 rounded-full bg-primary" aria-hidden />
          <span className="text-sm font-semibold tracking-tight">Enron network case</span>
        </div>
        <nav aria-label="Views" className="overflow-x-auto px-3 pb-3 md:pb-0">
          <ul className="flex gap-1 md:flex-col">
            {VIEWS.map((view) => {
              const Icon = ICONS[view.id];
              const current = view.id === active;
              return (
                <li key={view.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(view.id)}
                    aria-current={current ? "page" : undefined}
                    className={cn(
                      "flex w-full items-center gap-2.5 whitespace-nowrap rounded-md px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      current
                        ? "bg-accent text-foreground"
                        : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                    )}
                  >
                    <Icon className={cn("h-4 w-4", current && "text-primary")} aria-hidden />
                    {view.label}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-4 border-b px-6 py-4 print:px-0 print:py-1">
          <h1 className="text-lg font-semibold tracking-tight">{activeLabel}</h1>
          {source === "sample" ? (
            <Badge variant="outline" className="border-amber-500/40 text-amber-300 print:text-black">
              Sample data
            </Badge>
          ) : (
            <Badge variant="secondary">Release data</Badge>
          )}
        </header>
        <main id={MAIN_ID} tabIndex={-1} className="flex-1 px-6 py-6 focus:outline-none print:px-0 print:py-1">
          {children}
        </main>
        <footer className="border-t px-6 py-4 text-xs text-muted-foreground print:px-0 print:py-1 print:text-[7pt]">
          <div className="flex flex-wrap gap-x-6 gap-y-1">
            <span>
              Seed <span className="font-mono text-foreground">{run.seed}</span>
            </span>
            <span>
              Code version <span className="font-mono text-foreground">{run.code_version}</span>
            </span>
            <span>
              Contract <span className="font-mono text-foreground">{contractVersion}</span>
            </span>
            <span>{run.sample ? "Synthetic sample corpus" : "Public Enron corpus"}</span>
          </div>
          <details className="mt-2 print:hidden">
            <summary className="cursor-pointer select-none hover:text-foreground">Run parameters</summary>
            <dl className="mt-2 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-0.5 sm:grid-cols-[max-content_1fr_max-content_1fr]">
              {Object.entries(run.parameters).map(([name, value]) => (
                <div key={name} className="contents">
                  <dt>{name}</dt>
                  <dd className="font-mono text-foreground">{parameterText(value)}</dd>
                </div>
              ))}
            </dl>
          </details>
        </footer>
      </div>
    </div>
  );
}
