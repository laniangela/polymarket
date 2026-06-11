from datetime import datetime, timedelta, timezone

from polyscanner.settlement import SettlementGuard
from polyscanner.storage import SnapshotStore


def record_brti(store, observed_at, *, brti=62_200, trailing=62_190, settlement=62_185):
    store.record_feed_observation(
        observed_at=observed_at.isoformat(),
        source="brti",
        coinbase_spot=brti,
        brti_value=brti,
        brti_60s_average=trailing,
        settlement_window_average=settlement,
    )


def test_settlement_guard_rejects_missing_brti(tmp_path):
    now = datetime.now(timezone.utc)
    state = SettlementGuard(SnapshotStore(tmp_path / "feed.db")).evaluate(
        now=now,
        closes_at=now + timedelta(seconds=90),
        target_price=62_000,
        coinbase_spot=62_200,
        side="yes",
    )
    assert not state.allowed
    assert "No authenticated BRTI" in state.reason


def test_settlement_guard_rejects_stale_brti(tmp_path):
    now = datetime.now(timezone.utc)
    store = SnapshotStore(tmp_path / "feed.db")
    record_brti(store, now - timedelta(seconds=20))
    state = SettlementGuard(store).evaluate(
        now=now,
        closes_at=now + timedelta(seconds=90),
        target_price=62_000,
        coinbase_spot=62_200,
        side="yes",
    )
    assert not state.allowed
    assert "stale" in state.reason


def test_settlement_guard_rejects_wide_coinbase_basis(tmp_path):
    now = datetime.now(timezone.utc)
    store = SnapshotStore(tmp_path / "feed.db")
    record_brti(store, now, brti=62_100)
    state = SettlementGuard(store).evaluate(
        now=now,
        closes_at=now + timedelta(minutes=5),
        target_price=62_000,
        coinbase_spot=62_200,
        side="yes",
    )
    assert not state.allowed
    assert "basis" in state.reason


def test_settlement_guard_uses_final_window_and_requires_buffer(tmp_path):
    now = datetime.now(timezone.utc)
    store = SnapshotStore(tmp_path / "feed.db")
    record_brti(store, now, settlement=62_010)
    state = SettlementGuard(store).evaluate(
        now=now,
        closes_at=now + timedelta(seconds=45),
        target_price=62_000,
        coinbase_spot=62_200,
        side="yes",
    )
    assert not state.allowed
    assert state.reference_value == 62_010
    assert state.target_buffer_usd == 10


def test_settlement_guard_allows_fresh_supported_side(tmp_path):
    now = datetime.now(timezone.utc)
    store = SnapshotStore(tmp_path / "feed.db")
    record_brti(store, now, settlement=62_100)
    state = SettlementGuard(store).evaluate(
        now=now,
        closes_at=now + timedelta(seconds=45),
        target_price=62_000,
        coinbase_spot=62_205,
        side="yes",
    )
    assert state.allowed
    assert state.coinbase_basis_usd == 5
