from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from polyscanner.models import ProbabilityEstimate, ThresholdContract
from polyscanner.parser import parse_threshold_contract
from polyscanner.probability import annualized_realized_volatility, estimate_contract
from polyscanner.providers import CoinbasePublicClient, KalshiPublicClient
from polyscanner.storage import SnapshotStore


@dataclass(frozen=True)
class ScanResult:
    spot_usd: float
    annualized_volatility: float
    contracts: list[tuple[ThresholdContract, ProbabilityEstimate]]
    scanned_at: datetime
    catalog_markets: int
    bitcoin_markets: int
    threshold_contracts: int


def run_scan(
    kalshi: KalshiPublicClient,
    coinbase: CoinbasePublicClient,
    store: SnapshotStore,
) -> ScanResult:
    scanned_at = datetime.now(timezone.utc)
    spot = coinbase.spot_price()
    volatility = annualized_realized_volatility(
        coinbase.intraday_closes(hours=24, granularity=300),
        periods_per_year=365 * 24 * 12,
    )
    bitcoin_payloads = kalshi.active_bitcoin_markets(days=14)
    parsed = [
        contract
        for payload in bitcoin_payloads
        if (contract := parse_threshold_contract(payload)) is not None
    ]
    estimates = [(contract, estimate_contract(contract, spot, volatility, scanned_at)) for contract in parsed]
    store.record_scan(scanned_at.isoformat(), len(estimates))
    for contract, estimate in estimates:
        store.record_estimate(contract, estimate)
    return ScanResult(
        spot,
        volatility,
        estimates,
        scanned_at,
        catalog_markets=len(bitcoin_payloads),
        bitcoin_markets=len(bitcoin_payloads),
        threshold_contracts=len(parsed),
    )
