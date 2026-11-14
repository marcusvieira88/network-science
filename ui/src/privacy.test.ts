import { render } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it } from "vitest";

import { View } from "@/App";
import { TABLE_COLUMNS } from "@/lib/data";
import { LEAK_PATTERN, PERSON_COUNT_COLUMNS, identifierCount, minimumGroupSize, smallPersonCounts } from "@/lib/privacy";
import { VIEWS } from "@/lib/views";
import { rawSample, sampleData } from "@/test/sample";

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
    const { container, unmount } = render(createElement(View, { view, data }));
    const text = container.textContent ?? "";
    expect(text).not.toMatch(LEAK_PATTERN);
    expect(container.querySelectorAll("[data-person], [data-pid]")).toHaveLength(0);
    // The network draws one node per published group and nothing finer.
    const nodes = container.querySelectorAll("[data-testid=group-node]");
    if (view === "network") expect(nodes).toHaveLength(data.tables.community_groups.length);
    else expect(nodes).toHaveLength(0);
    unmount();
  });
});
