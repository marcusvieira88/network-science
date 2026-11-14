import { act, render, screen } from "@testing-library/react";
import { Group, Mesh, type Object3D, Points, Sprite } from "three";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CommunityGraph3D from "@/components/CommunityGraph3D";
import type { NetworkMode, Point } from "@/lib/cells";
import { type GraphLink, type GraphNode, LAYOUT_TICKS, LINK_CURVATURE } from "@/lib/network3d";

type Placed = GraphNode & { x?: number; fx?: number };

interface CapturedProps {
  graphData: { nodes: Placed[]; links: GraphLink[] };
  linkVisibility: boolean;
  warmupTicks: number;
  enableNodeDrag: boolean;
  onEngineStop: () => void;
  nodeThreeObject: (node: Placed) => Object3D;
  nodeLabel: (node: Placed) => string;
  linkCurvature: number;
  linkDirectionalParticles: string;
  linkDirectionalParticleSpeed: string;
}

const captured: { props: CapturedProps | null } = { props: null };
const zoomToFit = vi.fn();
const addPass = vi.fn();

// three.js needs WebGL, which jsdom lacks; the stand-in records the props it receives.
vi.mock("react-force-graph-3d", async () => {
  const { forwardRef, useImperativeHandle } = await import("react");
  return {
    default: forwardRef<object, CapturedProps>(function ForceGraphStub(props, ref) {
      useImperativeHandle(ref, () => ({ zoomToFit, postProcessingComposer: () => ({ addPass }) }));
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
  { id: "G01", nPersons: 14, val: 14, radius: 7, color: "hsl(213, 76%, 72.0%)" },
  { id: "G02", nPersons: 9, val: 9, radius: 6, color: "hsl(213, 76%, 40.0%)" },
];
const tie = { source: "G01", target: "G02", color: "rgba(157, 194, 242, 0.850)" };
const allTies: GraphLink[] = [{ ...tie, weight: 9, width: 3, particles: 6, particleSpeed: 0.012 }];
const weekTies: GraphLink[] = [{ ...tie, weight: 2, width: 1, particles: 2, particleSpeed: 0.004 }];
const points = new Map<string, Point[]>([
  ["G01", Array.from({ length: 14 }, (_, i) => [i / 10, 0, 0])],
  ["G02", Array.from({ length: 9 }, (_, i) => [0, i / 10, 0])],
]);

function renderCanvas(links: GraphLink[], week: string, mode: NetworkMode = "groups") {
  return <CommunityGraph3D nodes={nodes} links={links} layout={allTies} week={week} mode={mode} points={points} />;
}

/** Every object below `root`, depth first. */
function descendants(root: Object3D): Object3D[] {
  return [root, ...root.children.flatMap(descendants)];
}

function latest(): CapturedProps {
  if (!captured.props) throw new Error("force graph not rendered");
  return captured.props;
}

describe("CommunityGraph3D", () => {
  beforeEach(() => {
    captured.props = null;
    zoomToFit.mockClear();
    addPass.mockClear();
    vi.stubGlobal("ResizeObserver", SizedResizeObserver);
  });

  it("lays out on all weeks' ties with links hidden, then freezes positions and shows the week", () => {
    const { rerender } = render(renderCanvas(weekTies, "2000-01-03"));
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
    rerender(renderCanvas([], "2000-01-10"));
    expect(latest().graphData.links).toEqual([]);
    expect(latest().graphData.nodes).toBe(placedBefore);
  });

  it("never hands the engine the caller's objects, which it would mutate", () => {
    render(renderCanvas(weekTies, "2000-01-03"));
    expect(latest().graphData.nodes[0]).not.toBe(nodes[0]);
    expect(latest().graphData.links[0]).not.toBe(allTies[0]);
  });

  it("draws curved ties with signal particles taken from each link, and adds one bloom pass", () => {
    const { rerender } = render(renderCanvas(weekTies, "2000-01-03"));
    expect(latest().linkCurvature).toBe(LINK_CURVATURE);
    expect(latest().linkDirectionalParticles).toBe("particles");
    expect(latest().linkDirectionalParticleSpeed).toBe("particleSpeed");
    expect(addPass).toHaveBeenCalledTimes(1);
    expect(addPass.mock.calls[0]?.[0]).toBeInstanceOf(UnrealBloomPass);
    rerender(renderCanvas([], "2000-01-10"));
    expect(addPass).toHaveBeenCalledTimes(1);
  });

  it("in the Groups mode draws each group as a glowing cell body with a halo and a hover label", () => {
    render(renderCanvas(weekTies, "2000-01-03"));
    const [first] = latest().graphData.nodes;
    if (!first) throw new Error("no node");
    const cell = latest().nodeThreeObject(first);
    expect(cell).toBeInstanceOf(Group);
    expect(cell.children.map((child) => child.constructor)).toEqual([Mesh, Sprite]);
    expect(descendants(cell).some((object) => object instanceof Points)).toBe(false);
    expect(latest().nodeLabel(first)).toBe("Group G01 · 14 people");
  });

  it("in the Individuals mode draws n_persons anonymous vertices per group, with no label or data", () => {
    render(renderCanvas(weekTies, "2000-01-03", "individuals"));
    expect(screen.getByRole("img")).toHaveAttribute("data-mode", "individuals");
    let vertices = 0;
    for (const node of latest().graphData.nodes) {
      const objects = descendants(latest().nodeThreeObject(node));
      const clouds = objects.filter((object): object is Points => object instanceof Points);
      expect(clouds).toHaveLength(1);
      vertices += clouds[0]?.geometry.getAttribute("position").count ?? 0;
      for (const object of objects) {
        expect(object.name).toBe("");
        expect(object.userData).toEqual({});
      }
      expect(latest().nodeLabel(node)).toBe("");
    }
    expect(vertices).toBe(14 + 9);
  });
});
