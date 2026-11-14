export const VIEWS = [
  { id: "overview", label: "Overview" },
  { id: "metrics", label: "Metrics" },
  { id: "network", label: "Network" },
  { id: "clusters", label: "Clusters" },
  { id: "hypotheses", label: "Hypotheses" },
  { id: "quality", label: "Data quality" },
  { id: "risk", label: "Privacy and risk" },
  { id: "limits", label: "Limits" },
] as const;

export type ViewId = (typeof VIEWS)[number]["id"];
