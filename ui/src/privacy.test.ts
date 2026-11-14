import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createElement } from "react";
import { describe, expect, it, vi } from "vitest";

import { View } from "@/App";
import { CommunityGraph } from "@/components/CommunityGraph";
import { totalPoints } from "@/lib/cells";
import { baselinePeriod } from "@/lib/series";
import { TABLE_COLUMNS } from "@/lib/data";
import { K_FLOOR, LEAK_PATTERN, PERSON_COUNT_COLUMNS, identifierCount, minimumGroupSize, smallPersonCounts } from "@/lib/privacy";
import { type LabelCanvas, drawGroupHover, networkPalette } from "@/lib/sigmaNetwork";
import { VIEWS } from "@/lib/views";
import { layerStub, resetLayerStub } from "@/test/layerWebgl";
import { drawnNode, resetSigmaStub, sigmaStub } from "@/test/reactSigma";
import { rawSample, sampleData } from "@/test/sample";
import { applyThemeVariables } from "@/test/theme";

// WebGL does not run in jsdom: React Sigma is replaced by a stand-in that keeps the graph, the
// settings and the events the view hands to Sigma, so the test can inspect what would be drawn.
vi.mock("@react-sigma/core", () => import("@/test/reactSigma"));
vi.mock("@sigma/layer-webgl", () => import("@/test/layerWebgl"));

/** Attributes a bare anonymous point may carry in the SVG view: position, size and colour. */
const BARE_POINT_ATTRIBUTES = ["cx", "cy", "fill", "r"];
/** Attributes an anonymous Sigma node carries: position, size, colour, kind, drawing order, no label. */
const BARE_NODE_ATTRIBUTES = ["color", "kind", "label", "size", "x", "y", "zIndex"];
/** An anonymous node's key: its group's place in label order and its own sequence number. */
const OPAQUE_POINT_KEY = /^point:\d+-\d+$/;

// Column names that would only exist in person-level data.
const PERSON_LEVEL_COLUMNS = /pid|addr|name|owner|member|person_id|entity/i;

