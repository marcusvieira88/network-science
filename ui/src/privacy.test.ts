import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createElement, forwardRef, useImperativeHandle } from "react";
import { type Object3D, Points } from "three";
import { describe, expect, it, vi } from "vitest";

import { View } from "@/App";
import { CommunityGraph } from "@/components/CommunityGraph";
import { totalPoints } from "@/lib/cells";
import { TABLE_COLUMNS } from "@/lib/data";
import { LEAK_PATTERN, PERSON_COUNT_COLUMNS, identifierCount, minimumGroupSize, smallPersonCounts } from "@/lib/privacy";
import { VIEWS } from "@/lib/views";
import { rawSample, sampleData } from "@/test/sample";

interface ScenePropsSeen {
  graphData: { nodes: { id: string }[] };
  nodeThreeObject: (node: { id: string }) => Object3D;
  nodeLabel: (node: { id: string }) => string;
}

const scene: { props: ScenePropsSeen | null } = { props: null };

// WebGL does not run in jsdom: the 3D graph is replaced by a stand-in that keeps what it was given,
// so the test can inspect the scene objects the view would draw.
vi.mock("react-force-graph-3d", () => ({
  default: forwardRef<object, ScenePropsSeen>(function SceneStub(props, ref) {
    useImperativeHandle(ref, () => ({ zoomToFit: () => undefined, postProcessingComposer: () => ({ addPass: () => undefined }) }));
    scene.props = props;
    return createElement("div", { "data-testid": "scene" });
  }),
}));

/** Attributes a bare anonymous point may carry: position, size and colour, nothing else. */
const BARE_POINT_ATTRIBUTES = ["cx", "cy", "fill", "r"];

function descendants(root: Object3D): Object3D[] {
  return [root, ...root.children.flatMap(descendants)];
}

// Column names that would only exist in person-level data.
const PERSON_LEVEL_COLUMNS = /pid|addr|name|owner|member|person_id|entity/i;

describe("privacy of the loaded data", () => {
  const data = sampleData();

  it("contains no address and no person or organisation pseudonym", () => {
    expect(JSON.stringify(rawSample())).not.toMatch(/@/);
    expect(identifierCount(rawSample())).toBe(0);
  });

  it("publishes no person count below the minimum group size", () => {
    expect(minimumGroupSize(data)).toBeGreaterThanOrEqual(5);
    expect(smallPersonCounts(data)).toBe(0);
    for (const [table, columns] of Object.entries(PERSON_COUNT_COLUMNS)) {
      for (const row of data.tables[table as keyof typeof PERSON_COUNT_COLUMNS] as Record<string, unknown>[]) {
        for (const column of columns) {
          const count = row[column];
          if (count !== null) expect(count).toBeGreaterThanOrEqual(5);
        }
      }
    }
  });

  it("checks the exploratory custodian counts against the minimum group size", () => {
    const sample = sampleData();
    const [first, ...rest] = sample.tables.exploratory;
    if (!first) throw new Error("sample has no exploratory rows");
    const exploratory = [{ ...first, custodians: 4, placebo_custodians: 3 }, ...rest];
    expect(smallPersonCounts({ ...sample, tables: { ...sample.tables, exploratory } })).toBe(2);
  });

  it("counts an active_persons value below the minimum group size", () => {
    const sample = sampleData();
    const index = sample.tables.weekly_metrics.findIndex((r) => r.metric === "active_persons");
    const row = sample.tables.weekly_metrics[index];
    if (!row) throw new Error("sample has no active_persons rows");
    const weekly = sample.tables.weekly_metrics.map((r, i) => (i === index ? { ...row, value: 4 } : r));
    expect(smallPersonCounts({ ...sample, tables: { ...sample.tables, weekly_metrics: weekly } })).toBe(1);
  });

  it("has no person-level column in any table", () => {
    for (const columns of Object.values(TABLE_COLUMNS)) {
      for (const column of Object.keys(columns)) {
        if (column === "persons" || column === "n_persons") continue; // counts, not identities
        expect(column).not.toMatch(PERSON_LEVEL_COLUMNS);
      }
    }
  });
});

