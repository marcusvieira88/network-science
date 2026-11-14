import { describe, expect, it } from "vitest";

import type { CommunityEdgeRow, CommunityGroupRow } from "@/lib/data";
import { publishedTies } from "@/lib/network";
import {
  EDGE_MAX_WIDTH,
  EDGE_MIN_WIDTH,
  type LabelCanvas,
  type NetworkNode,
  type NetworkPalette,
  POINT_RADIUS,
  edgeAppearance,
  edgeWidth,
  findGroup,
  focusOn,
  drawGroupHover,
  groupKey,
  groupNodeRadius,
  layoutPositions,
  legendSizes,
  legendWeights,
  networkGraph,
  networkPalette,
  nodeAppearance,
  pointKey,
} from "@/lib/sigmaNetwork";

const groups: CommunityGroupRow[] = [
  { group: "G02", n_persons: 9 },
  { group: "G01", n_persons: 16 },
  { group: "G03", n_persons: 5 },
];

function edge(week: string, src: string, dst: string, weight: number | null): CommunityEdgeRow {
  return { week, src_group: src, dst_group: dst, weight, n_messages: weight === null ? null : 10 };
}

const edges: CommunityEdgeRow[] = [
  edge("2000-01-03", "G01", "G02", 6),
  edge("2000-01-03", "G02", "G01", 2),
  edge("2000-01-03", "G01", "G01", 7),
  edge("2000-01-10", "G02", "G03", 1),
  edge("2000-01-10", "G01", "G09", 3),
];

const palette: NetworkPalette = {
  groups: new Map([
    ["G01", "#000001"],
    ["G02", "#000002"],
    ["G03", "#000003"],
  ]),
  tie: "#00000a8c",
  point: "#00000b",
  dimmed: "#00000c",
  label: "#00000d",
  hoverBackground: "#00000e",
};

const positions = new Map([
  ["G01", { x: 0, y: 0 }],
  ["G02", { x: 10, y: 0 }],
  ["G03", { x: 0, y: 10 }],
]);

function graphFor(week: string, points: ReadonlyMap<string, [number, number][]> | null = null) {
  const ties = publishedTies(edges, week, positions.keys());
  return networkGraph({ groups, positions, ties, maxTie: 8, palette, points });
}

describe("sizes", () => {
  it("makes disc area proportional to group size", () => {
    expect(groupNodeRadius(16)).toBe(4);
    expect(groupNodeRadius(9)).toBe(3);
    // Four times the people, twice the radius, four times the area.
    expect(groupNodeRadius(36) / groupNodeRadius(9)).toBe(2);
  });

  it("scales tie width with the share of the heaviest weekly tie, clamped", () => {
    expect(edgeWidth(0, 8)).toBe(EDGE_MIN_WIDTH);
    expect(edgeWidth(8, 8)).toBe(EDGE_MAX_WIDTH);
    expect(edgeWidth(4, 8)).toBeCloseTo((EDGE_MIN_WIDTH + EDGE_MAX_WIDTH) / 2, 12);
    expect(edgeWidth(16, 8)).toBe(EDGE_MAX_WIDTH);
  });
});

describe("networkPalette", () => {
  it("gives each group its chart slot in label order and converts the theme tokens to hex", () => {
    const theme: Record<string, string> = {
      "--chart-1": "#3987e5",
      "--chart-2": "#d95926",
      "--chart-other": "#6b6b66",
      "--muted-foreground": "0 100% 50%",
      "--foreground": "120 100% 25%",
      "--muted": "#202022",
      "--popover": "#101010",
    };
    const read = (name: string): string => theme[name] ?? "";
    const result = networkPalette([{ group: "other", n_persons: 7 }, ...groups.slice(0, 2)], read);
    expect([...result.groups]).toEqual([
      ["G01", "#3987e5"],
      ["G02", "#d95926"],
      ["other", "#6b6b66"],
    ]);
    expect(result.tie).toBe("#ff00008c");
    expect(result.point).toBe("#008000");
    expect(result.label).toBe("#008000");
    expect(result.dimmed).toBe("#202022");
    expect(result.hoverBackground).toBe("#101010");
  });

  it("fails loudly when a theme variable is missing", () => {
    expect(() => networkPalette(groups, () => "")).toThrow("--chart-1");
  });
});

