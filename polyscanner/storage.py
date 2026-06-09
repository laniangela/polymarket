from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from polyscanner.models import ProbabilityEstimate, ThresholdContract


class SnapshotStore:
    def __init__(self, path: str | Path = "data/scanner.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS scans ("
                "id INTEGER PRIMARY KEY, scanned_at TEXT NOT NULL, eligible_markets INTEGER NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS estimates ("
                "id INTEGER PRIMARY KEY, calculated_at TEXT NOT NULL, market_id TEXT, slug TEXT, "
                "question TEXT, direction TEXT, strike_usd REAL, expires_at TEXT, spot_usd REAL, "
                "annualized_volatility REAL, modeled_probability REAL, executable_price REAL, "
                "raw_edge REAL, edge_after_fee REAL, cap_strike_usd REAL, yes_ask_size REAL, "
                "rules TEXT, venue TEXT, event_ticker TEXT, event_title TEXT, event_subtitle TEXT)"
            )
            existing = {
                row[1] for row in connection.execute("PRAGMA table_info(estimates)").fetchall()
            }
            for column, column_type in {
                "cap_strike_usd": "REAL",
                "yes_ask_size": "REAL",
                "rules": "TEXT",
                "venue": "TEXT",
                "event_ticker": "TEXT",
                "event_title": "TEXT",
                "event_subtitle": "TEXT",
            }.items():
                if column not in existing:
                    connection.execute(f"ALTER TABLE estimates ADD COLUMN {column} {column_type}")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS recorder_status ("
                "id INTEGER PRIMARY KEY CHECK (id = 1), state TEXT NOT NULL, started_at TEXT, "
                "heartbeat_at TEXT NOT NULL, market_count INTEGER NOT NULL DEFAULT 0, "
                "observation_count INTEGER NOT NULL DEFAULT 0, last_error TEXT)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS feed_observations ("
                "id INTEGER PRIMARY KEY, observed_at TEXT NOT NULL, source TEXT NOT NULL, "
                "market_ticker TEXT, coinbase_spot REAL, brti_value REAL, brti_60s_average REAL, "
                "settlement_window_average REAL, yes_bid REAL, yes_ask REAL, "
                "yes_bid_size REAL, yes_ask_size REAL)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS feed_observations_time "
                "ON feed_observations(observed_at DESC)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def record_scan(self, scanned_at: str, eligible_markets: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO scans(scanned_at, eligible_markets) VALUES (?, ?)",
                (scanned_at, eligible_markets),
            )

    def record_estimate(self, contract: ThresholdContract, estimate: ProbabilityEstimate) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO estimates("
                "calculated_at, market_id, slug, question, direction, strike_usd, expires_at, "
                "spot_usd, annualized_volatility, modeled_probability, executable_price, "
                "raw_edge, edge_after_fee, cap_strike_usd, yes_ask_size, rules, venue, "
                "event_ticker, event_title, event_subtitle"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    estimate.calculated_at.isoformat(),
                    contract.market_id,
                    contract.slug,
                    contract.question,
                    contract.direction.value,
                    contract.strike_usd,
                    contract.expires_at.isoformat(),
                    estimate.spot_usd,
                    estimate.annualized_volatility,
                    estimate.probability,
                    estimate.executable_price,
                    estimate.raw_edge,
                    estimate.edge_after_fee,
                    contract.cap_strike_usd,
                    contract.yes_ask_size,
                    contract.rules,
                    contract.venue,
                    contract.event_ticker,
                    contract.event_title,
                    contract.event_subtitle,
                ),
            )

    def recent_estimates(self, limit: int = 100) -> list[dict[str, object]]:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM estimates ORDER BY calculated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def recent_scans(self, limit: int = 100) -> list[dict[str, object]]:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM scans ORDER BY scanned_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def update_recorder_status(
        self,
        state: str,
        market_count: int,
        observation_count: int,
        started_at: str | None = None,
        last_error: str | None = None,
    ) -> None:
        heartbeat = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO recorder_status("
                "id, state, started_at, heartbeat_at, market_count, observation_count, last_error"
                ") VALUES (1, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET state=excluded.state, "
                "started_at=COALESCE(excluded.started_at, recorder_status.started_at), "
                "heartbeat_at=excluded.heartbeat_at, market_count=excluded.market_count, "
                "observation_count=excluded.observation_count, last_error=excluded.last_error",
                (
                    state,
                    started_at,
                    heartbeat,
                    market_count,
                    observation_count,
                    last_error,
                ),
            )

    def recorder_status(self) -> dict[str, object] | None:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM recorder_status WHERE id = 1"
            ).fetchone()
        return dict(row) if row else None

    def record_feed_observation(
        self,
        *,
        observed_at: str,
        source: str,
        market_ticker: str | None = None,
        coinbase_spot: float | None = None,
        brti_value: float | None = None,
        brti_60s_average: float | None = None,
        settlement_window_average: float | None = None,
        yes_bid: float | None = None,
        yes_ask: float | None = None,
        yes_bid_size: float | None = None,
        yes_ask_size: float | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO feed_observations("
                "observed_at, source, market_ticker, coinbase_spot, brti_value, "
                "brti_60s_average, settlement_window_average, yes_bid, yes_ask, "
                "yes_bid_size, yes_ask_size"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    observed_at,
                    source,
                    market_ticker,
                    coinbase_spot,
                    brti_value,
                    brti_60s_average,
                    settlement_window_average,
                    yes_bid,
                    yes_ask,
                    yes_bid_size,
                    yes_ask_size,
                ),
            )

    def recent_feed_observations(self, limit: int = 100) -> list[dict[str, object]]:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM feed_observations ORDER BY observed_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def feed_observations_since(self, since: str) -> list[dict[str, object]]:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM feed_observations WHERE observed_at >= ? "
                "ORDER BY observed_at ASC",
                (since,),
            ).fetchall()
        return [dict(row) for row in rows]
