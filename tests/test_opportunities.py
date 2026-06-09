from datetime import datetime, timedelta, timezone

from polyscanner.models import Direction, ProbabilityEstimate, ThresholdContract
from polyscanner.opportunities import rank_opportunities


def opportunity(ticker: str, event: str, edge: float):
    now = datetime.now(timezone.utc)
    contract = ThresholdContract(
        ticker,
        ticker,
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
        event_ticker=event,
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


def test_ranking_selects_only_best_contract_per_event():
    ranked = rank_opportunities(
        [
            opportunity("LOWER", "EVENT-A", 0.05),
            opportunity("HIGHER", "EVENT-A", 0.08),
            opportunity("OTHER", "EVENT-B", 0.05),
        ],
        equity=1_000,
    )
    assert [item.contract.market_id for item in ranked] == ["HIGHER", "LOWER", "OTHER"]
    assert ranked[0].decision.action == "PAPER TRADE"
    assert ranked[1].decision.action == "WATCH"
    assert ranked[2].decision.action == "PAPER TRADE"
