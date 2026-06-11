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
            connection.execute(
                "CREATE TABLE IF NOT EXISTS microstructure_signals ("
                "id INTEGER PRIMARY KEY, evaluated_at TEXT NOT NULL, market_ticker TEXT NOT NULL, "
                "verdict TEXT NOT NULL, score REAL NOT NULL, summary TEXT NOT NULL, "
                "entry_bid REAL, entry_ask REAL, spread REAL, bid_size REAL, ask_size REAL, "
                "depth_imbalance REAL, coinbase_momentum_60s_bps REAL, "
                "quote_change_60s_points REAL, repricing_delay_seconds REAL, "
                "freshness_seconds REAL, quote_observations INTEGER NOT NULL, "
                "coinbase_observations INTEGER NOT NULL)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS microstructure_signals_market_time "
                "ON microstructure_signals(market_ticker, evaluated_at DESC)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS signal_outcomes ("
                "id INTEGER PRIMARY KEY, signal_id INTEGER NOT NULL, horizon_seconds INTEGER NOT NULL, "
                "target_at TEXT NOT NULL, observed_at TEXT, elapsed_seconds REAL, exit_bid REAL, "
                "gross_return REAL, estimated_fees REAL, net_return REAL, favorable INTEGER, "
                "FOREIGN KEY(signal_id) REFERENCES microstructure_signals(id), "
                "UNIQUE(signal_id, horizon_seconds))"
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

    def record_microstructure_signal(
        self,
        *,
        evaluated_at: str,
        market_ticker: str,
        verdict: str,
        score: float,
        summary: str,
        entry_bid: float | None,
        entry_ask: float | None,
        spread: float | None,
        bid_size: float | None,
        ask_size: float | None,
        depth_imbalance: float | None,
        coinbase_momentum_60s_bps: float | None,
        quote_change_60s_points: float | None,
        repricing_delay_seconds: float | None,
        freshness_seconds: float | None,
        quote_observations: int,
        coinbase_observations: int,
    ) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO microstructure_signals("
                "evaluated_at, market_ticker, verdict, score, summary, entry_bid, entry_ask, "
                "spread, bid_size, ask_size, depth_imbalance, coinbase_momentum_60s_bps, "
                "quote_change_60s_points, repricing_delay_seconds, freshness_seconds, "
                "quote_observations, coinbase_observations"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    evaluated_at,
                    market_ticker,
                    verdict,
                    score,
                    summary,
                    entry_bid,
                    entry_ask,
                    spread,
                    bid_size,
                    ask_size,
                    depth_imbalance,
                    coinbase_momentum_60s_bps,
                    quote_change_60s_points,
                    repricing_delay_seconds,
                    freshness_seconds,
                    quote_observations,
                    coinbase_observations,
                ),
            )
            return int(cursor.lastrowid)

    def create_signal_outcome(
        self,
        signal_id: int,
        horizon_seconds: int,
        target_at: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO signal_outcomes("
                "signal_id, horizon_seconds, target_at"
                ") VALUES (?, ?, ?)",
                (signal_id, horizon_seconds, target_at),
            )

    def latest_signal_time(self, market_ticker: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT evaluated_at FROM microstructure_signals "
                "WHERE market_ticker = ? ORDER BY evaluated_at DESC LIMIT 1",
                (market_ticker,),
            ).fetchone()
        return str(row[0]) if row else None

    def pending_signal_outcomes(
        self,
        market_ticker: str,
        observed_at: str,
    ) -> list[dict[str, object]]:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT o.*, s.evaluated_at, s.entry_ask FROM signal_outcomes o "
                "JOIN microstructure_signals s ON s.id = o.signal_id "
                "WHERE s.market_ticker = ? AND o.observed_at IS NULL AND o.target_at <= ? "
                "ORDER BY o.target_at ASC",
                (market_ticker, observed_at),
            ).fetchall()
        return [dict(row) for row in rows]

    def resolve_signal_outcome(
        self,
        outcome_id: int,
        *,
        observed_at: str,
        elapsed_seconds: float,
        exit_bid: float | None,
        gross_return: float | None,
        estimated_fees: float | None,
        net_return: float | None,
        favorable: bool | None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE signal_outcomes SET observed_at = ?, elapsed_seconds = ?, exit_bid = ?, "
                "gross_return = ?, estimated_fees = ?, net_return = ?, favorable = ? WHERE id = ?",
                (
                    observed_at,
                    elapsed_seconds,
                    exit_bid,
                    gross_return,
                    estimated_fees,
                    net_return,
                    None if favorable is None else int(favorable),
                    outcome_id,
                ),
            )

    def validation_summary(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT s.verdict, o.horizon_seconds, COUNT(*) AS outcomes, "
                "SUM(CASE WHEN o.net_return IS NOT NULL THEN 1 ELSE 0 END) AS executable, "
                "AVG(o.favorable) AS favorable_rate, AVG(o.net_return) AS average_net_return, "
                "AVG(o.elapsed_seconds) AS average_elapsed_seconds "
                "FROM signal_outcomes o JOIN microstructure_signals s ON s.id = o.signal_id "
                "WHERE o.observed_at IS NOT NULL GROUP BY s.verdict, o.horizon_seconds "
                "ORDER BY s.verdict, o.horizon_seconds"
            ).fetchall()
        return [dict(row) for row in rows]

    def recent_microstructure_signals(self, limit: int = 100) -> list[dict[str, object]]:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM microstructure_signals ORDER BY evaluated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def validation_counts(self) -> dict[str, int]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT "
                "(SELECT COUNT(*) FROM microstructure_signals) AS signals, "
                "(SELECT COUNT(*) FROM microstructure_signals WHERE verdict = 'support') AS supports, "
                "(SELECT COUNT(*) FROM signal_outcomes WHERE observed_at IS NOT NULL) AS resolved, "
                "(SELECT COUNT(*) FROM signal_outcomes WHERE net_return IS NOT NULL) AS executable"
            ).fetchone()
        return {
            "signals": int(row[0]),
            "supports": int(row[1]),
            "resolved": int(row[2]),
            "executable": int(row[3]),
        }
