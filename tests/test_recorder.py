from datetime import datetime, timedelta, timezone

from polyscanner.recorder import LiveFeedRecorder, RecorderConfig
from polyscanner.storage import SnapshotStore


class FakeSigner:
    pass


class FakeCoinbase:
    def spot_price(self):
        return 63_620.0


class FakeKalshi:
    def active_bitcoin_markets(self, days=2):
        close = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        return [
            {
                "ticker": ticker,
                "event_ticker": "KXBTC-EVENT",
                "strike_type": "between",
                "floor_strike": floor,
                "cap_strike": floor + 249.99,
                "close_time": close,
                "yes_bid_dollars": "0.10",
                "yes_ask_dollars": "0.12",
                "yes_ask_size_fp": "100",
            }
            for ticker, floor in [
                ("KXBTC-FAR", 60_000),
                ("KXBTC-NEAR", 63_500),
                ("KXBTC-NEXT", 63_750),
            ]
        ]


def test_recorder_selects_nearest_contracts_for_earliest_event(tmp_path):
    recorder = LiveFeedRecorder(
        FakeSigner(),
        RecorderConfig(database=str(tmp_path / "feed.db"), max_markets=2),
        store=SnapshotStore(tmp_path / "feed.db"),
        kalshi=FakeKalshi(),
        coinbase=FakeCoinbase(),
    )
    assert recorder.selected_markets() == ["KXBTC-NEAR", "KXBTC-NEXT"]
