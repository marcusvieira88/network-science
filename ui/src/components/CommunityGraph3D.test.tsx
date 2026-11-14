import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CommunityGraph3D from "@/components/CommunityGraph3D";
import { type GraphLink, type GraphNode, LAYOUT_TICKS } from "@/lib/network3d";

interface CapturedProps {
  graphData: { nodes: (GraphNode & { x?: number; fx?: number })[]; links: GraphLink[] };
  linkVisibility: boolean;
  warmupTicks: number;
  enableNodeDrag: boolean;
  onEngineStop: () => void;
}

const captured: { props: CapturedProps | null } = { props: null };
const zoomToFit = vi.fn();

// three.js needs WebGL, which jsdom lacks; the stand-in records the props it receives.
vi.mock("react-force-graph-3d", async () => {
  const { forwardRef, useImperativeHandle } = await import("react");
  return {
    default: forwardRef<{ zoomToFit: typeof zoomToFit }, CapturedProps>(function ForceGraphStub(props, ref) {
      useImperativeHandle(ref, () => ({ zoomToFit }));
      captured.props = props;
      return <div data-testid="force-graph" />;
    }),
  };
});

class SizedResizeObserver implements ResizeObserver {
  constructor(private readonly callback: ResizeObserverCallback) {}
  observe(): void {
    this.callback([{ contentRect: { width: 800 } } as ResizeObserverEntry], this);
  }
  unobserve(): void {}
  disconnect(): void {}
}

const nodes: GraphNode[] = [
  { id: "G01", nPersons: 14, val: 14, color: "hsl(213, 76%, 72.0%)" },
  { id: "G02", nPersons: 9, val: 9, color: "hsl(213, 76%, 40.0%)" },
];
const allTies: GraphLink[] = [{ source: "G01", target: "G02", weight: 9, width: 3, color: "rgba(138, 137, 132, 0.850)" }];
const weekTies: GraphLink[] = [{ source: "G01", target: "G02", weight: 2, width: 1, color: "rgba(138, 137, 132, 0.400)" }];

function latest(): CapturedProps {
  if (!captured.props) throw new Error("force graph not rendered");
  return captured.props;
}

describe("CommunityGraph3D", () => {
  beforeEach(() => {
    captured.props = null;
    zoomToFit.mockClear();
    vi.stubGlobal("ResizeObserver", SizedResizeObserver);
  });

  it("lays out on all weeks' ties with links hidden, then freezes positions and shows the week", () => {
    const { rerender } = render(<CommunityGraph3D nodes={nodes} links={weekTies} layout={allTies} week="2000-01-03" />);
    expect(screen.getByRole("img")).toHaveAccessibleName("3D group network for the week of 2000-01-03");
    expect(latest().warmupTicks).toBe(LAYOUT_TICKS);
    expect(latest().enableNodeDrag).toBe(false);
    expect(latest().linkVisibility).toBe(false);
    expect(latest().graphData.links.map((l) => l.weight)).toEqual([9]);

    // The engine has placed the nodes and stopped.
    latest().graphData.nodes.forEach((node, i) => Object.assign(node, { x: 10 * (i + 1), y: 0, z: 0 }));
    act(() => latest().onEngineStop());
    expect(latest().linkVisibility).toBe(true);
    expect(latest().graphData.links.map((l) => l.weight)).toEqual([2]);
    expect(latest().graphData.nodes.map((n) => n.fx)).toEqual([10, 20]);
    expect(zoomToFit).toHaveBeenCalledTimes(1);
    // A later engine stop (the week changed) neither moves the camera nor re-fixes the layout.
    act(() => latest().onEngineStop());
    expect(zoomToFit).toHaveBeenCalledTimes(1);

    const placedBefore = latest().graphData.nodes;
    rerender(<CommunityGraph3D nodes={nodes} links={[]} layout={allTies} week="2000-01-10" />);
    expect(latest().graphData.links).toEqual([]);
    expect(latest().graphData.nodes).toBe(placedBefore);
  });

  it("never hands the engine the caller's objects, which it would mutate", () => {
    render(<CommunityGraph3D nodes={nodes} links={weekTies} layout={allTies} week="2000-01-03" />);
    expect(latest().graphData.nodes[0]).not.toBe(nodes[0]);
    expect(latest().graphData.links[0]).not.toBe(allTies[0]);
  });
});
