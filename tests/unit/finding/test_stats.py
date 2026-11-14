"""Statistics against known answers: planted steps, iid noise, hand-computed cases."""

from __future__ import annotations

import numpy as np
import pytest

from enron_case.config import Config
from enron_case.finding import stats

CONFIG = Config()
ALPHA = CONFIG.alpha

N_WEEKS = 117  # analysis window 2000-01-03 .. 2002-03-25
FIRST_CANDIDATE = 52  # first week after the 2000 baseline


def _step_series(seed: int, change: int, step: float, n: int = N_WEEKS) -> np.ndarray:
    rng = np.random.default_rng(seed)
    values = rng.normal(0.0, 1.0, n)
    values[change:] += step
    return values


@pytest.mark.parametrize(("seed", "change"), [(1, 60), (2, 85), (3, 100), (4, 70)])
def test_cusum_recovers_planted_step_within_one_week(seed: int, change: int) -> None:
    values = _step_series(seed, change, step=3.0)
    found = stats.change_point(
        values, FIRST_CANDIDATE, 1, 999, stats.rng_for(seed), min_after_weeks=CONFIG.min_after_weeks
    )
    assert abs(found.index - change) <= 1
    assert found.p_value < ALPHA


def test_cusum_localises_three_sd_steps_within_one_week_almost_always() -> None:
    hits = 0
    n_series = 200
    for seed in range(n_series):
        change = int(np.random.default_rng(seed).integers(60, N_WEEKS - 12))
        values = _step_series(seed, change, step=3.0)
        found = stats.change_point(
            values,
            FIRST_CANDIDATE,
            1,
            9,
            stats.rng_for(seed),
            min_after_weeks=CONFIG.min_after_weeks,
        )
        hits += abs(found.index - change) <= 1
    assert hits / n_series >= 0.95


def test_cusum_finds_downward_step_only_when_looking_down() -> None:
    values = _step_series(5, 80, step=-2.0)
    down = stats.change_point(
        values, FIRST_CANDIDATE, -1, 999, stats.rng_for(5), min_after_weeks=CONFIG.min_after_weeks
    )
    up = stats.change_point(
        values, FIRST_CANDIDATE, 1, 999, stats.rng_for(5), min_after_weeks=CONFIG.min_after_weeks
    )
    assert abs(down.index - 80) <= 1
    assert down.p_value < ALPHA
    assert up.p_value > ALPHA


def test_permutation_false_positive_rate_on_no_change() -> None:
    n_series = 400
    rejections = 0
    for seed in range(n_series):
        values = np.random.default_rng(seed).normal(0.0, 1.0, N_WEEKS)
        found = stats.change_point(
            values,
            FIRST_CANDIDATE,
            1,
            199,
            stats.rng_for(10_000 + seed),
            min_after_weeks=CONFIG.min_after_weeks,
        )
        rejections += found.p_value < ALPHA
    rate = rejections / n_series
    # Exact test: expected rate is alpha. Allow two binomial standard errors of sampling noise.
    tolerance = 2 * np.sqrt(ALPHA * (1 - ALPHA) / n_series)
    assert rate <= ALPHA + tolerance


def _ar1_series(seed: int, phi: float, n: int = N_WEEKS) -> np.ndarray:
    """Stationary AR(1) with unit innovations and no change: x_t = phi * x_(t-1) + e_t."""
    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, 1.0, n)
    values = np.empty(n)
    values[0] = noise[0] / np.sqrt(1 - phi**2)
    for t in range(1, n):
        values[t] = phi * values[t - 1] + noise[t]
    return values


# False-positive rates measured on 1000 no-change AR(1) series (documented in docs/hypotheses.md,
# "Known threats"). The permutation test assumes exchangeable weeks; autocorrelation breaks that.
AR1_CALIBRATION = {0.3: 0.148, 0.5: 0.256}


