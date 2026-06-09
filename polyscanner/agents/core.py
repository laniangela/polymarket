from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from polyscanner.models import ProbabilityEstimate, ThresholdContract


class Verdict(StrEnum):
    SUPPORT = "support"
    WATCH = "watch"
    VETO = "veto"


@dataclass(frozen=True)
class AgentOpinion:
    agent: str
    verdict: Verdict
    score: float
    summary: str
    evidence: tuple[str, ...]


class ContractAgent:
    name = "Contract interpreter"

    def evaluate(self, contract: ThresholdContract, _: ProbabilityEstimate) -> AgentOpinion:
        missing = []
        if not contract.rules:
            missing.append("settlement rules")
        if not contract.event_ticker:
            missing.append("parent event")
        if contract.cap_strike_usd is None:
            missing.append("range cap")
        if missing:
            return AgentOpinion(
                self.name,
                Verdict.VETO,
                0,
                "Contract structure is incomplete.",
                (f"Missing: {', '.join(missing)}",),
            )
        return AgentOpinion(
            self.name,
            Verdict.SUPPORT,
            1,
            "Range, event, close time, and BRTI rules are explicit.",
            (
                f"Event: {contract.event_ticker}",
                f"Range: ${contract.strike_usd:,.0f}-${contract.cap_strike_usd:,.2f}",
            ),
        )


class QuantAgent:
    name = "Quant"

    def evaluate(self, _: ThresholdContract, estimate: ProbabilityEstimate) -> AgentOpinion:
        edge = estimate.edge_after_fee
        if edge is None:
            return AgentOpinion(self.name, Verdict.VETO, 0, "No executable ask.", ())
        if edge >= 0.08:
            verdict = Verdict.SUPPORT
            summary = "Exceptional modeled edge after estimated fees."
        elif edge >= 0.04:
            verdict = Verdict.SUPPORT
            summary = "Strong modeled edge after estimated fees."
        elif edge >= 0.02:
            verdict = Verdict.WATCH
            summary = "Positive edge, but below the strong-trade threshold."
        else:
            verdict = Verdict.VETO
            summary = "Modeled edge is too small."
        return AgentOpinion(
            self.name,
            verdict,
            edge,
            summary,
            (
                f"Modeled probability: {estimate.probability:.1%}",
                f"Executable YES ask: {estimate.executable_price:.1%}",
                f"After-fee gap: {edge:+.1%}",
            ),
        )


class MarketQualityAgent:
    name = "Market quality"

    def evaluate(self, contract: ThresholdContract, _: ProbabilityEstimate) -> AgentOpinion:
        if contract.best_ask is None or contract.yes_ask_size is None:
            return AgentOpinion(self.name, Verdict.VETO, 0, "Quote or size is missing.", ())
        spread = (
            contract.best_ask - contract.best_bid
            if contract.best_bid is not None
            else contract.best_ask
        )
        if contract.yes_ask_size < 10:
            return AgentOpinion(
                self.name,
                Verdict.VETO,
                0,
                "Displayed ask size is too small for reliable execution.",
                (f"Ask size: {contract.yes_ask_size:,.0f}",),
            )
        if spread > 0.05:
            return AgentOpinion(
                self.name,
                Verdict.WATCH,
                max(0, 1 - spread),
                "Wide displayed spread raises execution risk.",
                (f"Spread: {spread:.1%}",),
            )
        return AgentOpinion(
            self.name,
            Verdict.SUPPORT,
            1,
            "Displayed spread and ask size pass initial checks.",
            (f"Spread: {spread:.1%}", f"Ask size: {contract.yes_ask_size:,.0f}"),
        )


class SettlementAgent:
    name = "Settlement risk"

    def evaluate(self, contract: ThresholdContract, _: ProbabilityEstimate) -> AgentOpinion:
        return AgentOpinion(
            self.name,
            Verdict.WATCH,
            0.5,
            "Coinbase is only a reference; Kalshi settles on the 60-second BRTI average.",
            (
                "Reference feed: Coinbase BTC-USD",
                "Settlement feed: CF Benchmarks BRTI",
                "Boundary outcomes carry basis risk.",
            ),
        )


class SkepticAgent:
    name = "Skeptic"

    def evaluate(self, contract: ThresholdContract, estimate: ProbabilityEstimate) -> AgentOpinion:
        distance_to_nearest_boundary = min(
            abs(estimate.spot_usd - contract.strike_usd),
            abs(estimate.spot_usd - (contract.cap_strike_usd or contract.strike_usd)),
        )
        if distance_to_nearest_boundary < 50:
            return AgentOpinion(
                self.name,
                Verdict.WATCH,
                0.25,
                "Spot is very close to a settlement boundary.",
                (f"Nearest boundary distance: ${distance_to_nearest_boundary:,.2f}",),
            )
        return AgentOpinion(
            self.name,
            Verdict.SUPPORT,
            0.75,
            "No immediate boundary-specific objection found.",
            (f"Nearest boundary distance: ${distance_to_nearest_boundary:,.2f}",),
        )
