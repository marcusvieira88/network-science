/**
 * The H26 vocabulary of the release contract (contracts/schemas.py DEPARTURE_*, P_BANDS), in its
 * own module so that both the loader (data.ts) and the privacy guard can use it without a cycle.
 */
export const DEPARTURE_WINDOWS = ["crisis", "reference", "placebo after", "placebo before"] as const;
/** The crisis window cut at a public event; descriptive, published only together. */
export const DEPARTURE_SPLITS = ["crisis before the split", "crisis from the split"] as const;
export const DEPARTURE_PERIODS = [...DEPARTURE_WINDOWS, ...DEPARTURE_SPLITS] as const;
export const DEPARTURE_OUTCOMES = ["high", "moderate", "low", "not established"] as const;
/** The variant holding the stated definition; the others are robustness variants. */
export const DEPARTURE_PRIMARY = "primary";
/** The run parameters the H26 statement and tests name (config.py), checked when the file loads. */
export const DEPARTURE_PARAMETERS = [
  "alpha",
  "departure_silence_weeks",
  "departure_live_weeks",
  "departure_active_weeks",
  "departure_lookback_weeks",
  "departure_rolling_min_at_risk",
] as const;
export type DepartureParameter = (typeof DEPARTURE_PARAMETERS)[number];
/** A p-value's band: below alpha over the hypotheses stated, below alpha, at or above it. */
export const P_BANDS = ["below the family bound", "below alpha", "alpha or above", "not computable"] as const;
