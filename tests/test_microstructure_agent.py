from datetime import datetime, timedelta, timezone

from polyscanner.agents import MicrostructureAgent
from polyscanner.agents.core import Verdict
from polyscanner.features import MicrostructureFeatureEngine
from polyscanner.models import Direction, ProbabilityEstimate, ThresholdContract
from polyscanner.storage import SnapshotStore


def contract_and_estimate():
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
        0.35,
        0.27,
        0.08,
        0.07,
        now,
    )
    return contract, estimate


def test_microstructure_agent_vetoes_unrecorded_contract(tmp_path):
    contract, estimate = contract_and_estimate()
    agent = MicrostructureAgent(
        MicrostructureFeatureEngine(SnapshotStore(tmp_path / "agent.db"))
    )
    opinion = agent.evaluate(contract, estimate)
    assert opinion.verdict == Verdict.VETO
    assert "No recorded" in opinion.summary
