from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from polyscanner.storage import SnapshotStore


@dataclass(frozen=True)
class SettlementControls:
    max_brti_age_seconds: float = 10
    max_basis_usd: float = 30
    near_expiry_seconds: float = 120
    minimum_buffer_usd: float = 25


@dataclass(frozen=True)
class SettlementState:
    allowed: bool
    reason: str
    observed_at: datetime | None = None
    brti_value: float | None = None
    brti_60s_average: float | None = None
    settlement_window_average: float | None = None
    age_seconds: float | None = None
    coinbase_basis_usd: float | None = None
    reference_value: float | None = None
    target_buffer_usd: float | None = None


class SettlementGuard:
    def __init__(
        self,
        store: SnapshotStore,
        controls: SettlementControls | None = None,
    ) -> None:
        self.store = store
        self.controls = controls or SettlementControls()

    def evaluate(
        self,
        *,
        now: datetime,
        closes_at: datetime,
        target_price: float,
        coinbase_spot: float,
        side: str | None,
    ) -> SettlementState:
        row = self.store.latest_brti_observation()
        if row is None:
            return SettlementState(False, "No authenticated BRTI settlement feed is available.")
        observed_at = _timestamp(row["observed_at"])
        age = max(0.0, (now - observed_at).total_seconds())
        values = {
            "observed_at": observed_at,
            "brti_value": _float(row.get("brti_value")),
            "brti_60s_average": _float(row.get("brti_60s_average")),
            "settlement_window_average": _float(row.get("settlement_window_average")),
            "age_seconds": age,
        }
        if age > self.controls.max_brti_age_seconds:
            return SettlementState(False, f"BRTI is stale ({age:.1f}s old).", **values)
        brti = values["brti_value"]
        trailing = values["brti_60s_average"]
        if brti is None or trailing is None:
            return SettlementState(False, "BRTI value or trailing 60-second average is missing.", **values)
        basis = coinbase_spot - brti
        values["coinbase_basis_usd"] = basis
        if abs(basis) > self.controls.max_basis_usd:
            return SettlementState(
                False,
                f"Coinbase/BRTI basis is too wide (${basis:+,.2f}).",
                **values,
            )
        seconds_remaining = (closes_at - now).total_seconds()
        settlement_average = values["settlement_window_average"]
        reference = (
            settlement_average
            if seconds_remaining <= 60 and settlement_average is not None
            else trailing
        )
        buffer = reference - target_price
        values["reference_value"] = reference
        values["target_buffer_usd"] = buffer
        if side is not None and seconds_remaining <= self.controls.near_expiry_seconds:
            required = self.controls.minimum_buffer_usd
            side_supported = buffer >= required if side == "yes" else buffer <= -required
            if not side_supported:
                return SettlementState(
                    False,
                    f"BRTI settlement reference is only ${buffer:+,.2f} from the target for {side.upper()}.",
                    **values,
                )
        return SettlementState(True, "Fresh BRTI settlement evidence passes all controls.", **values)


def _timestamp(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)


def _float(value: object) -> float | None:
    return None if value in (None, "") else float(value)
