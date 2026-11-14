import * as React from "react";
import * as RechartsPrimitive from "recharts";

import { cn } from "@/lib/utils";

// shadcn/ui chart, reduced to the parts this app uses: a container that turns a config into
// CSS colour variables, and tooltip and legend contents styled with the theme.

export type ChartConfig = Record<string, { label?: React.ReactNode; color?: string }>;

const ChartContext = React.createContext<{ config: ChartConfig } | null>(null);

function useChart() {
  const context = React.useContext(ChartContext);
  if (!context) throw new Error("useChart must be used within a <ChartContainer />");
  return context;
}

const ChartContainer = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<"div"> & {
    config: ChartConfig;
    children: React.ComponentProps<typeof RechartsPrimitive.ResponsiveContainer>["children"];
  }
>(({ id, className, children, config, style, ...props }, ref) => {
  const uniqueId = React.useId();
  const chartId = `chart-${id ?? uniqueId.replace(/:/g, "")}`;
  const colorVars = Object.fromEntries(
    Object.entries(config)
      .filter(([, item]) => item.color)
      .map(([key, item]) => [`--color-${key}`, item.color]),
  ) as React.CSSProperties;
  return (
    <ChartContext.Provider value={{ config }}>
      <div
        data-chart={chartId}
        ref={ref}
        style={{ ...colorVars, ...style }}
        className={cn(
          "flex aspect-video justify-center text-xs [&_.recharts-cartesian-axis-tick_text]:fill-muted-foreground [&_.recharts-cartesian-grid_line[stroke='#ccc']]:stroke-border/50 [&_.recharts-curve.recharts-tooltip-cursor]:stroke-border [&_.recharts-reference-line_[stroke='#ccc']]:stroke-border [&_.recharts-surface]:outline-none",
          className,
        )}
        {...props}
      >
        <RechartsPrimitive.ResponsiveContainer>{children}</RechartsPrimitive.ResponsiveContainer>
      </div>
    </ChartContext.Provider>
  );
});
ChartContainer.displayName = "Chart";

const ChartTooltip = RechartsPrimitive.Tooltip;

type TooltipPayloadItem = {
  dataKey?: string | number;
  name?: string | number;
  value?: number | string | null;
  color?: string;
};

const ChartTooltipContent = React.forwardRef<
  HTMLDivElement,
  {
    active?: boolean;
    payload?: TooltipPayloadItem[];
    label?: React.ReactNode;
    formatValue?: (value: number) => string;
  }
>(({ active, payload, label, formatValue = (value) => value.toLocaleString() }, ref) => {
  const { config } = useChart();
  if (!active || !payload?.length) return null;
  return (
    <div
      ref={ref}
      className="grid min-w-[8rem] items-start gap-1.5 rounded-lg border border-border/50 bg-popover px-2.5 py-1.5 text-xs shadow-xl"
    >
      <div className="font-medium">{label}</div>
      {payload.map((item) => {
        const key = String(item.dataKey ?? item.name ?? "value");
        const value = typeof item.value === "number" ? formatValue(item.value) : "suppressed";
        return (
          <div key={key} className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 shrink-0 rounded-[2px]" style={{ background: item.color }} />
            <span className="text-muted-foreground">{config[key]?.label ?? key}</span>
            <span className="ml-auto font-mono font-medium tabular-nums text-foreground">{value}</span>
          </div>
        );
      })}
    </div>
  );
});
ChartTooltipContent.displayName = "ChartTooltip";

const ChartLegend = RechartsPrimitive.Legend;

const ChartLegendContent = React.forwardRef<
  HTMLDivElement,
  { payload?: { dataKey?: string | number; value?: string; color?: string }[] }
>(({ payload }, ref) => {
  const { config } = useChart();
  if (!payload?.length) return null;
  return (
    <div ref={ref} className="flex items-center justify-center gap-4 pt-3">
      {payload.map((item) => {
        const key = String(item.dataKey ?? item.value ?? "value");
        return (
          <div key={key} className="flex items-center gap-1.5">
            <span className="h-2 w-2 shrink-0 rounded-[2px]" style={{ backgroundColor: item.color }} />
            <span className="text-muted-foreground">{config[key]?.label ?? key}</span>
          </div>
        );
      })}
    </div>
  );
});
ChartLegendContent.displayName = "ChartLegend";

export { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent };
