# Exploratory hypotheses E1–E21 (= H5–H25) and question O1 (= H26)

> **Numbering (added later).** These hypotheses are now numbered as one list with the
> pre-registered ones: **E*n* is H*n*+4** (E1 = H5 … E12 = H16 … E20 = H24, the post-hoc
> E21 = H25, and the post-hoc question **O1 = H26** at the end of this file). This file keeps
> the original numbers because it is the dated record of when each was stated; the code, the
> release tables, the report and the UI use H5–H26.
>
> **Timing labels (added 2026-11-14).** Every surface uses three labels: "pre-registered" for
> H1–H4 (before any real data), "stated before computed, after earlier results" for H5–H24
> (this file calls them exploratory), and "post hoc" for H25 and H26. Notes in italics below
> mark what was added or corrected after a section was first written; the original text stays.

**Status: stated and committed before any of them was computed.** This is a second, exploratory
family, added after the pre-registered family H1–H4 (`docs/hypotheses.md`) produced no finding.
It is reported as exploratory. Its design answers the two artifacts that explained H2 and H3:

- **Composition** (who is in the data changes over time): every hypothesis compares each
  custodian with themselves. The statistic is a paired, within-person difference.
- **Volume and retention** (how much mail each person kept differs by period): every measure is
  a ratio or a rate per active week, never a raw count.
- **Hindsight in choosing the change point**: windows are fixed by public dates, not searched for
  in the data.

## Windows

| Name | Dates | Role |
|------|-------|------|
| Crisis (W1) | 2001-08-14 to 2001-12-02 | CEO resignation announced to Chapter 11 filing |
| Reference (W0) | 2000-08-14 to 2000-12-02 | same calendar weeks one year earlier (controls for season) |
| Placebo after (P1) | 2001-01-01 to 2001-04-30 | before any public crisis event |
| Placebo before (P0) | 2000-01-01 to 2000-04-30 | same calendar weeks one year earlier |

Local time is Houston (UTC−6, UTC−5 from April to October); timestamps are hour-resolution.
*(Clarified 2026-11-14: the corpus's `Date` headers carry Pacific offsets, which is what "Known
limits" below refers to; the pipeline converts them to UTC and measures hours in Houston local
time.)*

## Units

Custodians (the collected mailboxes): internal persons with `is_custodian`. A custodian enters a
comparison only with at least 20 messages (sent or received, as the hypothesis needs) in each of
the two windows compared.

## Hypotheses

Sent-side measures use each custodian's sent messages (one row per message, `msg_pid`), all
recipients, including mailings excluded from the network. Received-side measures use messages
in which the custodian is a recipient.

| ID | Measure per custodian and window | Direction in crisis | Reasoning |
|----|----------------------------------|---------------------|-----------|
| E1 | share of sent messages sent outside 07:00–19:00 local on weekdays | up | crisis work spills into evenings |
| E2 | share of sent messages sent on Saturday or Sunday | up | crisis work spills into weekends |
| E3 | share of sent messages with at least one Bcc recipient | up | more discreet copying |
| E4 | share of sent messages with at least one Cc recipient | up | more copying for the record |
| E5 | mean number of recipients per sent message | up | more one-to-many communication |
| E6 | share of sent messages with five or more recipients | up | more one-to-many communication |
| E7 | distinct internal contacts per active week (sent) | down | networks contract under stress |
| E8 | sent messages per active week | up | activity surge |
| E9 | share of sent messages that go to the custodian's three most frequent recipients in that window | up | attention narrows to a few people |
| E10 | share of received messages that came with 20 or more recipients | up | more broadcast communication from the organization |

A week is active for a custodian if it holds at least one of their messages of the kind measured.

## Test and decision rule

For each hypothesis, the paired difference d = measure(W1) − measure(W0) per custodian.

- **Statistic**: median of d; 95% bootstrap interval over custodians (seeded, 2,000 draws).
- **p-value**: Wilcoxon signed-rank test on d, two-sided; Holm correction across E1–E10. *(Superseded when the second family was stated: Holm runs across E1–E20.)*
- **Placebo**: the same difference for P1 − P0, before any crisis event.
- **Leave one out**: the median of d recomputed without each custodian in turn.

**Confident** only if all hold:

1. Holm-adjusted p < 0.05;
2. the interval lies wholly on the hypothesised side of zero;
3. placebo: its interval includes zero, or its median is less than half the crisis median on the
   same side (a pre-existing trend would otherwise explain the change). *(Reading note,
   2026-11-14; the rule is unchanged: "passes" means no change in the predicted direction before
   the crisis. A placebo that moves the other way passes even when it is as large as the crisis
   change (H21), and so does one whose interval touches zero while its median exceeds the crisis
   median (H25); read `placebo_median` next to `placebo_passes`.)*
4. every leave-one-out median has the hypothesised sign.

Otherwise the outcome is *not supported* or *inconclusive*, and is reported as such. All ten
outcomes are published, whatever they are.

## Known limits

- Custodians are mostly senior staff; results describe them, not the whole organization.
- Timestamps were normalised to Pacific time in the corpus and are hour-resolution; E1 and E2
  inherit that resolution.
- E3 depends on Bcc being visible, which it is only in the sender's own copy; sent-side measures
  use exactly those copies.
- This family is exploratory. A confident result here is a lead for confirmation on other data,
  not a pre-registered finding.
- *(Added after the data-science review.)* The placebo windows (January–April) hold less mail
  than the crisis and reference windows, so fewer custodians meet the minimum of 20 messages:
  in the last committed real run about half as many (`placebo_custodians` against `custodians`
  in `release/exploratory.csv`, e.g. 15 against 32 for the sent-side measures). The placebo
  therefore has lower power than the crisis comparison, and its custodians are a subset that
  may differ from those compared in the crisis. A passing placebo (interval covering zero) does
  not exclude a pre-existing trend; it only fails to detect one.

---

# Second exploratory family E11–E20

**Status: stated and committed before any of them was computed, after E1–E10 were computed.**
E1–E10 produced no confident result. They showed that hour-of-day measures are unreliable in this
corpus (the 2000 timestamps are shifted by several hours; *superseded, as built: the hour
convention differs between the two years, and which year is the shifted one is not established,
see the timestamp caveat below*) and that Bcc carries no information
(every Bcc line repeats the Cc line). This family avoids both. It uses the same windows, units,
minimum of 20 messages, test and decision rule as E1–E10, with one change: **Holm's correction runs
across all twenty exploratory hypotheses, E1–E20**, so adding hypotheses makes each one harder to
pass, not easier.

E11 is not independent of what was seen: it is derived from the unexpected E10 result (custodians
received a smaller share of broadcast mail in the crisis). It is marked as derived and must be
read as a consistency check on a lead, not as a fresh test.

| ID | Measure per custodian and window | Direction in crisis | Reasoning |
|----|----------------------------------|---------------------|-----------|
| E11 | share of sent messages with exactly one recipient | up | *derived from E10*: more direct, one-to-one mail |
| E12 | share of the custodian's sent-to contacts who also sent to the custodian in the same window | up | ties become mutual under stress |
| E13 | share of sent messages addressed to at least one other custodian | up | senior staff turn to each other |
| E14 | share of received messages sent by another custodian | up | the same, seen from the inbox |
| E15 | share of the window's distinct contacts not contacted in the 26 weeks before the window | down | less reaching out to new people |
| E16 | distinct senders per active week (received) | up | more people reach out to the custodian |
| E17 | share of received messages that come from the custodian's three most frequent senders | up | attention concentrates on a few senders |
| E18 | share of received messages from external senders | down | outsiders drop away |
| E19 | share of weeks in the window with at least one sent message | up | more consistently active |
| E20 | share of sent messages that include a non-person recipient (list, role or system address) | down | less routine, list-based traffic |

Received-side measures (E14, E16, E17, E18) use messages in which the custodian is a recipient;
the others use sent messages. E15 looks back 26 weeks before each window's start.

---

## Implementation notes (after code review, before any rerun)

A code review of the implementation found measurement details that did not match the text above;
they were fixed so the code measures what was stated:

- **E1** is the share among *weekday* messages (weekend volume no longer moves it). E1 remains
  invalid for the timestamp reason above.
- **Local time** uses the actual US daylight-saving switch dates, not April–October by month.
- **E19** counts only full Monday-to-Sunday weeks inside each window, in numerator and
  denominator, so partial edge weeks cannot lower it.
- A placebo with **no change at all** (every difference zero) now counts as passing; before, it
  was treated as undefined and failed.
- **Caveats** are recorded in the results and block a "confident" outcome: E1 (timestamp shift),
  E3 (Bcc repeats Cc), E15 (the 26-week look-back depends on how much older mail was kept).
- Parameters (minimum messages, bootstrap draws, alpha) are `Config` fields.

## Checks added after results were seen

**Written after the results of E1–E20 were known, and says so.** Two checks were added to this
family after its results, so they are post hoc. They can only stop a hypothesis from being held
true; neither can make one confident.

- **Mail-volume equalisation** (870f808, after E12 came out confident on the first computation).
  For every hypothesis not rejected and without a caveat, each custodian's sent and received
  messages in both windows are subsampled to the smaller window's count, the measure is
  recomputed and the paired test rerun. It is reported next to the outcome, not part of the
  rule. Because it is run only for the hypotheses that survived, its p has no Holm rank of its
  own: `equalised_p_holm` multiplies it by the family size (20; 21 since H25 was added) and caps
  it at 1, which is Holm's
  multiplier for the family's smallest p and conservative at every other rank. Read the
  equalised result against `equalised_p_holm`, not the unadjusted `equalised_p`.
- **Retention check** (2703cba, after the data-science review, run with the
  `/data-scientist-review` skill). Inbox retention differs by person and period, so a contact's
  message can be missing because the custodian's inbox lost it. E12 is recomputed counting only
  contacts who are themselves custodians, whose messages can survive in their own sent folders
  as well as in the receiving inbox, so the measure depends less on what one inbox kept (it is
  not independent of retention: the sender's own sent-folder retention still moves it; wording
  corrected in the pre-delivery review); crisis against reference with the same placebo. It passes
  only if the crisis interval lies on the hypothesised side over at least k custodians and the
  placebo passes; a hypothesis that fails it is at most inconclusive. E12 fails it: among
  custodian-to-custodian contacts the change is not established, and the same subset rises
  before the crisis. No hypothesis in E1–E20 is held true. The check is defined for E12 only.
  The same threat applies to the other received-side measures (E10, E14, E16–E18), but none of
  them was held true (in the last committed real run E16 is inconclusive and the others are not
  supported), and a failed check can only cap an outcome at inconclusive, so it could not change
  theirs. A future run in which one of them is held true needs its own retention check first.

- **Timestamp caveat on E2 (= H6)** (pre-delivery review, after every result, so post hoc). The
  hour convention of `Date` changes between the reference and crisis windows (see the record
  profile below). A shift of several hours moves messages across midnight, so the weekend share
  crosses the same change as E1. E2 now carries a caveat that blocks a confident outcome, as E1's
  does. It changes no outcome: E2 is not supported. E1's caveat no longer says which year is
  shifted, since that is not established.

E12 measures whether a contact sent the custodian anything in the same window, not whether they
replied: headers carry no thread.

---

# Post-hoc hypothesis E21 (= H25): a replication test of prior work

**Status: post hoc. Stated and committed on 2026-11-14, after every result of H1–H24 was known
and after prior work on the corpus was read, and before E21 was computed.** It is not a fresh
prediction of ours: it tests, at the scope our design can defend, the best-known published result
on how this network changed in 2001. Diesner, Frantz & Carley (2005) compare monthly networks
among Enron employees and report that during the crisis the network became denser and more
connected. *(Attribution corrected 2026-11-14, after checking both papers; the hypothesis and
its rule are unchanged. The denser, more connected crisis network, density 0.018 in October 2000
against 0.031 in October 2001, is reported by Diesner & Carley (2005), who compare those two
single months. Diesner, Frantz & Carley (2005) analyse monthly networks and report that
employee-level density does not follow the scandal, while previously disconnected people begin
to communicate. E21 tests the Diesner & Carley result.)* Our pre-registered H1–H4 do not test density, and the network-level density of the
observed or core network moves with how much mail was kept, so it cannot be read as behaviour.

| ID | Measure per custodian and window | Direction in crisis | Reasoning |
|----|----------------------------------|---------------------|-----------|
| E21 | share of the other custodians with whom the custodian exchanged at least one message, in either direction, in the window (core ego density; any surviving copy counts) | up | Diesner & Carley (2005): denser, more connected communication in the crisis *(attribution corrected, see above)* |

- **Units, windows, test and rule**: exactly as E1–E20 (crisis against the same weeks a year
  earlier; pre-crisis placebo; leave-one-out; Wilcoxon signed-rank; median with a bootstrap
  interval). A custodian enters with at least 20 sent **and** 20 received messages in each window
  (n is the smaller of the two counts). The denominator is the number of custodians minus one.
- **Multiple testing**: Holm's correction runs across E1–E21 (H5–H25, twenty-one hypotheses), so
  adding E21 makes every hypothesis harder to pass, not easier.
- **Retention check**: the same measure counting only the custodians this custodian *sent* to,
  which no inbox can move. *(Corrected in the pre-delivery review, after the result: a message
  to another custodian can also survive only in that custodian's inbox, and the sender's own
  sent-folder retention moves it, so the measure depends less on inbox retention, not on none.
  The rule is unchanged.)* It must pass as the E12 check does (crisis interval on the
  hypothesised side over at least k custodians, and the placebo passes), or E21 is at most
  inconclusive.
- **Volume equalisation** is reported next to it, as for the others.
- **Known threat stated before computing**: a monthly profile of custodians' sent mail (published
  as `release/record_profile.csv`) shows that the hour-of-day convention of the `Date` header
  changes between May and August 2001, consistent with a change of mail system. The crisis
  window lies after that change and the reference window before it; the placebo windows both lie
  before it. Any E21 outcome, like every E1–E20 outcome, compares two recording regimes, and
  the placebo cannot detect an artifact of that change. A confident E21 would therefore be
  reported as a lead, not as a finding.

## E21 result (written after it was computed)

E21 (H25) is **not supported**: the median within-custodian change is small, its interval touches
zero, its Holm-adjusted p across the twenty-one is above 0.05, and the pre-crisis placebo shows a
change at least as large. Its retention check did not run, because the outcome was not supported
(a check can only cap an outcome). The published densification is not established when each
custodian is compared with themselves a year earlier. The numbers are not repeated here, so they
cannot go stale: `release/exploratory.csv`, row H25, and the report's H5–H25 table, both
generated by the pipeline. *(Numbers typed here by hand earlier were replaced by this pointer in
the pre-delivery review.)*

The record profile stated as a known threat above is published as `release/record_profile.csv`
and summarised in the report ("What changed in the record during the crisis year"): the
after-hours share of the custodians' weekday sent mail lies far lower in every crisis month than
in any reference month, and falls step by step from late spring to late summer 2001. The placebo
windows (January–April 2000 and 2001) both lie
before that change, so a passing placebo cannot clear any H5–H25 result of it.

---

# Post-hoc question O1 (= H26): did custodians leave during the crisis?

**Status: post hoc. Stated and committed on 2026-11-14, after every result of H1–H25 and the
record profile were known, and before anything below was computed.** No departure, exit or
silence of any custodian has been counted before this commit. What was already seen: the
published tables (`release/*.csv`), in particular `record_profile.csv`, whose monthly
`custodians_sending` counts mix entries, exits and coverage and say nothing about departures.

The question comes from the brief: *one finding about how the organization changed during
2001*. Every behavioural hypothesis failed, so this asks about **structure**: did people leave
the organization's core during the crisis? The only people whose activity the record follows
from both sides are the custodians (their own mailbox holds what they sent and received), so
the question is asked about them.

## Why this design and not another

- **Communities fitted per period and tracked over time** (births, deaths, merges, splits) were
  considered and rejected. The observed network is the union of about 150 mailboxes' ego
  networks: a community "dies" when the mailboxes that saw it stop holding mail or when inbox
  retention changes, and received mail kept grows up to about 3.5× in the crisis (the largest
  crisis month against the largest reference month; about five times October on October). Its shape
  follows coverage, not the organization, and a placebo cannot separate the two.
- **Core concentration** (share of internal mail through the top-k senders) is close to H1
  (in-degree Gini, not supported) and H13/H21 (top-three shares, not supported).
- **Custodian departure** is a property of one person over time, can be read from sent mail
  alone at week resolution (insensitive to the hour convention), and the mailbox's own inbox can
  show whether the record still covers that person. That last property lets the design separate
  "stopped sending" from "mailbox not collected", which is the main artifact.

## Definitions

Weeks are Monday-start UTC weeks of `ts_hour`; events with a timestamp outside
`plausible_start .. plausible_end` are left out. Units are custodians (`entities_p.is_custodian`).

- **Sent week** of custodian X: a week with at least one event whose sender is X (any recipient,
  any flag: a departure is the end of all sending).
- **Mailbox-only week** of X: a week with a message addressed to X whose sender is not a
  custodian and which has no other custodian among its recipients. Such a message can survive
  only in X's own mailbox, so a mailbox-only week shows that X's mailbox was collected that week.
- **Silence**: S consecutive weeks without a sent week, all inside the record horizon (up to
  `plausible_end`). Its **start** is the week after the last sent week before it.
- **Live silence**: a silence with mailbox-only mail in at least L of its S weeks: mail kept
  arriving, nothing went out.
- **At risk at the start of window W**: in the 16 weeks before W, X has at least A sent weeks
  and at least A mailbox-only weeks (both sides of the mailbox are covered), and no silence
  starts in those 16 weeks (X has not already gone quiet).
- **Departure in W**: an at-risk custodian whose live silence starts in a week whose Monday lies
  in W. A silence that is not live is a **record end** (the mailbox stops holding mail too: a
  collection end or a closed account) and is reported, but is not a departure.
- **Hazard** h(W) = departures / at risk.

Primary parameters: S = 16 weeks, L = 4 weeks, A = 4 weeks.

## Windows

Those of H5–H25, fixed by public dates: crisis W1 (2001-08-14 to 2001-12-02) against reference
W0 (same weeks of 2000); placebo P1 (2001-01-01 to 2001-04-30) against P0 (same weeks of 2000).
**Rolling placebo**: every window of W1's length starting on a Monday from 2000-01-03 whose end
lies before W1's start, kept if at least 20 custodians are at risk. These windows include the
months of the record change (May–August 2001), so an exit wave caused by the change of mail
system would show there. Descriptive: the hazard for each calendar month from 2000-01 to
2001-12 (the public events of `config.PUBLIC_EVENTS` are marked next to it in the report).

## Test

- **Primary**: one-sided Fisher exact test that the departure share in W1 is greater than in W0.
- **Placebo**: the same test for P1 against P0.
- **Rolling**: h(W1) is compared with every rolling placebo window's hazard.
- **Leave one custodian out**: each custodian removed in turn from everything; the primary test
  and the rolling comparison are recomputed.
- **Within the same people**: a paired test is not used, because being at risk in W1 requires
  not having left in W0 (survivorship would bias a pairing towards W1). The composition control
  is the cohort variant below.

## Robustness variants (each recomputes W1, W0, P1, P0 and the rolling windows)

| Variant | Change from the primary | Threat it addresses |
|---------|-------------------------|---------------------|
| silence 8 / silence 26 | S = 8 or 26 weeks | arbitrary silence length |
| live 1 / live 8 | L = 1 or 8 weeks | inbox retention grows in the crisis, which makes "live" easier to show |
| active 2 / active 8 | A = 2 or 8 weeks | arbitrary activity threshold |
| custodian-visible | a sent week counts only mail from X to another custodian | X's own sent folder stopped being collected (that mail survives in the other custodian's inbox) |
| same cohort | at risk in W1 (P1) only if also at risk at W0's (P0's) start | the mix of mailboxes changes between the years |
| no successor | departures with a successor-like pseudonym are dropped, with them their custodians from the at-risk set | an address change not merged by identity resolution (likelier with a change of mail system) |
| any silence | every silence counts, live or not | reported only: it mixes in collection ends |

**Successor-like pseudonym** of a departure: an internal person P ≠ X who sent nothing in the 26
weeks before X's silence start, sent in the S weeks after it, and whose recipients in those S
weeks include at least half of X's distinct recipients from the 16 weeks before (and at least
three of them).

## Decision rule (fixed now)

The candidate finding: *during the crisis, custodians stopped sending while their mailboxes kept
receiving mail, at a higher rate than in the same weeks of 2000 and than in any comparable
earlier window.*

Necessary for any claim:

1. at least k = 5 departures in W1 (otherwise nothing can be published about them);
2. primary p < 0.05;
3. h(W1) is above every rolling placebo window's hazard;
4. the placebo P1 against P0 has p ≥ 0.05.

**High** confidence if also: 5. primary p < 0.05 / 26 (a Bonferroni bound over H1–H26, because
this question comes after twenty-five others); 6. every leave-one-out keeps 2 and 3; 7. every
variant except *any silence* keeps p < 0.05 and h(W1) > h(W0).

**Moderate** if 1–4 and 6 hold and every variant except *any silence* keeps h(W1) > h(W0), but 5
or a variant's p fails. **Low** (a lead, not a finding) if 1–4 hold and anything else fails.
If any of 1–4 fails, the result is: **no departure wave can be established**, with the reasons.

## Known limits, stated before computing

- Custodians are about 150 mostly senior people; a departure among them is not a layoff count.
  *(As built: about 150 mailboxes give 147 custodian entities, 122 of them internal persons.)*
- A live silence is also produced by leave, a role without email, an assistant sending on X's
  behalf, or an unmerged address change (the successor variant only partly covers it).
- A message addressed to X can sit in another custodian's mailbox through an invisible Bcc; it
  would then look like mailbox-only mail. Rare, not corrected.
- Departures right after the Chapter 11 filing (the layoffs of December 2001) fall after W1 and
  are not part of the test; the monthly hazard shows them descriptively. Their silence reaches
  into 2002, when the record thins, so they are likelier to be record ends.
- Power is limited: tens of custodians at risk, a handful of events per window.
- Publication: counts of at-risk custodians, departures and record ends below k = 5 are
  suppressed, and with them any hazard derived from them; a p-value is published only when
  every count it is computed from reaches k, otherwise only its band (below 0.05/26, below 0.05,
  0.05 or above).

## Amendment before computing (2026-11-14, still nothing computed)

Two publication details changed while designing the release table, before any number existed:

- **No monthly hazard is published.** Monthly departure counts overlap the window counts, so a
  published window total minus published months would reveal a month below k. Instead the
  crisis departures are split at the third-quarter loss announcement (2001-10-16, the middle
  event of `config.PUBLIC_EVENTS`; *corrected 2026-11-14: it is the second of the five events,
  `config.CRISIS_SPLIT`*): before it and from it on. Both parts are published only if
  both reach k. Descriptive; not part of the rule.
- **Variants publish no counts.** Their at-risk sets and departures are nested in the primary's
  (a variant's count minus the primary's could describe fewer than k custodians), so each variant
  publishes only whether h(W1) > h(W0), its p band, its placebo's p band and whether it clears
  the rolling windows. The primary publishes its counts under the k rule stated above.

## O1 (H26) result (written after it was computed)

First computed by the pipeline at commit 9a6c4c0, which was committed before the first real-data
run. The computation of the outcome was not changed after the result; later commits changed
report wording, documents, the release suppression and added the power columns below (the run
manifest names the commit of the committed release). The numbers live in `release/departures.csv`, `release/departure_tests.csv` and the
report's H26 section; they are not repeated here, so they cannot go stale.

**Outcome: not established.** No departure wave in the crisis window can be claimed. The first
necessary condition already fails: fewer than k = 5 of the custodians at risk in the crisis
window stopped sending while their mailbox kept receiving mail (so the count is suppressed).
The other necessary conditions fail too: the crisis share is not above the reference share
(one-sided p at or above 0.05) and not above every earlier window of the same length.
Leave-one-out does not apply once the test itself fails. The placebo passes, but with 9
custodians at risk before it, it could hardly fail. No published variant in the rule reaches p
below 0.05 (one variant, `active 8`, has a window with fewer than k custodians at risk and
publishes nothing). Record ends in the crisis and reference windows and both parts of the
split at the third-quarter loss announcement are suppressed.

**Power (added after the data-science review, post hoc).** At these numbers at risk the test
could only see a large wave: even with no departure a year earlier, the crisis window needed the
number of departures published as `detectable_departures` (`release/departure_tests.csv`) for p
below 0.05. A null here rules out a large wave, not a modest rise.

Read plainly: among the custodians whose record covers both what they sent and what they
received, the headers show no departure wave in the crisis window: departures there are too
few to publish, and their share is not higher than a year earlier. This does not say nobody left Enron; it says the collected mailboxes do not record a
departure wave among their owners in those weeks. Departures after the bankruptcy filing
(December 2001 onwards) fall outside the stated window, and their silences run into the months
when collection ends, where they cannot be told from record ends.

**Deviations from the statement, found in review (after the result).** The successor rule
counts only X's recipients who are internal persons, where the statement says "X's distinct
recipients". Leave-one-out removes each custodian from the units counted, not from the record
(their mail still marks others' mailbox-only weeks and successor candidates). Neither can
change the outcome: the primary test fails before either matters.