describe("privacy of the loaded data", () => {
  const data = sampleData();

  it("contains no address and no person or organisation pseudonym", () => {
    expect(JSON.stringify(rawSample())).not.toMatch(/@/);
    expect(identifierCount(rawSample())).toBe(0);
  });

  it("takes the minimum group size from k_min, never below the floor", () => {
    const withK = (kMin: unknown) => ({ ...data, run: { ...data.run, parameters: { ...data.run.parameters, k_min: kMin } } });
    expect(minimumGroupSize(withK(K_FLOOR + 4))).toBe(K_FLOOR + 4);
    expect(minimumGroupSize(withK(K_FLOOR - 2))).toBe(K_FLOOR);
    expect(minimumGroupSize(withK(String(K_FLOOR + 4)))).toBe(K_FLOOR);
    expect(minimumGroupSize(withK(undefined))).toBe(K_FLOOR);
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

  it("network view, group-size dots mode (2D): one bare point per published person, no id, label or tooltip", async () => {
    const user = userEvent.setup();
    const k = minimumGroupSize(data);
    const { container, unmount } = render(createElement(View, { view: "network", data, onSelect: () => undefined }));
    await user.click(screen.getByRole("tab", { name: "Group sizes (dots)" }));
    expect(container).toHaveTextContent(`The dots only show how many people each group of at least ${k} has`);
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

  it("network view, group-size dots mode (WebGL): one bare anonymous node per published person, no label, id or tooltip", async () => {
    resetSigmaStub();
    applyThemeVariables();
    const user = userEvent.setup();
    const groups = data.tables.community_groups;
    const k = minimumGroupSize(data);
    const { container, unmount } = render(
      createElement(CommunityGraph, {
        groups,
        edges: data.tables.community_graph,
        weeks: [],
        events: [],
        minGroupSize: k,
        seed: data.run.seed,
        baseline: baselinePeriod(data),
        webgl: true,
      }),
    );
    await user.click(screen.getByRole("tab", { name: "Group sizes (dots)" }));
    await waitFor(() => expect(sigmaStub.graph?.order).toBe(groups.length + totalPoints(groups)));
    const graph = sigmaStub.graph;
    if (!graph) throw new Error("no graph loaded");
    expect(container).toHaveTextContent(`The dots only show how many people each group of at least ${k} has`);

    const points = graph.filterNodes((_, node) => node.kind === "point");
    expect(points).toHaveLength(totalPoints(groups));
    const labels = new Set(groups.map((g) => g.group));
    const palette = networkPalette(groups, (name) => document.documentElement.style.getPropertyValue(name));
    for (const key of points) {
      const node = graph.getNodeAttributes(key);
      expect(Object.keys(node).sort()).toEqual(BARE_NODE_ATTRIBUTES);
      expect(node.label).toBeNull();
      expect(key).toMatch(OPAQUE_POINT_KEY);
      // No tie, label or hover text for a single person: ties join groups only.
      expect(graph.degree(key)).toBe(0);
      expect(drawnNode(key).label).toBeNull();
      const drawn: string[] = [];
      const canvas: LabelCanvas = {
        font: "",
        fillStyle: "",
        measureText: () => ({ width: 0 }),
        fillRect: () => drawn.push("box"),
        fillText: (text) => drawn.push(text),
      };
      drawGroupHover(canvas, node, { labelSize: 12, labelFont: "sans-serif", labelWeight: "600" }, palette);
      expect(drawn).toEqual([]);
    }
    for (const tie of graph.edges()) {
      for (const end of graph.extremities(tie)) expect(labels.has(graph.getNodeAttribute(end, "label") ?? "")).toBe(true);
    }

    // Hovering a point shows nothing; searching for a point key finds nothing.
    const before = container.textContent;
    const [firstPoint = ""] = points;
    act(() => sigmaStub.handlers.enterNode?.({ node: firstPoint }));
    expect(screen.queryByText(/people · tied to/)).not.toBeInTheDocument();
    expect(container.textContent).toBe(before);
    await user.type(screen.getByRole("combobox", { name: "Search a group by label" }), `${firstPoint}{Enter}`);
    expect(screen.getByText("No group matches.")).toBeInTheDocument();
    expect(sigmaStub.gotoNode).not.toHaveBeenCalled();
    // No anonymous key reaches the page, apart from what was typed into the search box.
    expect(container.innerHTML.replace(`value="${firstPoint}"`, "")).not.toMatch(/point:\d/);
    expect(container.textContent ?? "").not.toMatch(LEAK_PATTERN);
    unmount();
  });

  it("network view, Overlap mode (WebGL): group discs only, group-level counts only", async () => {
    resetSigmaStub();
    resetLayerStub();
    applyThemeVariables();
    const user = userEvent.setup();
    const groups = data.tables.community_groups;
    const edges = data.tables.community_graph;
    const weeks = [...new Set(edges.map((row) => row.week))].sort();
    const { container, unmount } = render(
      createElement(CommunityGraph, {
        groups,
        edges,
        weeks,
        events: [],
        minGroupSize: minimumGroupSize(data),
        seed: data.run.seed,
        baseline: baselinePeriod(data),
        webgl: true,
      }),
    );
    await user.click(screen.getByRole("tab", { name: "Overlap" }));
    await waitFor(() => expect(sigmaStub.graph?.order).toBe(groups.length));
    const graph = sigmaStub.graph;
    if (!graph) throw new Error("no graph loaded");
    const labels = new Set(groups.map((g) => g.group));
    // Nothing per person: one disc per published group and no other node.
    for (const key of graph.nodes()) expect(labels.has(graph.getNodeAttribute(key, "label") ?? "")).toBe(true);
    // One contour layer, drawn from those group nodes.
    expect(layerStub.binds).toHaveLength(1);
    const [first = ""] = graph.nodes();
    act(() => sigmaStub.handlers.enterNode?.({ node: first }));
    expect(container.textContent ?? "").not.toMatch(LEAK_PATTERN);
    unmount();
  });
});
