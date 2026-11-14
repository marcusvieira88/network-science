"""Change point, effect size, block bootstrap interval and Holm correction (docs/hypotheses.md).

Pure functions on numpy arrays. Every random draw comes from a generator built by `rng_for`
from the configured seed, so results are reproducible.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

# Decision parameters fixed in docs/hypotheses.md before any real-data analysis. They belong in
# config.py, which is frozen for work packages; see the WP-F report.
ALPHA = 0.05
CI_LEVEL = 0.95
BLOCK_WEEKS = 4
MIN_AFTER_WEEKS = 4
MIN_BASELINE_WEEKS = 2

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]


class InsufficientData(ValueError):
    """The series is too short or too flat for the statistic to be defined."""


@dataclass(frozen=True)
class ChangePoint:
    index: int  # first week of the "after" period
    statistic: float
    p_value: float


def rng_for(seed: int, *stream: int) -> np.random.Generator:
    """Independent, reproducible generator for one named use of the configured seed."""
    return np.random.default_rng([seed, *stream])


def _candidates(n_weeks: int, first_candidate: int) -> IntArray:
    first = max(first_candidate, 1)
    last = n_weeks - MIN_AFTER_WEEKS
    if last < first:
        raise InsufficientData("no candidate change week leaves enough weeks after it")
    return np.arange(first, last + 1, dtype=np.int64)


def _cusum_scores(values: FloatArray, candidates: IntArray, direction: int) -> FloatArray:
    """Weighted directional CUSUM per candidate week; `values` is (..., weeks).

    A step in `direction` at week t drives the centred sum of the weeks before t towards
    -direction. The weight sqrt(n / (t (n - t))) keeps late and early changes from being
    under-scored relative to changes in the middle.
    """
    n = values.shape[-1]
    centred = values - values.mean(axis=-1, keepdims=True)
    sums = np.cumsum(centred, axis=-1)[..., candidates - 1]
    weights = np.sqrt(n / (candidates * (n - candidates)))
    result: FloatArray = -direction * sums * weights
    return result


def change_point(
    values: FloatArray,
    first_candidate: int,
    direction: int,
    permutations: int,
    rng: np.random.Generator,
) -> ChangePoint:
    """Most likely change week at or after `first_candidate` in `direction` (+1 up, -1 down),
    with a permutation p-value over shuffled weeks."""
    candidates = _candidates(len(values), first_candidate)
    scores = _cusum_scores(values, candidates, direction)
    best = int(np.argmax(scores))
    observed = float(scores[best])
    shuffled = rng.permuted(np.tile(values, (permutations, 1)), axis=1)
    null = _cusum_scores(shuffled, candidates, direction).max(axis=1)
    exceed = int(np.sum(null >= observed))
    return ChangePoint(int(candidates[best]), observed, (1 + exceed) / (1 + permutations))


def effect_size(before: FloatArray, after: FloatArray) -> float:
    """(mean after − mean before) / sample sd before."""
    if len(before) < MIN_BASELINE_WEEKS or len(after) == 0:
        raise InsufficientData("effect needs two baseline weeks and one week after")
    spread = float(np.std(before, ddof=1))
    if spread == 0.0:
        raise InsufficientData("baseline is constant")
    return (float(np.mean(after)) - float(np.mean(before))) / spread


def _block_resample(values: FloatArray, reps: int, rng: np.random.Generator) -> FloatArray:
    """(reps, len) moving-block resamples: random 4-week blocks laid end to end."""
    n = len(values)
    block = min(BLOCK_WEEKS, n)
    n_blocks = -(-n // block)
    starts = rng.integers(0, n - block + 1, size=(reps, n_blocks))
    index = (starts[:, :, None] + np.arange(block)).reshape(reps, -1)[:, :n]
    result: FloatArray = values[index]
    return result


def block_bootstrap_ci(
    before: FloatArray, after: FloatArray, reps: int, rng: np.random.Generator
) -> tuple[float, float]:
    """Percentile interval of `effect_size`, resampling each period by moving blocks."""
    effect_size(before, after)  # raises if the point estimate is undefined
    base = _block_resample(before, reps, rng)
    post = _block_resample(after, reps, rng)
    spread = base.std(axis=1, ddof=1)
    valid = spread > 0
    effects = (post.mean(axis=1)[valid] - base.mean(axis=1)[valid]) / spread[valid]
    if len(effects) == 0:
        raise InsufficientData("every bootstrap baseline is constant")
    tail = (1.0 - CI_LEVEL) / 2.0
    low, high = np.quantile(effects, [tail, 1.0 - tail])
    return float(low), float(high)


def on_side(direction: int, ci_low: float, ci_high: float) -> bool:
    """The interval lies wholly on the hypothesised side of zero."""
    return ci_low > 0 if direction > 0 else ci_high < 0


def holm(p_values: Sequence[float]) -> list[float]:
    """Holm step-down adjusted p-values, in input order."""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p_values[i]))
        adjusted[i] = running
    return adjusted
