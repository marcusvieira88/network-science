export const VIEWS = [
  { id: "summary", label: "Executive summary" },
  { id: "overview", label: "Overview" },
  { id: "metrics", label: "Metrics" },
  { id: "network", label: "Network" },
  { id: "clusters", label: "Clusters" },
  { id: "hypotheses", label: "Hypotheses" },
  { id: "quality", label: "Data quality" },
  { id: "risk", label: "Privacy and risk" },
  { id: "limits", label: "Limits" },
  { id: "glossary", label: "Glossary" },
] as const;

export type ViewId = (typeof VIEWS)[number]["id"];

/** The view the explorer opens on. */
export const LANDING_VIEW: ViewId = "summary";