@pytest.mark.parametrize(("phi", "documented"), sorted(AR1_CALIBRATION.items()))
def test_permutation_test_is_liberal_on_autocorrelated_no_change(
    phi: float, documented: float
) -> None:
    n_series = 1000
    rejections = 0
    for seed in range(n_series):
        found = stats.change_point(
            _ar1_series(seed, phi),
            FIRST_CANDIDATE,
            1,
            199,
            stats.rng_for(20_000 + seed),
            min_after_weeks=CONFIG.min_after_weeks,
        )
        rejections += found.p_value < ALPHA
    rate = rejections / n_series
    standard_error = np.sqrt(documented * (1 - documented) / n_series)
    assert abs(rate - documented) <= 2 * standard_error  # the documented limit still holds
    assert rate > ALPHA + 2 * np.sqrt(ALPHA * (1 - ALPHA) / n_series)  # well above nominal


def test_change_point_is_deterministic_for_a_seed() -> None:
    values = _step_series(9, 90, step=0.3)
    first = stats.change_point(
        values, FIRST_CANDIDATE, 1, 199, stats.rng_for(42), min_after_weeks=CONFIG.min_after_weeks
    )
    second = stats.change_point(
        values, FIRST_CANDIDATE, 1, 199, stats.rng_for(42), min_after_weeks=CONFIG.min_after_weeks
    )
    assert first == second


def test_change_point_needs_room_after_the_baseline() -> None:
    values = np.zeros(FIRST_CANDIDATE + CONFIG.min_after_weeks - 1)
    with pytest.raises(stats.InsufficientData):
        stats.change_point(
            values, FIRST_CANDIDATE, 1, 99, stats.rng_for(1), min_after_weeks=CONFIG.min_after_weeks
        )


def test_effect_size_hand_computed() -> None:
    # baseline mean 2, sample sd 1; after mean 4.5
    assert stats.effect_size(
        np.array([1.0, 2.0, 3.0]),
        np.array([4.0, 5.0]),
        min_baseline_weeks=CONFIG.min_baseline_weeks,
    ) == pytest.approx(2.5)


@pytest.mark.parametrize(
    ("before", "after"),
    [([2.0, 2.0, 2.0], [3.0]), ([1.0], [3.0]), ([1.0, 2.0], [])],
)
def test_effect_size_undefined_raises(before: list[float], after: list[float]) -> None:
    with pytest.raises(stats.InsufficientData):
        stats.effect_size(
            np.array(before), np.array(after), min_baseline_weeks=CONFIG.min_baseline_weeks
        )


def test_block_bootstrap_interval_covers_a_known_effect() -> None:
    true_effect = 1.0
    covered = 0
    n_series = 60
    for seed in range(n_series):
        rng = np.random.default_rng(seed)
        before = rng.normal(0.0, 1.0, 52)
        after = rng.normal(true_effect, 1.0, 33)
        low, high = stats.block_bootstrap_ci(
            before,
            after,
            999,
            stats.rng_for(500 + seed),
            block_weeks=CONFIG.block_weeks,
            ci_level=CONFIG.ci_level,
            min_baseline_weeks=CONFIG.min_baseline_weeks,
        )
        assert low < high
        covered += low <= true_effect <= high
    # Nominal 95%; the percentile interval on short series undercovers a little.
    assert covered / n_series >= 0.85


def test_block_bootstrap_interval_excludes_zero_for_a_large_effect() -> None:
    rng = np.random.default_rng(3)
    low, _ = stats.block_bootstrap_ci(
        rng.normal(0, 1, 52),
        rng.normal(3, 1, 33),
        999,
        stats.rng_for(3),
        block_weeks=CONFIG.block_weeks,
        ci_level=CONFIG.ci_level,
        min_baseline_weeks=CONFIG.min_baseline_weeks,
    )
    assert low > 0


def test_holm_worked_example() -> None:
    # sorted: 0.005 x4 = 0.02; 0.01 x3 = 0.03; 0.03 x2 = 0.06; 0.04 x1 = 0.04 -> 0.06 (monotone)
    assert stats.holm([0.01, 0.04, 0.03, 0.005]) == pytest.approx([0.03, 0.06, 0.06, 0.02])


def test_holm_caps_at_one() -> None:
    assert stats.holm([0.5, 0.6, 1.0, 0.9]) == pytest.approx([1.0, 1.0, 1.0, 1.0])
