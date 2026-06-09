from __future__ import annotations

from dataclasses import dataclass

from polyscanner.agents import (
    ContractAgent,
    MarketQualityAgent,
    MicrostructureAgent,
    QuantAgent,
    SettlementAgent,
    SkepticAgent,
)
from polyscanner.models import ProbabilityEstimate, ThresholdContract
from polyscanner.orchestrator import OpportunityOrchestrator, TradeDecision
from polyscanner.features import MicrostructureFeatureEngine
from polyscanner.storage import SnapshotStore


@dataclass(frozen=True)
class RankedOpportunity:
    rank: int
    contract: ThresholdContract
    estimate: ProbabilityEstimate
    decision: TradeDecision


def default_orchestrator(store: SnapshotStore | None = None) -> OpportunityOrchestrator:
    agents = [
        ContractAgent(),
        QuantAgent(),
        MarketQualityAgent(),
    ]
    if store is not None:
        agents.append(MicrostructureAgent(MicrostructureFeatureEngine(store)))
    agents.extend(
        [
            SettlementAgent(),
            SkepticAgent(),
        ]
    )
    return OpportunityOrchestrator(
        agents
    )


def rank_opportunities(
    contracts: list[tuple[ThresholdContract, ProbabilityEstimate]],
    equity: float,
    event_exposure: dict[str, float] | None = None,
    total_exposure: float = 0,
    orchestrator: OpportunityOrchestrator | None = None,
    store: SnapshotStore | None = None,
) -> list[RankedOpportunity]:
    engine = orchestrator or default_orchestrator(store)
    exposure_by_event = dict(event_exposure or {})
    selected_events = {
        ticker for ticker, exposure in exposure_by_event.items() if exposure > 0
    }
    running_total = total_exposure
    ranked = sorted(
        contracts,
        key=lambda item: (
            item[1].edge_after_fee
            if item[1].edge_after_fee is not None
            else float("-inf")
        ),
        reverse=True,
    )
    opportunities = []
    for rank, (contract, estimate) in enumerate(ranked, start=1):
        event_already_selected = contract.event_ticker in selected_events
        decision = engine.decide(
            contract,
            estimate,
            equity,
            event_exposure=(
                0
                if event_already_selected
                else exposure_by_event.get(contract.event_ticker, 0)
            ),
            total_exposure=running_total,
        )
        if decision.action == "PAPER TRADE" and event_already_selected:
            decision = TradeDecision(
                "WATCH",
                0,
                0,
                ("A stronger price bucket from this event is already selected.",),
                decision.opinions,
            )
        elif decision.action == "PAPER TRADE":
            selected_events.add(contract.event_ticker)
            exposure_by_event[contract.event_ticker] = (
                exposure_by_event.get(contract.event_ticker, 0) + decision.stake_usd
            )
            running_total += decision.stake_usd
        opportunities.append(RankedOpportunity(rank, contract, estimate, decision))
    return opportunities
