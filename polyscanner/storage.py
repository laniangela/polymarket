from __future__ import annotations

import sqlite3
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
