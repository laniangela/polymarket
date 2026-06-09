from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from polyscanner.storage import SnapshotStore


@dataclass(frozen=True)
class MicrostructureFeatures:
    market_ticker: str
    calculated_at: datetime
    latest_observation_at: datetime | None
    freshness_seconds: float | None
    quote_observations: int
    coinbase_observations: int
    yes_bid: float | None
    yes_ask: float | None
    spread: float | None
    bid_size: float | None
    ask_size: float | None
    depth_imbalance: float | None
    coinbase_momentum_60s_bps: float | None
    quote_change_60s_points: float | None
    repricing_delay_seconds: float | None
    brti_basis_usd: float | None


class MicrostructureFeatureEngine:
    def __init__(
        self,
        store: SnapshotStore,
        now: datetime | None = None,
        lookback_minutes: int = 15,
    ) -> None:
        self.now = now or datetime.now(timezone.utc)
        since = self.now - timedelta(minutes=lookback_minutes)
        self.rows = store.feed_observations_since(since.isoformat())

    def calculate(self, market_ticker: str) -> MicrostructureFeatures:
        market_rows = sorted(
            (
                row
                for row in self.rows
                if row["source"] == "orderbook"
                and row["market_ticker"] == market_ticker
                and (row["yes_bid"] is not None or row["yes_ask"] is not None)
            ),
            key=lambda row: str(row["observed_at"]),
        )
        coinbase_rows = sorted(
            (
                row
                for row in self.rows
                if row["source"] == "coinbase" and row["coinbase_spot"] is not None
            ),
            key=lambda row: str(row["observed_at"]),
        )
        latest = market_rows[-1] if market_rows else None
        latest_at = _timestamp(latest["observed_at"]) if latest else None
        freshness = (
            max(0.0, (self.now - latest_at).total_seconds())
            if latest_at is not None
            else None
        )
        yes_bid = _float(latest.get("yes_bid")) if latest else None
        yes_ask = _float(latest.get("yes_ask")) if latest else None
        bid_size = _float(latest.get("yes_bid_size")) if latest else None
        ask_size = _float(latest.get("yes_ask_size")) if latest else None
        spread = yes_ask - yes_bid if yes_bid is not None and yes_ask is not None else None
        depth_total = (bid_size or 0) + (ask_size or 0)
        depth_imbalance = (
            ((bid_size or 0) - (ask_size or 0)) / depth_total
            if depth_total > 0 and bid_size is not None and ask_size is not None
            else None
        )
        recent_start = self.now - timedelta(seconds=60)
        recent_coinbase = [
            row for row in coinbase_rows if _timestamp(row["observed_at"]) >= recent_start
        ]
        recent_market = [
            row for row in market_rows if _timestamp(row["observed_at"]) >= recent_start
        ]
        momentum = _relative_bps(recent_coinbase, "coinbase_spot")
        quote_change = _midpoint_change(recent_market)
        brti_basis = None
        if latest and latest.get("coinbase_spot") is not None and latest.get("brti_value") is not None:
            brti_basis = float(latest["coinbase_spot"]) - float(latest["brti_value"])
        return MicrostructureFeatures(
            market_ticker=market_ticker,
            calculated_at=self.now,
            latest_observation_at=latest_at,
            freshness_seconds=freshness,
            quote_observations=len(market_rows),
            coinbase_observations=len(coinbase_rows),
            yes_bid=yes_bid,
            yes_ask=yes_ask,
            spread=spread,
            bid_size=bid_size,
            ask_size=ask_size,
            depth_imbalance=depth_imbalance,
            coinbase_momentum_60s_bps=momentum,
            quote_change_60s_points=quote_change,
            repricing_delay_seconds=_repricing_delay(coinbase_rows, market_rows),
            brti_basis_usd=brti_basis,
        )


def _repricing_delay(
    coinbase_rows: list[dict[str, object]],
    market_rows: list[dict[str, object]],
    trigger_usd: float = 20,
    quote_step: float = 0.01,
) -> float | None:
    if len(coinbase_rows) < 2 or len(market_rows) < 2:
        return None
    for index in range(len(coinbase_rows) - 1, 0, -1):
        current = coinbase_rows[index]
        baseline = next(
            (
                row
                for row in reversed(coinbase_rows[:index])
                if abs(float(current["coinbase_spot"]) - float(row["coinbase_spot"]))
                >= trigger_usd
            ),
            None,
        )
        if baseline is None:
            continue
        trigger_at = _timestamp(current["observed_at"])
        before = [row for row in market_rows if _timestamp(row["observed_at"]) <= trigger_at]
        after = [row for row in market_rows if _timestamp(row["observed_at"]) > trigger_at]
        if not before or not after:
            continue
        baseline_midpoint = _midpoint(before[-1])
        if baseline_midpoint is None:
            continue
        response = next(
            (
                row
                for row in after
                if (mid := _midpoint(row)) is not None
                and abs(mid - baseline_midpoint) >= quote_step
            ),
            None,
        )
        if response is not None:
            return max(
                0.0,
                (_timestamp(response["observed_at"]) - trigger_at).total_seconds(),
            )
    return None


def _midpoint_change(rows: list[dict[str, object]]) -> float | None:
    if len(rows) < 2:
        return None
    first = _midpoint(rows[0])
    last = _midpoint(rows[-1])
    return last - first if first is not None and last is not None else None


def _midpoint(row: dict[str, object]) -> float | None:
    bid = _float(row.get("yes_bid"))
    ask = _float(row.get("yes_ask"))
    if bid is not None and ask is not None:
        return (bid + ask) / 2
    return bid if bid is not None else ask


def _relative_bps(rows: list[dict[str, object]], field: str) -> float | None:
    if len(rows) < 2:
        return None
    first = float(rows[0][field])
    last = float(rows[-1][field])
    return ((last / first) - 1) * 10_000 if first else None


def _timestamp(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)


def _float(value: object) -> float | None:
    return None if value is None else float(value)
