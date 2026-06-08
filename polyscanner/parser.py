from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from polyscanner.models import Direction, ThresholdContract

BITCOIN_PATTERN = re.compile(r"\b(bitcoin|btc)\b", re.IGNORECASE)
ABOVE_PATTERN = re.compile(
    r"\b(above|over|higher than|greater than|at least|reach(?:es)?)\b", re.IGNORECASE
)
BELOW_PATTERN = re.compile(
    r"\b(below|under|lower than|less than|at most|fall(?:s)? to)\b", re.IGNORECASE
)
PRICE_PATTERN = re.compile(
    r"\$\s*(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*([kK])?"
)


def is_bitcoin_market(payload: dict[str, Any]) -> bool:
    searchable = " ".join(
        str(payload.get(field, "")) for field in ("question", "title", "description", "slug", "category")
    )
    tags = payload.get("tags") or []
    searchable += " " + " ".join(
        str(tag.get("label", "")) + " " + str(tag.get("slug", ""))
        for tag in tags
        if isinstance(tag, dict)
    )
    return bool(BITCOIN_PATTERN.search(searchable))


def parse_threshold_contract(payload: dict[str, Any]) -> ThresholdContract | None:
    if not is_bitcoin_market(payload):
        return None
    question = str(payload.get("question") or payload.get("title") or "")
    price_match = PRICE_PATTERN.search(question)
    if not price_match:
        return None
    amount = float(price_match.group(1).replace(",", ""))
    if price_match.group(2):
        amount *= 1_000
    if ABOVE_PATTERN.search(question):
        direction = Direction.ABOVE
    elif BELOW_PATTERN.search(question):
        direction = Direction.BELOW
    else:
        return None
    expiry_raw = payload.get("endDate") or payload.get("end_date")
    if not expiry_raw:
        return None
    expires_at = datetime.fromisoformat(str(expiry_raw).replace("Z", "+00:00"))
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return ThresholdContract(
        market_id=str(payload.get("id", "")),
        slug=str(payload.get("slug", "")),
        question=question,
        strike_usd=amount,
        direction=direction,
        expires_at=expires_at,
        best_bid=_amount(payload.get("bestBidQuote")),
        best_ask=_amount(payload.get("bestAskQuote")),
        fee_coefficient=float(payload.get("feeCoefficient") or 0),
    )


def _amount(value: Any) -> float | None:
    if isinstance(value, dict):
        value = value.get("value")
    if value in (None, ""):
        return None
    return float(value)