describe("layoutPositions", () => {
  const layout = layoutPositions(groups, edges);
  const distance = (a: string, b: string): number => {
    const p = layout.get(a);
    const q = layout.get(b);
    if (!p || !q) throw new Error("missing group");
    return Math.hypot(p.x - q.x, p.y - q.y);
  };

  it("places every published group and only those", () => {
    expect([...layout.keys()]).toEqual(["G01", "G02", "G03"]);
  });

  it("is deterministic and independent of row order", () => {
    expect(layoutPositions([...groups].reverse(), [...edges].reverse())).toEqual(layout);
  });

  it("keeps discs apart and pulls the heavily tied pair closest", () => {
    const radius = new Map(groups.map((g) => [g.group, groupNodeRadius(g.n_persons)]));
    for (const [a, b] of [
      ["G01", "G02"],
      ["G01", "G03"],
      ["G02", "G03"],
    ] as const) {
      expect(distance(a, b)).toBeGreaterThanOrEqual((radius.get(a) ?? 0) + (radius.get(b) ?? 0));
    }
    // G01–G02 carry 8 over all weeks, G02–G03 carry 1, G01–G03 nothing.
    expect(distance("G01", "G02")).toBeLessThan(distance("G01", "G03"));
  });
});

describe("networkGraph", () => {
  it("draws one disc per group, sized and coloured, labelled with the group only", () => {
    const graph = graphFor("2000-01-03");
    expect(graph.nodes()).toEqual(["group:G01", "group:G02", "group:G03"]);
    expect(graph.getNodeAttributes("group:G01")).toEqual({
      x: 0,
      y: 0,
      size: 4,
      color: "#000001",
      label: "G01",
      kind: "group",
      zIndex: 0,
    });
  });

  it("draws the week's ties between distinct published groups, width by weight", () => {
    const first = graphFor("2000-01-03");
    expect(first.size).toBe(1);
    const [tie] = first.edges();
    if (!tie) throw new Error("no tie");
    expect(first.extremities(tie)).toEqual(["group:G01", "group:G02"]);
    expect(first.getEdgeAttributes(tie)).toEqual({ size: EDGE_MAX_WIDTH, color: "#00000a8c", weight: 8 });
    // The tie to G09, which is not published, is dropped.
    const second = graphFor("2000-01-10");
    expect(second.edges().map((key) => second.extremities(key))).toEqual([["group:G02", "group:G03"]]);
    expect(graphFor("2000-01-17").size).toBe(0);
  });

  it("in the Individuals mode adds bare anonymous points inside a translucent disc, and no tie to them", () => {
    const points = new Map<string, [number, number][]>([
      ["G01", [[1, 1], [-1, 0]]],
      ["G02", [[0, 2]]],
      ["G03", []],
    ]);
    const graph = graphFor("2000-01-03", points);
    expect(graph.order).toBe(3 + 3);
    expect(graph.getNodeAttribute("group:G01", "color")).toBe("#00000140");
    expect(graph.getNodeAttributes(pointKey(0, 0))).toEqual({
      x: 1,
      y: 1,
      size: POINT_RADIUS,
      color: "#00000b",
      label: null,
      kind: "point",
      zIndex: 1,
    });
    expect(graph.getNodeAttributes(pointKey(1, 0))).toMatchObject({ x: 10, y: 2 });
    for (const key of graph.filterNodes((_, node) => node.kind === "point")) expect(graph.degree(key)).toBe(0);
    expect(graph.size).toBe(1);
  });
});

