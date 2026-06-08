from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import requests

from polyscanner.parser import is_bitcoin_market


class PolymarketUSPublicClient:
    BASE_URL = "https://gateway.polymarket.us"

    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout

    def active_crypto_markets(self) -> list[dict[str, Any]]:
        response = requests.get(
            f"{self.BASE_URL}/v1/markets",
            params={"limit": 100, "active": "true", "categories": "crypto"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("markets", [])

    def active_bitcoin_markets(self) -> list[dict[str, Any]]:
        return [market for market in self.active_crypto_markets() if is_bitcoin_market(market)]

    def market_book(self, slug: str) -> dict[str, Any]:
        response = requests.get(
            f"{self.BASE_URL}/v1/markets/{slug}/book",
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()


class CoinbasePublicClient:
    TICKER_URL = "https://api.exchange.coinbase.com/products/BTC-USD/ticker"
    CANDLES_URL = "https://api.exchange.coinbase.com/products/BTC-USD/candles"

    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout
        self.headers = {"User-Agent": "PolymarketProbabilityScanner/0.1"}

    def spot_price(self) -> float:
        response = requests.get(self.TICKER_URL, headers=self.headers, timeout=self.timeout)
        response.raise_for_status()
        return float(response.json()["price"])

    def daily_closes(self, days: int = 31) -> pd.Series:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        response = requests.get(
            self.CANDLES_URL,
            params={"granularity": 86400, "start": start.isoformat(), "end": end.isoformat()},
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        rows = response.json()
        return pd.Series(
            {
                pd.to_datetime(row[0], unit="s", utc=True).tz_localize(None): float(row[4])
                for row in rows
            },
            name="BTC-USD",
        ).sort_index()
