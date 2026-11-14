/**
 * The analysis terms the explorer uses, each in one or two plain sentences, for readers who are
 * not data scientists. Shown on the Glossary and Hypotheses views and behind every "?" next to a
 * term; kept in one place so every view agrees.
 */
export interface GlossaryTerm {
  term: string;
  meaning: string;
}

export const GLOSSARY: readonly GlossaryTerm[] = [
  {
    term: "Hypothesis",
    meaning:
      "A claim about how email behaviour changed, written down before the result was computed, so the data could not shape the question.",
  },
  {
    term: "Held up / Held true",
    meaning: "The change is large enough to be unlikely by chance and survived every check listed below.",
  },
  {
    term: "p (Holm)",
    meaning:
      "How likely a change this large would be if nothing had really changed, adjusted because many hypotheses were tested at once. Below 0.05 counts as significant.",
  },
  {
    term: "95% interval",
    meaning: "The range the true change most likely lies in. If it includes 0, 'no change' is still a plausible answer.",
  },
  {
    term: "Effect (standardised)",
    meaning: "The size of the change measured against normal week-to-week variation, so different measures can be compared.",
  },
  {
    term: "Artifact check",
    meaning:
      "A test of whether a known quirk of the data (for example, who happens to be in the archive) explains the result instead of a real change in behaviour.",
  },
  {
    term: "Placebo",
    meaning: "The same test run on a calm period where nothing should change. If it also 'finds' a change, the method is picking up noise.",
  },
  {
    term: "Leave-one-out",
    meaning: "The test repeated leaving out each mailbox in turn, so that no single person can drive the result.",
  },
  {
    term: "Custodian",
    meaning: "A person whose mailbox is in the archive. Mail of everyone else is seen only when it reached a custodian.",
  },
  {
    term: "Group",
    meaning:
      "A cluster of people who mostly email each other, found in the baseline period. Only groups above a minimum size are shown, never a single person.",
  },
  {
    term: "Tie weight",
    meaning: "How much mail ran between two groups in a week; a thicker line means more mail.",
  },
  {
    term: "Re-identification",
    meaning: "The share of people an attacker with outside knowledge could single out in a released table. Lower is safer.",
  },
  {
    term: "Confidence",
    meaning:
      "How many robustness checks a supported result passed: high if all of them, moderate if all but one, low otherwise. A result that is not supported is always low.",
  },
  {
    term: "Robustness variants",
    meaning: "The same test rerun with another reasonable setting, for example monthly instead of weekly. A real change should survive them.",
  },
  {
    term: "Retention check",
    meaning:
      "The test repeated on mail that survives whatever an inbox kept, so that what people deleted or kept cannot create the change by itself.",
  },
  {
    term: "Change point",
    meaning: "The week in which a weekly series shifts the most, estimated from the data itself.",
  },
  {
    term: "Core and observed network",
    meaning:
      "Core: mail between custodians only, so every tie is seen from both mailboxes. Observed: every tie between internal people that the archive shows.",
  },
  {
    term: "Precision and recall",
    meaning:
      "Precision: of the merges a rule made, the share that were right. Recall: of the merges it should have made, the share it found.",
  },
  {
    term: "Pseudonym",
    meaning:
      "A code that replaces a name or address. It hides the name but not the pattern of who wrote to whom, so pseudonymised data is not anonymous.",
  },
  {
    term: "Minimum group size (k)",
    meaning:
      "The fewest people any published number may describe; anything smaller is hidden. This is the idea of k-anonymity: no published number singles out fewer than k people.",
  },
  {
    term: "Releases R0, R1, R2",
    meaning:
      "The three versions of the output that were attacked. R0: person-level data under pseudonyms, never published. R1: group totals only, the published release. R2: R1 with random noise added, a sketch rather than a formal guarantee.",
  },
  {
    term: "Attackers A1, A2, A3",
    meaning:
      "Three simulated attackers. A1: an outsider holding the public archive. A2: an insider who knows a few people. A3: an insider who knows every mailbox owner, since the public archive names them all.",
  },
  {
    term: "Anonymity set and unique share",
    meaning:
      "Anonymity set: how many people look the same as a given person in a release. Unique share: the share of people who look like nobody else, the easiest to single out.",
  },
];

/** The plain meaning of one term; an unknown term is a programming error, so it throws. */
export function glossaryMeaning(term: string): string {
  const entry = GLOSSARY.find((item) => item.term === term);
  if (!entry) throw new Error(`No glossary entry for "${term}"`);
  return entry.meaning;
}
