/**
 * The analysis terms the explorer uses, each in one or two plain sentences, for readers who are
 * not data scientists. Shown on the Glossary and Hypotheses views and behind every "?" next to a
 * term; kept in one place so every view agrees.
 */
interface GlossaryTerm {
  term: string;
  meaning: string;
}

export const GLOSSARY: readonly GlossaryTerm[] = [
  {
    term: "Hypothesis",
    meaning:
      "A claim about how email communication, or who took part in it, changed, written down before its own result was computed. When it was written down matters: see Pre-registered, Stated before computed and Post hoc.",
  },
  {
    term: "Pre-registered",
    meaning: "Stated before any real data was analysed, so no result could shape the question. Only the first hypotheses are.",
  },
  {
    term: "Stated before computed, after earlier results",
    meaning:
      "Written down and committed before its own result was computed, but after the results of earlier hypotheses were known. Those results may have shaped the question, so it weighs less than a pre-registered one.",
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
      "A test of whether a known artifact of the data or the method (for example, who happens to be in the archive, or groups fixed on the baseline going stale) explains the result instead of a real change in behaviour.",
  },
  {
    term: "Placebo",
    meaning:
      "The same test run on a calm period before the crisis, where nothing should change. It passes when that period shows no change in the predicted direction. A calm-period change against the prediction therefore still passes; where the calm period already shows the crisis change, the result says so.",
  },
  {
    term: "Leave-one-out",
    meaning:
      "The test repeated leaving out each mailbox in turn. It is stable only if the result keeps the predicted direction every time, so 'unstable' covers both a result that single mailboxes carry and one that is not in the predicted direction to begin with.",
  },
  {
    term: "Custodian",
    meaning: "A person whose mailbox is in the archive. Mail of everyone else is seen only when it reached a custodian.",
  },
  {
    term: "Departure and record end",
    meaning:
      "A custodian departs when they stop sending for months while their own mailbox keeps receiving mail: they went quiet, but the record still covers them. If the incoming mail stops too, it is a record end: the archive stopped collecting that mailbox, which says nothing about whether the person left.",
  },
  {
    term: "Post hoc",
    meaning:
      "Stated after every other result was known, though still before its own result was computed. Such a question may have been prompted by what was already seen, so it carries the least weight.",
  },
  {
    term: "Group",
    meaning:
      "A cluster of people who mostly email each other, found in the baseline period. Only groups of at least a minimum size are shown, never a single person.",
  },
  {
    term: "Outside the baseline groups",
    meaning:
      "Internal people without a baseline group: no tie in the baseline period, or in a cluster below the minimum size. They are counted together but are not a group, so the network does not draw them.",
  },
  {
    term: "Tie weight",
    meaning: "How much mail ran between two groups in a week; a thicker line means more mail.",
  },
  {
    term: "Re-identification",
    meaning:
      "The share of people an attacker with outside knowledge correctly singles out. It was measured on person-level data only (R0), which is never published.",
  },
  {
    term: "Confidence",
    meaning:
      "How many robustness checks a supported result passed: high if all of them, moderate if all but one, low otherwise. A result that is not supported is always low, and a check against a known artifact that fails or cannot run caps it at low whatever else passed.",
  },
  {
    term: "Robustness variants",
    meaning: "The same test rerun with another reasonable setting, for example monthly instead of weekly. A real change should survive them.",
  },
  {
    term: "Retention check",
    meaning:
      "The test repeated on mail that depends less on what one inbox kept, so that what people deleted or kept is less able to create the change by itself.",
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
      "The fewest people any published number may describe; anything smaller is hidden. A minimum group size, in the spirit of k-anonymity, not a proof of it.",
  },
  {
    term: "Releases R0, R1, R2",
    meaning:
      "Three versions of the output. R0: person-level data under pseudonyms, never published, and the only one the attacks measure. R1: group totals only, the published release. R2: R1 with random noise added, a sketch rather than a formal guarantee. R1 and R2 hold no person-level record, so the person-level attacks have nothing to match there: their 0 is by construction, not a measurement.",
  },
  {
    term: "Attackers A1, A2, A3",
    meaning:
      "Three simulated attackers. A1: an outsider holding the public archive. A2: an insider who knows a few people. A3: anyone holding the public archive, which names every mailbox owner.",
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
