from __future__ import annotations

import argparse
import json
import signal
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import websocket

from polyscanner.auth import KalshiCredentials, KalshiRequestSigner
from polyscanner.live import (
    BrtiSnapshot,
    OrderBookQuote,
    OrderBookState,
    parse_brti_message,
    parse_rest_orderbook,
)
from polyscanner.parser import parse_threshold_contract
from polyscanner.providers import CoinbasePublicClient, KalshiPublicClient
from polyscanner.storage import SnapshotStore


@dataclass(frozen=True)
class RecorderConfig:
    database: str = "data/scanner.db"
    max_markets: int = 12
    coinbase_interval: float = 5.0
    heartbeat_interval: float = 5.0
    rest_book_interval: float = 15.0
    reconnect_max: float = 30.0
    duration_seconds: float | None = None


class LiveFeedRecorder:
    URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
    PATH = "/trade-api/ws/v2"

    def __init__(
        self,
        signer: KalshiRequestSigner | None,
        config: RecorderConfig | None = None,
        store: SnapshotStore | None = None,
        kalshi: KalshiPublicClient | None = None,
        coinbase: CoinbasePublicClient | None = None,
    ) -> None:
        self.signer = signer
        self.config = config or RecorderConfig()
        self.store = store or SnapshotStore(self.config.database)
        self.kalshi = kalshi or KalshiPublicClient()
        self.coinbase = coinbase or CoinbasePublicClient()
        self.running = True
        self.observation_count = 0
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.deadline = (
            time.monotonic() + self.config.duration_seconds
            if self.config.duration_seconds is not None
            else None
        )
        self.coinbase_spot: float | None = None
        self.brti: BrtiSnapshot | None = None
        self.books: dict[str, OrderBookState] = {}

    def stop(self, *_: Any) -> None:
        self.running = False

    def selected_markets(self) -> list[str]:
        spot = self.coinbase.spot_price()
        self.coinbase_spot = spot
        contracts = [
            contract
            for payload in self.kalshi.active_bitcoin_markets(days=2)
            if (contract := parse_threshold_contract(payload)) is not None
            and contract.cap_strike_usd is not None
        ]
        contracts.sort(
            key=lambda contract: (
                contract.expires_at,
                abs(((contract.strike_usd + contract.cap_strike_usd) / 2) - spot),
            )
        )
        return [contract.market_id for contract in contracts[: self.config.max_markets]]

    def run(self) -> None:
        markets = self.selected_markets()
        if not markets:
            raise RuntimeError("No near-term Kalshi BTC markets are available to record.")
        self.books = {ticker: OrderBookState() for ticker in markets}
        self.store.update_recorder_status(
            "starting", len(markets), self.observation_count, self.started_at
        )
        if self.signer is None:
            self._record_public_loop(markets)
            self.store.update_recorder_status(
                "stopped", len(markets), self.observation_count
            )
            return
        backoff = 1.0
        while self.running and not self._expired():
            try:
                self._record_connection(markets)
                backoff = 1.0
            except Exception as error:
                self.store.update_recorder_status(
                    "reconnecting",
                    len(markets),
                    self.observation_count,
                    last_error=str(error),
                )
                if not self.running:
                    break
                time.sleep(backoff)
                backoff = min(self.config.reconnect_max, backoff * 2)
        self.store.update_recorder_status(
            "stopped", len(markets), self.observation_count
        )

    def _record_connection(self, markets: list[str]) -> None:
        headers = [
            f"{key}: {value}"
            for key, value in self.signer.headers("GET", self.PATH).items()
        ]
        connection = websocket.create_connection(
            self.URL,
            header=headers,
            timeout=1,
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
            connection.send(
                json.dumps(
                    {
                        "id": 2,
                        "cmd": "subscribe",
                        "params": {
                            "channels": ["orderbook_delta"],
                            "market_tickers": markets,
                        },
                    }
                )
            )
            self.store.update_recorder_status(
                "running", len(markets), self.observation_count
            )
            next_coinbase = 0.0
            next_heartbeat = 0.0
            while self.running:
                if self._expired():
                    self.running = False
                    break
                now = time.monotonic()
                if now >= next_coinbase:
                    self._record_coinbase()
                    next_coinbase = now + self.config.coinbase_interval
                if now >= next_heartbeat:
                    self.store.update_recorder_status(
                        "running", len(markets), self.observation_count
                    )
                    next_heartbeat = now + self.config.heartbeat_interval
                try:
                    payload = json.loads(connection.recv())
                except websocket.WebSocketTimeoutException:
                    continue
                self._handle_message(payload)
        finally:
            connection.close()

    def _record_coinbase(self) -> None:
        self.coinbase_spot = self.coinbase.spot_price()
        self._record("coinbase", datetime.now(timezone.utc))

    def _handle_message(self, payload: dict[str, Any]) -> None:
        brti = parse_brti_message(payload)
        if brti is not None:
            self.brti = brti
            self._record("brti", brti.received_at)
            return
        message = payload.get("msg") or {}
        ticker = str(message.get("market_ticker") or "")
        state = self.books.get(ticker)
        if state is None:
            return
        quote = state.apply(payload)
        if quote is not None:
            self._record_quote(quote)

    def _record_quote(self, quote: OrderBookQuote) -> None:
        self._record(
            "orderbook",
            quote.received_at,
            market_ticker=quote.market_ticker,
            yes_bid=quote.yes_bid,
            yes_ask=quote.yes_ask,
            yes_bid_size=quote.yes_bid_size,
            yes_ask_size=quote.yes_ask_size,
        )

    def _record(
        self,
        source: str,
        observed_at: datetime,
        market_ticker: str | None = None,
        yes_bid: float | None = None,
        yes_ask: float | None = None,
        yes_bid_size: float | None = None,
        yes_ask_size: float | None = None,
    ) -> None:
        self.store.record_feed_observation(
            observed_at=observed_at.isoformat(),
            source=source,
            market_ticker=market_ticker,
            coinbase_spot=self.coinbase_spot,
            brti_value=self.brti.value if self.brti else None,
            brti_60s_average=self.brti.trailing_60s_average if self.brti else None,
            settlement_window_average=(
                self.brti.settlement_window_average if self.brti else None
            ),
            yes_bid=yes_bid,
            yes_ask=yes_ask,
            yes_bid_size=yes_bid_size,
            yes_ask_size=yes_ask_size,
        )
        self.observation_count += 1

    def _record_public_loop(self, markets: list[str]) -> None:
        self.store.update_recorder_status(
            "public-rest", len(markets), self.observation_count
        )
        next_coinbase = 0.0
        next_books = 0.0
        next_heartbeat = 0.0
        while self.running and not self._expired():
            now = time.monotonic()
            if now >= next_coinbase:
                self._record_coinbase()
                next_coinbase = now + self.config.coinbase_interval
            if now >= next_books:
                for ticker in markets:
                    try:
                        quote = parse_rest_orderbook(
                            ticker,
                            self.kalshi.market_book(ticker),
                            datetime.now(timezone.utc),
                        )
                        self._record_quote(quote)
                    except Exception as error:
                        self.store.update_recorder_status(
                            "public-rest",
                            len(markets),
                            self.observation_count,
                            last_error=f"{ticker}: {error}",
                        )
                next_books = now + self.config.rest_book_interval
            if now >= next_heartbeat:
                self.store.update_recorder_status(
                    "public-rest", len(markets), self.observation_count
                )
                next_heartbeat = now + self.config.heartbeat_interval
            time.sleep(0.25)

    def _expired(self) -> bool:
        return self.deadline is not None and time.monotonic() >= self.deadline


def main() -> None:
    parser = argparse.ArgumentParser(description="Record Kalshi BTC and BRTI live feeds.")
    parser.add_argument("--database", default="data/scanner.db")
    parser.add_argument("--max-markets", type=int, default=12)
    parser.add_argument("--duration", type=float)
    args = parser.parse_args()
    credentials = KalshiCredentials.from_env()
    recorder = LiveFeedRecorder(
        KalshiRequestSigner(credentials) if credentials else None,
        RecorderConfig(
            database=args.database,
            max_markets=args.max_markets,
            duration_seconds=args.duration,
        ),
    )
    signal.signal(signal.SIGINT, recorder.stop)
    signal.signal(signal.SIGTERM, recorder.stop)
    recorder.run()


if __name__ == "__main__":
    main()
