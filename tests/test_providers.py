from unittest.mock import Mock, patch

from polyscanner.providers import PolymarketUSPublicClient


def test_catalog_filters_unrelated_markets():
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "markets": [
            {"question": "Will Bitcoin be above $64k?", "slug": "btc-64k"},
            {"question": "Will the Yankees win?", "slug": "yankees"},
        ]
    }
    with patch("polyscanner.providers.requests.get", return_value=response):
        markets = PolymarketUSPublicClient().active_bitcoin_markets()
    assert [market["slug"] for market in markets] == ["btc-64k"]
