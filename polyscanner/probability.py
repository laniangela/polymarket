from __future__ import annotations

import math
from datetime import datetime, timezone

import pandas as pd

from polyscanner.models import Direction, ProbabilityEstimate, ThresholdContract

SECONDS_PER_YEAR = 365.25 * 24 * 60 * 60


def annualized_realized_volatility(closes: pd.Series, periods_per_year: int = 365) -> float:
    clean = closes.astype(float).dropna()
    if len(clean) < 3:
        raise ValueError("At least three closes are required.")
    log_returns = clean.map(math.log).diff().dropna()
    return float(log_returns.std(ddof=1) * math.sqrt(periods_per_year))


def threshold_probability(
    spot_usd: float,
    strike_usd: float,
    annualized_volatility: float,
    seconds_to_expiry: float,
    direction: Direction,
    cap_strike_usd: float | None = None,
) -> float:
    if spot_usd <= 0 or strike_usd <= 0:
        raise ValueError("Spot and strike must be positive.")
    if seconds_to_expiry <= 0:
        above = 1.0 if spot_usd > strike_usd else 0.0
        return above if direction == Direction.ABOVE else 1.0 - above
    if annualized_volatility <= 0:
        raise ValueError("Volatility must be positive.")
    time_years = seconds_to_expiry / SECONDS_PER_YEAR
    sigma_t = annualized_volatility * math.sqrt(time_years)
    z = (math.log(strike_usd / spot_usd) + 0.5 * annualized_volatility**2 * time_years) / sigma_t
    above = 1.0 - _normal_cdf(z)
    if direction == Direction.BETWEEN:
        if cap_strike_usd is None or cap_strike_usd <= strike_usd:
            raise ValueError("Between contracts require a cap above the floor.")
        cap_z = (
            math.log(cap_strike_usd / spot_usd)
            + 0.5 * annualized_volatility**2 * time_years
        ) / sigma_t
        return max(0.0, _normal_cdf(cap_z) - _normal_cdf(z))
    return above if direction == Direction.ABOVE else 1.0 - above


def estimate_contract(
    contract: ThresholdContract,
    spot_usd: float,
    annualized_volatility: float,
    now: datetime | None = None,
) -> ProbabilityEstimate:
    now = now or datetime.now(timezone.utc)
    probability = threshold_probability(
        spot_usd,
        contract.strike_usd,
        annualized_volatility,
        (contract.expires_at - now).total_seconds(),
        contract.direction,
        contract.cap_strike_usd,
    )
    executable = contract.best_ask
    raw_edge = probability - executable if executable is not None else None
    fee = contract.fee_coefficient * executable * (1 - executable) if executable is not None else None
    edge_after_fee = raw_edge - fee if raw_edge is not None and fee is not None else None
    return ProbabilityEstimate(
        spot_usd=spot_usd,
        strike_usd=contract.strike_usd,
        expires_at=contract.expires_at,
        annualized_volatility=annualized_volatility,
        probability=probability,
        executable_price=executable,
        raw_edge=raw_edge,
        edge_after_fee=edge_after_fee,
        calculated_at=now,
    )


def _normal_cdf(value: float) -> float:
    return 0.5 * (1 + math.erf(value / math.sqrt(2)))