describe("focus", () => {
  const graph = graphFor("2000-01-03", new Map([["G03", [[0, 0]]]]));

  it("focuses groups only, with the groups they are tied to this week", () => {
    expect(focusOn(graph, null)).toBeNull();
    expect(focusOn(graph, "group:G99")).toBeNull();
    expect(focusOn(graph, pointKey(2, 0))).toBeNull();
    expect(focusOn(graph, "group:G01")).toEqual({ key: "group:G01", neighbours: new Set(["group:G02"]) });
  });

  it("highlights the focused group, keeps its tied groups and dims the rest without label", () => {
    const focus = focusOn(graph, "group:G01");
    const node = (key: string): NetworkNode => graph.getNodeAttributes(key);
    expect(nodeAppearance("group:G01", node("group:G01"), focus, "#dim")).toMatchObject({ highlighted: true, label: "G01" });
    expect(nodeAppearance("group:G02", node("group:G02"), focus, "#dim")).toEqual(node("group:G02"));
    expect(nodeAppearance("group:G03", node("group:G03"), focus, "#dim")).toMatchObject({ color: "#dim", label: null });
    expect(nodeAppearance("group:G03", node("group:G03"), null, "#dim")).toEqual(node("group:G03"));
    expect(nodeAppearance(pointKey(2, 0), node(pointKey(2, 0)), focus, "#dim").label).toBeNull();
  });

  it("hides the ties that do not touch the focused group", () => {
    const tie = { size: 1, color: "#000000", weight: 3 };
    const focus = focusOn(graph, "group:G03");
    expect(edgeAppearance(tie, ["group:G01", "group:G02"], focus)).toMatchObject({ hidden: true });
    expect(edgeAppearance(tie, ["group:G02", "group:G03"], focus)).toEqual(tie);
    expect(edgeAppearance(tie, ["group:G01", "group:G02"], null)).toEqual(tie);
  });
});

describe("findGroup", () => {
  const labels = ["G01", "G10", "other"];

  it("prefers an exact match, ignoring case and spaces, else the first label containing the query", () => {
    expect(findGroup(labels, " g10 ")).toBe("G10");
    expect(findGroup(labels, "1")).toBe("G01");
    expect(findGroup(labels, "OTH")).toBe("other");
  });

  it("finds nothing for an empty or unmatched query, and never a point key", () => {
    expect(findGroup(labels, "  ")).toBeNull();
    expect(findGroup(labels, "G7")).toBeNull();
    expect(findGroup(labels, "point:0-0")).toBeNull();
  });
});

describe("legend", () => {
  it("shows the smallest and largest group with area proportional to people", () => {
    expect(legendSizes(groups, 10)).toEqual([
      { people: 5, radius: 10 * Math.sqrt(5 / 16) },
      { people: 16, radius: 10 },
    ]);
    expect(legendSizes([{ group: "G01", n_persons: 8 }], 10)).toEqual([{ people: 8, radius: 10 }]);
    expect(legendSizes([], 10)).toEqual([]);
  });

  it("shows half the heaviest tie and the heaviest, in proportion to the drawn width", () => {
    const [half, full] = legendWeights(8, 6);
    expect(full).toEqual({ weight: 8, width: 6 });
    expect(half?.weight).toBe(4);
    expect(half?.width).toBeCloseTo((6 * (EDGE_MIN_WIDTH + EDGE_MAX_WIDTH)) / 2 / EDGE_MAX_WIDTH, 12);
  });
});

describe("drawGroupHover", () => {
  function recordingContext(): { calls: string[]; context: LabelCanvas } {
    const calls: string[] = [];
    const context: LabelCanvas = {
      font: "",
      fillStyle: "",
      measureText: (text) => ({ width: text.length * 6 }),
      fillRect: () => calls.push("box"),
      fillText: (text) => calls.push(`text:${text}`),
    };
    return { calls, context };
  }
  const font = { labelSize: 12, labelFont: "sans-serif", labelWeight: "600" };

  it("draws the group label in a box", () => {
    const { calls, context } = recordingContext();
    drawGroupHover(context, { x: 0, y: 0, size: 4, label: "G01" }, font, palette);
    expect(calls).toEqual(["box", "text:G01"]);
    expect(context.fillStyle).toBe(palette.label);
  });

  it("draws nothing for a node without a label, such as an anonymous point", () => {
    const { calls, context } = recordingContext();
    drawGroupHover(context, { x: 0, y: 0, size: 0.3, label: null }, font, palette);
    expect(calls).toEqual([]);
  });

  it("keys groups by label and points by position in the drawing order only", () => {
    expect(groupKey("G01")).toBe("group:G01");
    expect(pointKey(2, 7)).toBe("point:2-7");
  });
});
