from datetime import datetime, timedelta, timezone

from polyscanner.models import Direction, ThresholdContract
from polyscanner.probability import estimate_contract
from polyscanner.storage import SnapshotStore


def test_storage_records_estimate(tmp_path):
    store = SnapshotStore(tmp_path / "scanner.db")
    now = datetime.now(timezone.utc)
    contract = ThresholdContract(
        "1", "btc-64k", "Will BTC be above $64k?", 64_000, Direction.ABOVE,
        now + timedelta(hours=1), 0.32, 0.33, 0.05,
    )
    store.record_estimate(contract, estimate_contract(contract, 63_700, 0.60, now))
    rows = store.recent_estimates()
    assert len(rows) == 1
    assert rows[0]["slug"] == "btc-64k"
    assert rows[0]["venue"] == "Kalshi"


def test_storage_records_zero_market_scan(tmp_path):
    store = SnapshotStore(tmp_path / "scanner.db")
    store.record_scan("2026-06-08T22:00:00+00:00", 0)
    rows = store.recent_scans()
    assert rows[0]["eligible_markets"] == 0


def test_storage_records_feed_and_recorder_heartbeat(tmp_path):
    store = SnapshotStore(tmp_path / "scanner.db")
    store.update_recorder_status(
        "running",
        market_count=12,
        observation_count=4,
        started_at="2026-06-09T20:00:00+00:00",
    )
    store.record_feed_observation(
        observed_at="2026-06-09T20:00:01+00:00",
        source="orderbook",
        market_ticker="KXBTC-RANGE",
        coinbase_spot=62000,
        brti_value=61998,
        yes_bid=0.31,
        yes_ask=0.33,
    )
    assert store.recorder_status()["state"] == "running"
    assert store.recorder_status()["market_count"] == 12
    row = store.recent_feed_observations()[0]
    assert row["market_ticker"] == "KXBTC-RANGE"
    assert row["brti_value"] == 61998
