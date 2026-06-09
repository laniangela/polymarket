from datetime import datetime, timedelta, timezone

import pytest

from polyscanner.features import MicrostructureFeatureEngine
from polyscanner.storage import SnapshotStore


def record(store, at, source, **values):
    store.record_feed_observation(
        observed_at=at.isoformat(),
        source=source,
        **values,
    )


def test_feature_engine_calculates_spread_imbalance_momentum_and_delay(tmp_path):
    store = SnapshotStore(tmp_path / "features.db")
    now = datetime.now(timezone.utc)
    record(store, now - timedelta(seconds=50), "coinbase", coinbase_spot=62_000)
    record(
        store,
        now - timedelta(seconds=45),
        "orderbook",
        market_ticker="KXBTC-X",
        coinbase_spot=62_000,
        yes_bid=0.30,
        yes_ask=0.34,
        yes_bid_size=30,
        yes_ask_size=10,
    )
    record(store, now - timedelta(seconds=30), "coinbase", coinbase_spot=62_030)
    record(
        store,
        now - timedelta(seconds=18),
        "orderbook",
        market_ticker="KXBTC-X",
        coinbase_spot=62_030,
        yes_bid=0.32,
        yes_ask=0.36,
        yes_bid_size=25,
        yes_ask_size=15,
    )
    record(store, now - timedelta(seconds=5), "coinbase", coinbase_spot=62_040)
    feature = MicrostructureFeatureEngine(store, now=now).calculate("KXBTC-X")
    assert feature.spread == pytest.approx(0.04)
    assert feature.depth_imbalance == pytest.approx(0.25)
    assert feature.coinbase_momentum_60s_bps == pytest.approx(6.4516, rel=1e-3)
    assert feature.quote_change_60s_points == pytest.approx(0.02)
    assert feature.repricing_delay_seconds == 12
    assert feature.freshness_seconds == 18


def test_feature_engine_reports_missing_market_evidence(tmp_path):
    feature = MicrostructureFeatureEngine(
        SnapshotStore(tmp_path / "features.db")
    ).calculate("KXBTC-MISSING")
    assert feature.latest_observation_at is None
    assert feature.quote_observations == 0
