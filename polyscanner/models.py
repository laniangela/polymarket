from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Direction(StrEnum):
    ABOVE = "above"
    BELOW = "below"
    BETWEEN = "between"


@dataclass(frozen=True)
class ThresholdContract:
    market_id: str
    slug: str
    question: str
    strike_usd: float
    direction: Direction
    expires_at: datetime
    best_bid: float | None
    best_ask: float | None
    fee_coefficient: float
    cap_strike_usd: float | None = None
    yes_ask_size: float | None = None
    rules: str = ""
    venue: str = "Kalshi"


@dataclass(frozen=True)
class ProbabilityEstimate:
    spot_usd: float
    strike_usd: float
    expires_at: datetime
    annualized_volatility: float
    probability: float
    executable_price: float | None
    raw_edge: float | None
    edge_after_fee: float | None
    calculated_at: datetime
