from __future__ import annotations

from datetime import datetime, timedelta, timezone

from polyscanner.agents import MicrostructureAgent
from polyscanner.features import MicrostructureFeatureEngine, MicrostructureFeatures
from polyscanner.storage import SnapshotStore


class MicrostructureValidator:
    def __init__(
        self,
        store: SnapshotStore,
        horizons: tuple[int, ...] = (5, 15, 30, 60),
        sample_interval_seconds: int = 15,
        fee_coefficient: float = 0.07,
    ) -> None:
        self.store = store
        self.horizons = horizons
        self.sample_interval_seconds = sample_interval_seconds
        self.fee_coefficient = fee_coefficient

    def process_quote(
        self,
        market_ticker: str,
        observed_at: datetime,
        exit_bid: float | None,
    ) -> None:
        self.resolve_due(market_ticker, observed_at, exit_bid)
        if self._sample_due(market_ticker, observed_at):
            self.capture(market_ticker, observed_at)

    def capture(self, market_ticker: str, evaluated_at: datetime) -> int:
        feature = MicrostructureFeatureEngine(
            self.store,
            now=evaluated_at,
        ).calculate(market_ticker)
        opinion = MicrostructureAgent(_StaticFeatureEngine(feature)).evaluate_features(feature)
        signal_id = self.store.record_microstructure_signal(
            evaluated_at=evaluated_at.isoformat(),
            market_ticker=market_ticker,
            verdict=opinion.verdict.value,
            score=opinion.score,
            summary=opinion.summary,
            entry_bid=feature.yes_bid,
            entry_ask=feature.yes_ask,
            spread=feature.spread,
            bid_size=feature.bid_size,
            ask_size=feature.ask_size,
            depth_imbalance=feature.depth_imbalance,
            coinbase_momentum_60s_bps=feature.coinbase_momentum_60s_bps,
            quote_change_60s_points=feature.quote_change_60s_points,
            repricing_delay_seconds=feature.repricing_delay_seconds,
            freshness_seconds=feature.freshness_seconds,
            quote_observations=feature.quote_observations,
            coinbase_observations=feature.coinbase_observations,
        )
        for horizon in self.horizons:
            self.store.create_signal_outcome(
                signal_id,
                horizon,
                (evaluated_at + timedelta(seconds=horizon)).isoformat(),
            )
        return signal_id

    def resolve_due(
        self,
        market_ticker: str,
        observed_at: datetime,
        exit_bid: float | None,
    ) -> int:
        pending = self.store.pending_signal_outcomes(
            market_ticker,
            observed_at.isoformat(),
        )
        for outcome in pending:
            entry_ask = _optional_float(outcome["entry_ask"])
            gross = (
                exit_bid - entry_ask
                if exit_bid is not None and entry_ask is not None
                else None
            )
            fees = (
                self._fee(entry_ask) + self._fee(exit_bid)
                if exit_bid is not None and entry_ask is not None
                else None
            )
            net = gross - fees if gross is not None and fees is not None else None
            evaluated_at = _timestamp(outcome["evaluated_at"])
            self.store.resolve_signal_outcome(
                int(outcome["id"]),
                observed_at=observed_at.isoformat(),
                elapsed_seconds=(observed_at - evaluated_at).total_seconds(),
                exit_bid=exit_bid,
                gross_return=gross,
                estimated_fees=fees,
                net_return=net,
                favorable=(net > 0) if net is not None else None,
            )
        return len(pending)

    def _sample_due(self, market_ticker: str, now: datetime) -> bool:
        latest = self.store.latest_signal_time(market_ticker)
        if latest is None:
            return True
        return (now - _timestamp(latest)).total_seconds() >= self.sample_interval_seconds

    def _fee(self, price: float) -> float:
        return self.fee_coefficient * price * (1 - price)


class _StaticFeatureEngine:
    def __init__(self, feature: MicrostructureFeatures) -> None:
        self.feature = feature

    def calculate(self, _: str) -> MicrostructureFeatures:
        return self.feature


def _timestamp(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)
