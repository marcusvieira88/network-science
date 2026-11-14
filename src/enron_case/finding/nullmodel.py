"""Volume-preserving null network and the deviation of an observed effect from it.

Within each week, recipients are shuffled among events with the same weight, the same
`in_network` flag and the same kind of sender (person or not, internal or not). Each event keeps
its sender and weight, and each recipient receives events of the same weights from the same kind
of sender as before, so every sender's out-weight and every recipient's in-weight per week is
unchanged, including the in-weight from internal persons that the network is built from. What
changes is who is tied to whom.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import polars as pl

from enron_case.finding.stats import InsufficientData

# A recipient's attributes travel with the recipient.
RECIPIENT_COLUMNS = ("recipient_pid", "recipient_type", "recipient_internal", "recipient_org_pid")
# The sender kind is in the stratum because only ties from internal persons enter the network:
# without it a recipient could trade a person's message for a list's of equal weight.
STRATUM = ("_week", "in_network", "sender_type", "sender_internal", "weight")
_ROW = "_row"
_DRAW = "_draw"


def rewire(events: pl.DataFrame, rng: np.random.Generator) -> pl.DataFrame:
    """One rewired copy of `events`, rows and columns in the input order."""
    keyed = events.with_columns(
        pl.col("ts_hour").dt.date().dt.truncate("1w").alias(STRATUM[0]),
        pl.int_range(pl.len()).alias(_ROW),
        pl.Series(_DRAW, rng.random(events.height)),
    )
    # Both sides sorted by stratum first, so row i of each lies in the same stratum; within a
    # stratum the senders keep their order and the recipients take a random one.
    senders = keyed.sort([*STRATUM, _ROW]).drop(RECIPIENT_COLUMNS)
    recipients = keyed.sort([*STRATUM, _DRAW]).select(RECIPIENT_COLUMNS)
    return pl.concat([senders, recipients], how="horizontal").sort(_ROW).select(events.columns)


def null_z(observed: float, null_values: Sequence[float]) -> float:
    """(observed − mean null) / sample sd null. ±inf when the null never varies but the
    observation differs from it; 0 when the null reproduces the observation exactly."""
    if len(null_values) < 2:
        raise InsufficientData("null deviation needs at least two replicates")
    values = np.asarray(null_values, dtype=np.float64)
    # Tested exactly: the mean of identical floats can differ from them in the last bit.
    if np.all(values == values[0]):
        difference = observed - float(values[0])
        return 0.0 if difference == 0.0 else math.copysign(math.inf, difference)
    return (observed - float(values.mean())) / float(values.std(ddof=1))
