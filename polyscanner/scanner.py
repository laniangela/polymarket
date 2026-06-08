from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from polyscanner.models import ProbabilityEstimate, ThresholdContract
from polyscanner.parser import is_bitcoin_market, parse_threshold_contract
from polyscanner.probability import annualized_realized_volatility, estimate_contract
from polyscanner.providers import CoinbasePublicClient, PolymarketUSPublicClient
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
    polymarket: PolymarketUSPublicClient,
    coinbase: CoinbasePublicClient,
    store: SnapshotStore,
) -> ScanResult:
    scanned_at = datetime.now(timezone.utc)
    spot = coinbase.spot_price()
    volatility = annualized_realized_volatility(coinbase.daily_closes())
    catalog_payloads = polymarket.active_crypto_markets()
    bitcoin_payloads = [payload for payload in catalog_payloads if is_bitcoin_market(payload)]
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
        catalog_markets=len(catalog_payloads),
        bitcoin_markets=len(bitcoin_payloads),
        threshold_contracts=len(parsed),
    )
