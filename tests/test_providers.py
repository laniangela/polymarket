from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from polyscanner.providers import KalshiPublicClient


def test_kalshi_client_fetches_only_events_within_14_days():
    now = datetime.now(timezone.utc)
    events_response = Mock()
    events_response.raise_for_status.return_value = None
    events_response.json.return_value = {
        "events": [
            {
                "event_ticker": "KXBTC-NEAR",
                "strike_date": (now + timedelta(days=2)).isoformat(),
            },
            {
                "event_ticker": "KXBTC-FAR",
                "strike_date": (now + timedelta(days=30)).isoformat(),
            },
        ]
    }
    markets_response = Mock()
    markets_response.raise_for_status.return_value = None
    markets_response.json.return_value = {
        "markets": [{"ticker": "KXBTC-NEAR-B64000", "strike_type": "between"}]
    }
    with patch(
        "polyscanner.providers.requests.get",
        side_effect=[events_response, markets_response],
    ) as request:
        markets = KalshiPublicClient().active_bitcoin_markets()
    assert markets[0]["ticker"] == "KXBTC-NEAR-B64000"
    assert request.call_count == 2
