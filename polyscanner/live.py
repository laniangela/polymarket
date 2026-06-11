from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import websocket
import certifi

from polyscanner.auth import KalshiRequestSigner


@dataclass(frozen=True)
class BrtiSnapshot:
    value: float
    trailing_60s_average: float | None
    settlement_window_average: float | None
    received_at: datetime


@dataclass(frozen=True)
class OrderBookQuote:
    market_ticker: str
    yes_bid: float | None
    yes_ask: float | None
    yes_bid_size: float | None
    yes_ask_size: float | None
    received_at: datetime


class OrderBookState:
    def __init__(self) -> None:
        self.yes: dict[float, float] = {}
        self.no: dict[float, float] = {}

    def apply(self, payload: dict[str, Any]) -> OrderBookQuote | None:
        message_type = payload.get("type")
        message = payload.get("msg") or {}
        market_ticker = str(message.get("market_ticker") or "")
        if not market_ticker:
            return None
        if message_type == "orderbook_snapshot":
            self.yes = _levels(message.get("yes_dollars_fp") or [])
            self.no = _levels(message.get("no_dollars_fp") or [])
        elif message_type == "orderbook_delta":
            side = str(message.get("side") or "")
            levels = self.yes if side == "yes" else self.no if side == "no" else None
            if levels is None:
                return None
            price = float(message["price_dollars"])
            size = levels.get(price, 0) + float(message["delta_fp"])
            if size <= 0:
                levels.pop(price, None)
            else:
                levels[price] = size
        else:
            return None
        timestamp_ms = message.get("ts_ms")
        received_at = (
            datetime.fromtimestamp(float(timestamp_ms) / 1000, tz=timezone.utc)
            if timestamp_ms is not None
            else datetime.now(timezone.utc)
        )
        yes_bid = max(self.yes, default=None)
        no_bid = max(self.no, default=None)
        return OrderBookQuote(
            market_ticker=market_ticker,
            yes_bid=yes_bid,
            yes_ask=(1 - no_bid) if no_bid is not None else None,
            yes_bid_size=self.yes.get(yes_bid) if yes_bid is not None else None,
            yes_ask_size=self.no.get(no_bid) if no_bid is not None else None,
            received_at=received_at,
        )


def parse_rest_orderbook(
    market_ticker: str,
    payload: dict[str, Any],
    observed_at: datetime | None = None,
) -> OrderBookQuote:
    book = payload.get("orderbook_fp") or {}
    state = OrderBookState()
    quote = state.apply(
        {
            "type": "orderbook_snapshot",
            "msg": {
                "market_ticker": market_ticker,
                "yes_dollars_fp": book.get("yes_dollars") or [],
                "no_dollars_fp": book.get("no_dollars") or [],
            },
        }
    )
    if quote is None:
        raise ValueError(f"Invalid Kalshi order book for {market_ticker}")
    if observed_at is None:
        return quote
    return OrderBookQuote(
        market_ticker=quote.market_ticker,
        yes_bid=quote.yes_bid,
        yes_ask=quote.yes_ask,
        yes_bid_size=quote.yes_bid_size,
        yes_ask_size=quote.yes_ask_size,
        received_at=observed_at,
    )


def parse_brti_message(payload: dict[str, Any]) -> BrtiSnapshot | None:
    if payload.get("type") != "cfbenchmarks_value":
        return None
    message = payload.get("msg") or {}
    if message.get("index_id") != "BRTI":
        return None
    data = json.loads(message.get("data") or "{}")
    if data.get("value") is None:
        return None
    received_ms = int(message.get("received_at") or data.get("time"))
    trailing = message.get("avg_60s_data") or {}
    settlement = message.get("last_60s_windowed_average_15min") or {}
    return BrtiSnapshot(
        value=float(data["value"]),
        trailing_60s_average=_optional_float(trailing.get("value")),
        settlement_window_average=_optional_float(settlement.get("value")),
        received_at=datetime.fromtimestamp(received_ms / 1000, tz=timezone.utc),
    )


class KalshiLiveClient:
    URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
    PATH = "/trade-api/ws/v2"

    def __init__(self, signer: KalshiRequestSigner, timeout: int = 8) -> None:
        self.signer = signer
        self.timeout = timeout

    def latest_brti(self) -> BrtiSnapshot:
        headers = [
            f"{key}: {value}"
            for key, value in self.signer.headers("GET", self.PATH).items()
        ]
        connection = websocket.create_connection(
            self.URL,
            header=headers,
            timeout=self.timeout,
            sslopt={"ca_certs": certifi.where()},
        )
        try:
            connection.send(
                json.dumps(
                    {
                        "id": 1,
                        "cmd": "subscribe",
                        "params": {
                            "channels": ["cfbenchmarks_value"],
                            "index_ids": ["BRTI"],
                        },
                    }
                )
            )
            for _ in range(20):
                snapshot = parse_brti_message(json.loads(connection.recv()))
                if snapshot is not None:
                    return snapshot
        finally:
            connection.close()
        raise TimeoutError("No BRTI update arrived from Kalshi.")


def _optional_float(value: Any) -> float | None:
    return None if value in (None, "") else float(value)


def _levels(rows: list[list[Any]]) -> dict[float, float]:
    return {
        float(price): float(size)
        for price, size in rows
        if float(size) > 0
    }
