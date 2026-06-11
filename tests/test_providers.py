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


def test_kalshi_client_fetches_active_15m_bitcoin_market():
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "events": [
            {
                "markets": [
                    {"ticker": "ACTIVE", "status": "active"},
                    {"ticker": "FUTURE", "status": "initialized"},
                ]
            }
        ]
    }
    with patch("polyscanner.providers.requests.get", return_value=response) as request:
        markets = KalshiPublicClient().active_bitcoin_15m_markets()
    assert markets == [{"ticker": "ACTIVE", "status": "active"}]
    assert request.call_args.kwargs["params"]["series_ticker"] == "KXBTC15M"
