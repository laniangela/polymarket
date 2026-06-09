from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import websocket

from polyscanner.auth import KalshiRequestSigner


@dataclass(frozen=True)
class BrtiSnapshot:
    value: float
    trailing_60s_average: float | None
    settlement_window_average: float | None
    received_at: datetime


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
        )
        try:
            connection.send(
                json.dumps(
                    {
                        "id": 1,
                        "cmd": "subscribe",
                        "params": {
                            "channels": ["cfbenchmarks_value"],
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
