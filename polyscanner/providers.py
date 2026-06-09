from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import requests

from polyscanner.auth import KalshiRequestSigner


class KalshiPublicClient:
    BASE_URL = "https://external-api.kalshi.com/trade-api/v2"

    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout

    def active_bitcoin_markets(self, days: int = 14) -> list[dict[str, Any]]:
        response = requests.get(
            f"{self.BASE_URL}/events",
            params={"limit": 200, "status": "open", "series_ticker": "KXBTC"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=days)
        events = []
        for event in response.json().get("events", []):
            strike_raw = event.get("strike_date")
            if not strike_raw:
                continue
            strike_date = datetime.fromisoformat(str(strike_raw).replace("Z", "+00:00"))
            if now <= strike_date <= cutoff:
                events.append(event)
        markets: list[dict[str, Any]] = []
        for event in events:
            market_response = requests.get(
                f"{self.BASE_URL}/markets",
                params={"event_ticker": event["event_ticker"], "limit": 1000},
                timeout=self.timeout,
            )
            market_response.raise_for_status()
            for market in market_response.json().get("markets", []):
                market["_event_title"] = event.get("title", "")
                market["_event_subtitle"] = event.get("sub_title", "")
                markets.append(market)
        return markets

    def market_book(self, slug: str) -> dict[str, Any]:
        response = requests.get(
            f"{self.BASE_URL}/markets/{slug}/orderbook",
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()


class KalshiAccountClient:
    BASE_URL = KalshiPublicClient.BASE_URL
    API_PATH = "/trade-api/v2"

    def __init__(self, signer: KalshiRequestSigner, timeout: int = 20) -> None:
        self.signer = signer
        self.timeout = timeout

    def balance(self) -> dict[str, Any]:
        return self._get("/portfolio/balance")

    def positions(self, limit: int = 200) -> dict[str, Any]:
        return self._get("/portfolio/positions", params={"limit": limit})

    def _get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        path = f"{self.API_PATH}{endpoint}"
        response = requests.get(
            f"{self.BASE_URL}{endpoint}",
            params=params,
            headers=self.signer.headers("GET", path),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()


class CoinbasePublicClient:
    TICKER_URL = "https://api.exchange.coinbase.com/products/BTC-USD/ticker"
    CANDLES_URL = "https://api.exchange.coinbase.com/products/BTC-USD/candles"

    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout
        self.headers = {"User-Agent": "KalshiProbabilityScanner/0.1"}

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

    def intraday_closes(self, hours: int = 24, granularity: int = 300) -> pd.Series:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)
        response = requests.get(
            self.CANDLES_URL,
            params={"granularity": granularity, "start": start.isoformat(), "end": end.isoformat()},
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
