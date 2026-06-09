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
