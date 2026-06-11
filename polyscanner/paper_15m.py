from __future__ import annotations

import argparse
import signal
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from polyscanner.agents import MicrostructureAgent
from polyscanner.features import MicrostructureFeatureEngine
from polyscanner.live import parse_rest_orderbook
from polyscanner.models import Direction
from polyscanner.probability import annualized_realized_volatility, threshold_probability
from polyscanner.providers import CoinbasePublicClient, KalshiPublicClient
from polyscanner.storage import SnapshotStore


@dataclass(frozen=True)
class Paper15mConfig:
    database: str = "data/scanner.db"
    initial_equity: float = 1000
    poll_interval: float = 5
    min_edge: float = 0.04
    min_seconds_remaining: float = 30
    max_seconds_remaining: float = 12 * 60
    max_spread: float = 0.05
    min_ask_size: float = 10
    max_open_exposure: float = 0.25
    require_lag: bool = True
    duration_seconds: float | None = None


class Paper15mEngine:
    FEE_COEFFICIENT = 0.07

    def __init__(
        self,
        config: Paper15mConfig | None = None,
        store: SnapshotStore | None = None,
        kalshi: KalshiPublicClient | None = None,
        coinbase: CoinbasePublicClient | None = None,
    ) -> None:
        self.config = config or Paper15mConfig()
        self.store = store or SnapshotStore(self.config.database)
        self.kalshi = kalshi or KalshiPublicClient()
        self.coinbase = coinbase or CoinbasePublicClient()
        self.running = True
        self.started = time.monotonic()
        self.volatility = self._volatility()

    def stop(self, *_: object) -> None:
        self.running = False

    def run(self) -> None:
        while self.running and not self._expired():
            try:
                now = datetime.now(timezone.utc)
                self.settle_open_positions(now)
                for market in self.kalshi.active_bitcoin_15m_markets():
                    self.observe_and_consider(market, now)
            except Exception:
                # A transient public-feed failure must not end a two-hour test.
                pass
            time.sleep(self.config.poll_interval)

    def observe_and_consider(self, market: dict[str, object], now: datetime) -> int | None:
        ticker = str(market["ticker"])
        spot = self.coinbase.spot_price()
        self.store.record_feed_observation(
            observed_at=now.isoformat(),
            source="coinbase",
            coinbase_spot=spot,
        )
        quote = parse_rest_orderbook(ticker, self.kalshi.market_book(ticker), now)
        self.store.record_feed_observation(
            observed_at=now.isoformat(),
            source="orderbook",
            market_ticker=ticker,
            coinbase_spot=spot,
            yes_bid=quote.yes_bid,
            yes_ask=quote.yes_ask,
            yes_bid_size=quote.yes_bid_size,
            yes_ask_size=quote.yes_ask_size,
        )
        close = _timestamp(market["close_time"])
        remaining = (close - now).total_seconds()
        if not self.config.min_seconds_remaining <= remaining <= self.config.max_seconds_remaining:
            self._record_evaluation(
                market, now, close, "watch", "Outside the configured entry window.", spot=spot
            )
            return None
        target = float(market["floor_strike"])
        yes_probability = threshold_probability(
            spot,
            target,
            self.volatility,
            remaining,
            Direction.ABOVE,
        )
        yes_ask = quote.yes_ask
        no_ask = 1 - quote.yes_bid if quote.yes_bid is not None else None
        choices = [
            ("yes", yes_probability, yes_ask),
            ("no", 1 - yes_probability, no_ask),
        ]
        side, probability, entry_price = max(
            choices,
            key=lambda choice: _edge(choice[1], choice[2], self.FEE_COEFFICIENT),
        )
        edge = _edge(probability, entry_price, self.FEE_COEFFICIENT)
        if entry_price is None or edge < self.config.min_edge:
            self._record_evaluation(
                market, now, close, "watch", "Fee-adjusted edge is below 4%.",
                side=side, spot=spot, target=target, probability=probability,
                entry_price=entry_price, edge=edge,
            )
            return None
        spread = (
            quote.yes_ask - quote.yes_bid
            if quote.yes_ask is not None and quote.yes_bid is not None
            else None
        )
        ask_size = quote.yes_ask_size if side == "yes" else quote.yes_bid_size
        if spread is None or spread > self.config.max_spread:
            self._record_evaluation(
                market, now, close, "watch", "Displayed spread exceeds 5%.",
                side=side, spot=spot, target=target, probability=probability,
                entry_price=entry_price, edge=edge,
            )
            return None
        if ask_size is None or ask_size < self.config.min_ask_size:
            self._record_evaluation(
                market, now, close, "watch", "Fewer than 10 contracts are available at the ask.",
                side=side, spot=spot, target=target, probability=probability,
                entry_price=entry_price, edge=edge,
            )
            return None
        opinion = None
        if self.config.require_lag:
            feature_engine = MicrostructureFeatureEngine(self.store, now=now)
            opinion = MicrostructureAgent(feature_engine).evaluate_features(
                feature_engine.calculate(ticker)
            )
            if opinion.verdict.value != "support":
                self._record_evaluation(
                    market, now, close, "watch", opinion.summary,
                    side=side, spot=spot, target=target, probability=probability,
                    entry_price=entry_price, edge=edge, opinion=opinion,
                )
                return None
        summary = self.store.paper_15m_summary(self.config.initial_equity)
        open_stake = sum(
            float(position["stake_usd"])
            for position in self.store.open_paper_15m_positions()
        )
        if open_stake >= float(summary["equity"]) * self.config.max_open_exposure:
            self._record_evaluation(
                market, now, close, "watch", "Open exposure has reached the 25% ceiling.",
                side=side, spot=spot, target=target, probability=probability,
                entry_price=entry_price, edge=edge, opinion=opinion,
            )
            return None
        allocation = 0.10 if edge >= 0.08 else 0.075
        stake = float(summary["equity"]) * allocation
        fee_per_contract = self._fee(entry_price)
        unit_cost = entry_price + fee_per_contract
        quantity = stake / unit_cost
        if ask_size < quantity:
            self._record_evaluation(
                market,
                now,
                close,
                "watch",
                f"Ask depth can fill {ask_size:,.2f} of {quantity:,.2f} required contracts.",
                side=side,
                spot=spot,
                target=target,
                probability=probability,
                entry_price=entry_price,
                edge=edge,
                opinion=opinion,
            )
            return None
        position_id = self.store.create_paper_15m_position(
            {
                "market_ticker": ticker,
                "opened_at": now.isoformat(),
                "closes_at": close.isoformat(),
                "side": side,
                "target_price": target,
                "reference_spot": spot,
                "modeled_probability": probability,
                "entry_price": entry_price,
                "estimated_edge": edge,
                "allocation_pct": allocation,
                "stake_usd": stake,
                "quantity": quantity,
                "entry_fee_usd": quantity * fee_per_contract,
                "agent_verdict": opinion.verdict.value if opinion else "not_required",
                "agent_summary": opinion.summary if opinion else "Model-only comparison cohort.",
            }
        )
        self._record_evaluation(
            market, now, close, "entered" if position_id else "already entered",
            "Held to final YES/NO settlement." if position_id else "A position already exists.",
            side=side, spot=spot, target=target, probability=probability,
            entry_price=entry_price, edge=edge, opinion=opinion,
        )
        return position_id

    def _record_evaluation(
        self,
        market: dict[str, object],
        now: datetime,
        close: datetime,
        decision: str,
        reason: str,
        *,
        side: str | None = None,
        spot: float | None = None,
        target: float | None = None,
        probability: float | None = None,
        entry_price: float | None = None,
        edge: float | None = None,
        opinion: object | None = None,
    ) -> None:
        self.store.record_paper_15m_evaluation(
            {
                "market_ticker": str(market["ticker"]),
                "evaluated_at": now.isoformat(),
                "closes_at": close.isoformat(),
                "decision": decision,
                "reason": reason,
                "side": side,
                "reference_spot": spot,
                "target_price": target,
                "modeled_probability": probability,
                "entry_price": entry_price,
                "estimated_edge": edge,
                "agent_verdict": getattr(getattr(opinion, "verdict", None), "value", None),
                "agent_summary": getattr(opinion, "summary", None),
            }
        )

    def settle_open_positions(self, now: datetime) -> int:
        settled = 0
        for position in self.store.open_paper_15m_positions():
            if now < _timestamp(position["closes_at"]):
                continue
            market = self.kalshi.market(str(position["market_ticker"]))
            result = str(market.get("result") or "")
            if market.get("status") != "finalized" or result not in {"yes", "no"}:
                continue
            won = result == position["side"]
            payout = float(position["quantity"]) if won else 0.0
            pnl = payout - float(position["stake_usd"])
            self.store.settle_paper_15m_position(
                str(position["market_ticker"]),
                result=result,
                settled_at=now.isoformat(),
                payout_usd=payout,
                pnl_usd=pnl,
                return_pct=pnl / float(position["stake_usd"]),
            )
            settled += 1
        return settled

    def _volatility(self) -> float:
        return annualized_realized_volatility(
            self.coinbase.intraday_closes(hours=24, granularity=300),
            365 * 24 * 12,
        )

    def _fee(self, price: float) -> float:
        return self.FEE_COEFFICIENT * price * (1 - price)

    def _expired(self) -> bool:
        return (
            self.config.duration_seconds is not None
            and time.monotonic() - self.started >= self.config.duration_seconds
        )


def _edge(probability: float, price: float | None, fee_coefficient: float) -> float:
    if price is None:
        return float("-inf")
    return probability - price - fee_coefficient * price * (1 - price)


def _timestamp(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)


def _optional_float(value: object) -> float | None:
    return None if value in (None, "") else float(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Paper trade Kalshi BTC 15-minute outcomes.")
    parser.add_argument("--database", default="data/scanner.db")
    parser.add_argument("--equity", type=float, default=1000)
    parser.add_argument("--duration", type=float)
    parser.add_argument(
        "--strategy",
        choices=("lag", "model-only"),
        default="lag",
        help="Require measured repricing lag or test the same model/risk rules without it.",
    )
    args = parser.parse_args()
    engine = Paper15mEngine(
        Paper15mConfig(
            database=args.database,
            initial_equity=args.equity,
            duration_seconds=args.duration,
            require_lag=args.strategy == "lag",
        )
    )
    signal.signal(signal.SIGINT, engine.stop)
    signal.signal(signal.SIGTERM, engine.stop)
    engine.run()


if __name__ == "__main__":
    main()
