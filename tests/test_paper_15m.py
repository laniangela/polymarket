from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd
import pytest

from polyscanner.agents.core import AgentOpinion, Verdict
from polyscanner.paper_15m import Paper15mConfig, Paper15mEngine
from polyscanner.storage import SnapshotStore


class FakeCoinbase:
    def spot_price(self):
        return 62_200.0

    def intraday_closes(self, hours=24, granularity=300):
        return pd.Series([61_900, 62_000, 62_100, 62_200], dtype=float)


class FakeKalshi:
    def __init__(self, close_time):
        self.close_time = close_time
        self.result = ""
        self.status = "active"

    def active_bitcoin_15m_markets(self):
        return [self.market_payload()]

    def market_payload(self):
        return {
            "ticker": "KXBTC15M-TEST",
            "close_time": self.close_time.isoformat(),
            "floor_strike": 62_000,
            "yes_bid_dollars": "0.39",
            "yes_ask_dollars": "0.40",
            "no_bid_dollars": "0.59",
            "no_ask_dollars": "0.60",
            "yes_ask_size_fp": "100",
        }

    def market_book(self, ticker):
        return {
            "orderbook_fp": {
                "yes_dollars": [["0.39", "1000"]],
                "no_dollars": [["0.60", "1000"]],
            }
        }

    def market(self, ticker):
        payload = self.market_payload()
        payload.update({"status": self.status, "result": self.result})
        return payload


class SupportingAgent:
    def __init__(self, features):
        pass

    def evaluate_features(self, feature):
        return AgentOpinion(
            "Microstructure",
            Verdict.SUPPORT,
            0.8,
            "Measured lag.",
            (),
        )


def test_paper_position_is_held_and_paid_from_final_result(tmp_path):
    now = datetime.now(timezone.utc)
    kalshi = FakeKalshi(now + timedelta(minutes=5))
    store = SnapshotStore(tmp_path / "paper.db")
    engine = Paper15mEngine(
        Paper15mConfig(database=str(tmp_path / "paper.db")),
        store=store,
        kalshi=kalshi,
        coinbase=FakeCoinbase(),
    )
    with patch("polyscanner.paper_15m.MicrostructureAgent", SupportingAgent):
        position_id = engine.observe_and_consider(kalshi.market_payload(), now)
    assert position_id is not None
    position = store.open_paper_15m_positions()[0]
    assert position["side"] == "yes"
    assert position["stake_usd"] == pytest.approx(100)

    kalshi.status = "finalized"
    kalshi.result = "yes"
    assert engine.settle_open_positions(now + timedelta(minutes=6)) == 1
    settled = store.paper_15m_positions()[0]
    assert settled["status"] == "settled"
    assert settled["result"] == "yes"
    assert settled["pnl_usd"] > 0


def test_losing_side_has_negative_settlement_pnl(tmp_path):
    now = datetime.now(timezone.utc)
    kalshi = FakeKalshi(now + timedelta(minutes=5))
    store = SnapshotStore(tmp_path / "paper.db")
    engine = Paper15mEngine(
        Paper15mConfig(database=str(tmp_path / "paper.db")),
        store=store,
        kalshi=kalshi,
        coinbase=FakeCoinbase(),
    )
    with patch("polyscanner.paper_15m.MicrostructureAgent", SupportingAgent):
        engine.observe_and_consider(kalshi.market_payload(), now)
    kalshi.status = "finalized"
    kalshi.result = "no"
    engine.settle_open_positions(now + timedelta(minutes=6))
    settled = store.paper_15m_positions()[0]
    assert settled["payout_usd"] == 0
    assert settled["pnl_usd"] == pytest.approx(-100)
    assert settled["return_pct"] == pytest.approx(-1)


def test_watch_decision_is_recorded_when_lag_is_not_supported(tmp_path):
    now = datetime.now(timezone.utc)
    kalshi = FakeKalshi(now + timedelta(minutes=5))
    store = SnapshotStore(tmp_path / "paper.db")
    engine = Paper15mEngine(
        Paper15mConfig(database=str(tmp_path / "paper.db")),
        store=store,
        kalshi=kalshi,
        coinbase=FakeCoinbase(),
    )
    assert engine.observe_and_consider(kalshi.market_payload(), now) is None
    evaluation = store.paper_15m_evaluations()[0]
    assert evaluation["decision"] == "watch"
    assert "history" in evaluation["reason"].lower()


def test_position_requires_full_size_at_displayed_ask(tmp_path):
    now = datetime.now(timezone.utc)
    kalshi = FakeKalshi(now + timedelta(minutes=5))
    store = SnapshotStore(tmp_path / "paper.db")
    engine = Paper15mEngine(
        Paper15mConfig(database=str(tmp_path / "paper.db"), min_ask_size=1),
        store=store,
        kalshi=kalshi,
        coinbase=FakeCoinbase(),
    )
    kalshi.market_book = lambda ticker: {
        "orderbook_fp": {
            "yes_dollars": [["0.39", "2"]],
            "no_dollars": [["0.60", "2"]],
        }
    }
    with patch("polyscanner.paper_15m.MicrostructureAgent", SupportingAgent):
        assert engine.observe_and_consider(kalshi.market_payload(), now) is None
    evaluation = store.paper_15m_evaluations()[0]
    assert "required contracts" in evaluation["reason"]


def test_model_only_cohort_does_not_require_lag_support(tmp_path):
    now = datetime.now(timezone.utc)
    kalshi = FakeKalshi(now + timedelta(minutes=5))
    store = SnapshotStore(tmp_path / "paper.db")
    engine = Paper15mEngine(
        Paper15mConfig(database=str(tmp_path / "paper.db"), require_lag=False),
        store=store,
        kalshi=kalshi,
        coinbase=FakeCoinbase(),
    )
    position_id = engine.observe_and_consider(kalshi.market_payload(), now)
    assert position_id is not None
    position = store.paper_15m_positions()[0]
    assert position["agent_verdict"] == "not_required"
