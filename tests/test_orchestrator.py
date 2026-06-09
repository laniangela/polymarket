from datetime import datetime, timedelta, timezone

from polyscanner.agents import (
    ContractAgent,
    MarketQualityAgent,
    QuantAgent,
    SettlementAgent,
    SkepticAgent,
)
from polyscanner.models import Direction, ProbabilityEstimate, ThresholdContract
from polyscanner.orchestrator import OpportunityOrchestrator


def opportunity(edge: float):
    now = datetime.now(timezone.utc)
    contract = ThresholdContract(
        "KXBTC-X",
        "KXBTC-X",
        "BTC range",
        63_500,
        Direction.BETWEEN,
        now + timedelta(hours=1),
        0.25,
        0.27,
        0.07,
        cap_strike_usd=63_749.99,
        yes_ask_size=100,
        rules="BRTI rules",
        event_ticker="KXBTC-EVENT",
    )
    estimate = ProbabilityEstimate(
        63_000,
        63_500,
        contract.expires_at,
        0.5,
        0.27 + edge,
        0.27,
        edge + 0.01,
        edge,
        now,
    )
    return contract, estimate


def test_strong_edge_sizes_from_equity():
    contract, estimate = opportunity(0.05)
    orchestrator = OpportunityOrchestrator(
        [ContractAgent(), QuantAgent(), MarketQualityAgent(), SettlementAgent(), SkepticAgent()]
    )
    decision = orchestrator.decide(contract, estimate, equity=1_000)
    assert decision.action == "PAPER TRADE"
    assert decision.stake_usd == 75


def test_small_edge_is_rejected_by_quant_agent():
    contract, estimate = opportunity(0.01)
    orchestrator = OpportunityOrchestrator([ContractAgent(), QuantAgent()])
    assert orchestrator.decide(contract, estimate, equity=1_000).action == "REJECT"
