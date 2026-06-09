from __future__ import annotations

from dataclasses import dataclass

from polyscanner.agents.core import AgentOpinion, Verdict
from polyscanner.models import ProbabilityEstimate, ThresholdContract


@dataclass(frozen=True)
class RiskPolicy:
    standard_allocation: float = 0.05
    strong_allocation: float = 0.075
    exceptional_allocation: float = 0.10
    strong_edge: float = 0.04
    exceptional_edge: float = 0.08
    max_event_exposure: float = 0.10
    max_total_exposure: float = 0.25


@dataclass(frozen=True)
class TradeDecision:
    action: str
    allocation_pct: float
    stake_usd: float
    reasons: tuple[str, ...]
    opinions: tuple[AgentOpinion, ...]


class OpportunityOrchestrator:
    def __init__(self, agents: list[object], policy: RiskPolicy | None = None) -> None:
        self.agents = agents
        self.policy = policy or RiskPolicy()

    def decide(
        self,
        contract: ThresholdContract,
        estimate: ProbabilityEstimate,
        equity: float,
        event_exposure: float = 0,
        total_exposure: float = 0,
    ) -> TradeDecision:
        opinions = tuple(agent.evaluate(contract, estimate) for agent in self.agents)
        vetoes = tuple(opinion.summary for opinion in opinions if opinion.verdict == Verdict.VETO)
        if vetoes:
            return TradeDecision("REJECT", 0, 0, vetoes, opinions)

        edge = estimate.edge_after_fee or 0
        if edge >= self.policy.exceptional_edge:
            allocation = self.policy.exceptional_allocation
        elif edge >= self.policy.strong_edge:
            allocation = self.policy.strong_allocation
        else:
            return TradeDecision(
                "WATCH",
                0,
                0,
                ("Edge has not reached the strong-trade threshold.",),
                opinions,
            )

        event_room = max(0, self.policy.max_event_exposure * equity - event_exposure)
        total_room = max(0, self.policy.max_total_exposure * equity - total_exposure)
        stake = min(allocation * equity, event_room, total_room)
        if stake <= 0:
            return TradeDecision(
                "REJECT",
                0,
                0,
                ("Portfolio exposure limit reached.",),
                opinions,
            )
        return TradeDecision(
            "PAPER TRADE",
            stake / equity,
            stake,
            ("All hard vetoes passed.",),
            opinions,
        )