describe("privacy of what the views render", () => {
  const data = sampleData();

  it.each(VIEWS.map((view) => view.id))("view %s renders no identifier and no per-person row", (view) => {
    const { container, unmount } = render(createElement(View, { view, data, onSelect: () => undefined }));
    const text = container.textContent ?? "";
    expect(text).not.toMatch(LEAK_PATTERN);
    expect(container.querySelectorAll("[data-person], [data-pid]")).toHaveLength(0);
    // The network draws one node per published group and nothing finer.
    const nodes = container.querySelectorAll("[data-testid=group-node]");
    if (view === "network") expect(nodes).toHaveLength(data.tables.community_groups.length);
    else expect(nodes).toHaveLength(0);
    // The clusters view draws at most one arc and one table row per published group.
    const arcs = [...container.querySelectorAll("[data-testid=group-arc]")];
    const sizes = [...container.querySelectorAll("[data-testid=group-size]")];
    if (view === "clusters") {
      expect(arcs.length).toBeGreaterThan(0);
      expect(sizes).toHaveLength(data.tables.community_groups.length);
    } else {
      expect(arcs).toHaveLength(0);
      expect(sizes).toHaveLength(0);
    }
    unmount();
  });

  it("clusters view: every segment is a published group of at least k people, in every period", async () => {
    const user = userEvent.setup();
    const published = new Map(data.tables.community_groups.map((g) => [g.group, g.n_persons]));
    const k = minimumGroupSize(data);
    const { container, unmount } = render(createElement(View, { view: "clusters", data, onSelect: () => undefined }));
    expect(container).toHaveTextContent(`Each segment is a group of at least ${k} people, never an individual`);
    for (const period of ["Baseline year", "Crisis weeks", "All weeks"]) {
      await user.click(screen.getByRole("tab", { name: period }));
      const arcs = [...container.querySelectorAll("[data-testid=group-arc]")];
      expect(arcs.length).toBeLessThanOrEqual(published.size);
      for (const arc of arcs) {
        const group = arc.getAttribute("data-group") ?? "";
        expect(published.get(group)).toBeGreaterThanOrEqual(k);
      }
      for (const cell of container.querySelectorAll("[data-testid=group-size]")) {
        expect(Number(cell.textContent)).toBeGreaterThanOrEqual(k);
      }
      expect(container.textContent ?? "").not.toMatch(LEAK_PATTERN);
    }
    unmount();
  });

  it("network view, Individuals mode (2D): one bare point per published person, no id, label or tooltip", async () => {
    const user = userEvent.setup();
    const k = minimumGroupSize(data);
    const { container, unmount } = render(createElement(View, { view: "network", data, onSelect: () => undefined }));
    await user.click(screen.getByRole("tab", { name: "Individuals (anonymous)" }));
    expect(container).toHaveTextContent(`Each point stands for one person in a group of at least ${k};`);
    const layer = screen.getByTestId("anonymous-points");
    expect(layer).toHaveAttribute("aria-hidden", "true");
    expect(layer.closest("[data-testid=group-node], [data-state]")).toBeNull();
    const points = [...layer.children];
    expect(points).toHaveLength(totalPoints(data.tables.community_groups));
    for (const point of points) {
      expect(point.tagName.toLowerCase()).toBe("circle");
      expect(point.getAttributeNames().sort()).toEqual(BARE_POINT_ATTRIBUTES);
      expect(point.childNodes).toHaveLength(0);
    }
    // Groups below k are never published, so they never appear.
    for (const group of data.tables.community_groups) expect(group.n_persons).toBeGreaterThanOrEqual(k);
    expect(container.textContent ?? "").not.toMatch(LEAK_PATTERN);
    unmount();
  });

  it("network view, Individuals mode (3D): one unnamed vertex per published person and no hover label", async () => {
    vi.stubGlobal(
      "ResizeObserver",
      class implements ResizeObserver {
        constructor(private readonly callback: ResizeObserverCallback) {}
        observe(): void {
          this.callback([{ contentRect: { width: 800 } } as ResizeObserverEntry], this);
        }
        unobserve(): void {}
        disconnect(): void {}
      },
    );
    const user = userEvent.setup();
    const { unmount } = render(
      createElement(CommunityGraph, {
        groups: data.tables.community_groups,
        edges: data.tables.community_graph,
        weeks: [],
        events: [],
        minGroupSize: minimumGroupSize(data),
        seed: data.run.seed,
        webgl: true,
      }),
    );
    await user.click(screen.getByRole("tab", { name: "Individuals (anonymous)" }));
    await waitFor(() => expect(screen.getByRole("img")).toHaveAttribute("data-mode", "individuals"));
    const props = scene.props;
    if (!props) throw new Error("scene not rendered");
    let vertices = 0;
    for (const node of props.graphData.nodes) {
      const objects = descendants(props.nodeThreeObject(node));
      for (const object of objects) {
        expect(object.name).toBe("");
        expect(object.userData).toEqual({});
        if (object instanceof Points) {
          vertices += object.geometry.getAttribute("position").count;
          expect(Object.keys(object.geometry.attributes)).toEqual(["position"]);
        }
      }
      expect(props.nodeLabel(node)).toBe("");
    }
    expect(vertices).toBe(totalPoints(data.tables.community_groups));
    unmount();
    vi.unstubAllGlobals();
  });
});
