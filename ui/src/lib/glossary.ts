/**
 * The analysis terms the explorer uses, each in one or two plain sentences, for readers who are
 * not data scientists. Shown on the Hypotheses view; kept in one place so every view agrees.
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
      "A test of whether a known artifact of the data or the method (for example, who happens to be in the archive, or groups fixed on the baseline going stale) explains the result instead of a real change in behaviour.",
  },
  {
    term: "Placebo",
    meaning:
      "The same test run on a calm period where nothing should change. If it also 'finds' a change, the method is picking up something other than the event, such as noise or a drift of its own.",
  },
  {
    term: "Leave-one-out",
    meaning: "The test repeated leaving out each mailbox in turn, to check that no single person drives the result.",
  },
  {
    term: "Custodian",
    meaning: "A person whose mailbox is in the archive. Mail of everyone else is seen only when it reached a custodian.",
  },
  {
    term: "Group",
    meaning:
      "A cluster of people who mostly email each other, found in the baseline period. Only groups of at least a minimum size are shown, never a single person.",
  },
  {
    term: "Outside the baseline groups",
    meaning:
      "People with no tie in the baseline period (such as people who first appear later) or in clusters below the minimum size. They are counted together but are not a group, so the network does not draw them.",
  },
  {
    term: "Tie weight",
    meaning: "How much mail ran between two groups in a week; a thicker line means more mail.",
  },
  {
    term: "Re-identification",
    meaning: "The share of people an attacker with outside knowledge could single out in a released table. Lower is safer.",
  },
];
