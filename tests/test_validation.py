from datetime import datetime, timedelta, timezone

import pytest

from polyscanner.storage import SnapshotStore
from polyscanner.validation import MicrostructureValidator


def quote(store, at, bid=0.30, ask=0.32):
    store.record_feed_observation(
        observed_at=at.isoformat(),
        source="orderbook",
        market_ticker="KXBTC-X",
        coinbase_spot=62_000,
        yes_bid=bid,
        yes_ask=ask,
        yes_bid_size=20,
        yes_ask_size=20,
    )


def test_validator_persists_signal_and_scores_due_horizons(tmp_path):
    store = SnapshotStore(tmp_path / "validation.db")
    now = datetime.now(timezone.utc)
    for offset in (-30, -20, -10, 0):
        quote(store, now + timedelta(seconds=offset))
    validator = MicrostructureValidator(
        store,
        horizons=(5, 15),
        sample_interval_seconds=15,
    )
    signal_id = validator.capture("KXBTC-X", now)
    assert signal_id > 0
    assert store.recent_microstructure_signals()[0]["entry_ask"] == 0.32

    assert validator.resolve_due("KXBTC-X", now + timedelta(seconds=6), 0.36) == 1
    summary = store.validation_summary()
    assert summary[0]["horizon_seconds"] == 5
    expected_fees = 0.07 * 0.32 * 0.68 + 0.07 * 0.36 * 0.64
    assert summary[0]["average_net_return"] == pytest.approx(0.04 - expected_fees)
    assert summary[0]["favorable_rate"] == 1


def test_validator_records_unavailable_exit_without_fake_return(tmp_path):
    store = SnapshotStore(tmp_path / "validation.db")
    now = datetime.now(timezone.utc)
    quote(store, now)
    validator = MicrostructureValidator(store, horizons=(5,))
    validator.capture("KXBTC-X", now)
    validator.resolve_due("KXBTC-X", now + timedelta(seconds=6), None)
    summary = store.validation_summary()[0]
    assert summary["outcomes"] == 1
    assert summary["executable"] == 0
    assert summary["average_net_return"] is None


def test_process_quote_respects_sampling_interval(tmp_path):
    store = SnapshotStore(tmp_path / "validation.db")
    now = datetime.now(timezone.utc)
    validator = MicrostructureValidator(
        store,
        horizons=(5,),
        sample_interval_seconds=15,
    )
    quote(store, now)
    validator.process_quote("KXBTC-X", now, 0.30)
    quote(store, now + timedelta(seconds=5))
    validator.process_quote("KXBTC-X", now + timedelta(seconds=5), 0.30)
    assert len(store.recent_microstructure_signals()) == 1
