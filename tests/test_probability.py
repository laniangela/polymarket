from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from polyscanner.models import Direction, ThresholdContract
from polyscanner.probability import (
    annualized_realized_volatility,
    estimate_contract,
    threshold_probability,
)


def test_probability_increases_when_spot_moves_above_strike():
    low = threshold_probability(63_000, 64_000, 0.60, 3600, Direction.ABOVE)
    high = threshold_probability(65_000, 64_000, 0.60, 3600, Direction.ABOVE)
    assert high > low


def test_above_and_below_are_complements():
    above = threshold_probability(63_700, 64_000, 0.60, 3600, Direction.ABOVE)
    below = threshold_probability(63_700, 64_000, 0.60, 3600, Direction.BELOW)
    assert above + below == pytest.approx(1)


def test_between_probability_is_bounded():
    probability = threshold_probability(
        63_700, 63_500, 0.60, 3600, Direction.BETWEEN, cap_strike_usd=63_750
    )
    assert 0 < probability < 1


def test_realized_volatility_is_positive():
    closes = pd.Series([100, 101, 99, 103, 102], dtype=float)
    assert annualized_realized_volatility(closes) > 0


def test_estimate_uses_executable_ask_and_fee():
    now = datetime.now(timezone.utc)
    contract = ThresholdContract(
        "1", "btc", "Will BTC be above $64k?", 64_000, Direction.ABOVE,
        now + timedelta(hours=1), 0.32, 0.33, 0.05,
    )
    estimate = estimate_contract(contract, 63_700, 0.60, now)
    assert estimate.executable_price == 0.33
    assert estimate.edge_after_fee is not None
    assert estimate.edge_after_fee < estimate.raw_edge
