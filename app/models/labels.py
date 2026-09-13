"""Label definition: N-trading-day forward return, thresholded into a
binary label ("5거래일 상승/초과수익" per the phase spec). See ADR 0011
for why a forward-return threshold (not a raw regression target or a
fixed dollar amount) is the baseline label.

Label computation looks *forward* from `as_of` by design - a label is
the supervised-learning target, and a target for a historical training
sample is necessarily computed from what happened after it. This is
never confused with a feature: `app.models.dataset.DatasetBuilder` is
the only caller of both this module and `app.models.features`, and it
fetches the two from separate, non-overlapping `MarketBarRow` lists
(see that module's docstring) - nothing in `app.models.features` ever
imports this module or looks past `as_of`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.db.repositories.market_data import MarketBarRow


@dataclass(frozen=True)
class LabelDefinition:
    horizon_days: int
    return_threshold: Decimal
    version: str


@dataclass(frozen=True)
class LabelResult:
    label: int | None
    forward_return: Decimal | None
    reason: str | None


def compute_forward_return_label(
    bars_from_as_of: list[MarketBarRow], *, definition: LabelDefinition
) -> LabelResult:
    """`bars_from_as_of` must be ordered ascending by `event_time`,
    starting at the `as_of` bar itself (index 0 = entry price) through
    at least `horizon_days` further bars (index `horizon_days` =
    forward price, e.g. index 5 for a 5-trading-day label).
    """
    required = definition.horizon_days + 1
    if len(bars_from_as_of) < required:
        return LabelResult(
            label=None,
            forward_return=None,
            reason=f"need {required} bars from as_of, got {len(bars_from_as_of)}",
        )

    entry_price = bars_from_as_of[0].close_price
    forward_price = bars_from_as_of[definition.horizon_days].close_price
    if entry_price == 0:
        return LabelResult(label=None, forward_return=None, reason="entry close_price is zero")

    forward_return = (forward_price - entry_price) / entry_price
    label = 1 if forward_return > definition.return_threshold else 0
    return LabelResult(label=label, forward_return=forward_return, reason=None)
