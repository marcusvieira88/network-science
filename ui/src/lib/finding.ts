/**
 * Why there is no behavioural headline, worded from `supported`, `confidence` and the artifact
 * checks (the same rule as headline_statement in src/enron_case/report/render.py). A hypothesis
 * that is not supported is never said to have passed anything. The finding about the record is
 * stated next to it (lib/record.ts), so this text never says a bare "no finding".
 */
import type { ArtifactCheckRow, HypothesisRow } from "@/lib/data";
import { joinList } from "@/lib/format";

export interface NoFindingText {
  title: string;
  body: string[];
}

function names(rows: HypothesisRow[]): string {
  return joinList(rows.map((row) => row.hypothesis));
}

function its(rows: HypothesisRow[]): string {
  return rows.length === 1 ? "its check" : "their checks";
}

export function noFindingExplanation(hypotheses: HypothesisRow[], checks: ArtifactCheckRow[]): NoFindingText {
  const supported = hypotheses.filter((row) => row.supported === "yes");
  if (supported.length === 0) {
    return {
      title: "No hypothesis supported",
      body: [
        "None of the pre-registered hypotheses H1–H4 shows both a significant change after correction for " +
          "multiple testing and an effect interval on the hypothesised side.",
        "This is reported as a result, not hidden: see the Hypotheses view for every outcome.",
      ],
    };
  }
  const result = (row: HypothesisRow) => checks.find((check) => check.hypothesis === row.hypothesis)?.passes;
  const failed = supported.filter((row) => result(row) === false);
  const notRun = supported.filter((row) => result(row) === null);
  const otherwise = supported.filter((row) => !failed.includes(row) && !notRun.includes(row));
  const body: string[] = [];
  if (failed.length) {
    body.push(
      `${names(failed)} passed the statistical tests but failed ${its(failed)} against a known artifact of the data, ` +
        "so no behavioural finding is claimed.",
    );
  }
  if (notRun.length) {
    body.push(
      `${names(notRun)} passed the statistical tests but ${its(notRun)} against a known artifact could not run, ` +
        "so the artifact is not ruled out and no behavioural finding is claimed.",
    );
  }
  for (const row of otherwise) {
    body.push(
      `${row.hypothesis} is supported but fails at least one robustness check (${row.confidence} confidence), ` +
        "so it is not claimed as a behavioural finding.",
    );
  }
  body.push("See the Hypotheses view for every outcome and the artifact checks.");
  return { title: "No behavioural finding claimed", body };
}
