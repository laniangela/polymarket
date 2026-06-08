from datetime import timezone

from polyscanner.models import Direction
from polyscanner.parser import is_bitcoin_market, parse_threshold_contract


def test_parser_extracts_above_contract():
    contract = parse_threshold_contract(
        {
            "id": "1",
            "slug": "btc-above-64k",
            "question": "Will Bitcoin be above $64k on June 8?",
            "endDate": "2026-06-08T20:00:00Z",
            "bestBidQuote": {"value": "0.32"},
            "bestAskQuote": {"value": "0.33"},
            "feeCoefficient": 0.05,
        }
    )
    assert contract is not None
    assert contract.strike_usd == 64_000
    assert contract.direction == Direction.ABOVE
    assert contract.best_ask == 0.33
    assert contract.expires_at.tzinfo == timezone.utc


def test_parser_rejects_unrelated_market():
    assert not is_bitcoin_market({"question": "Will AMD exceed $200?"})
    assert parse_threshold_contract({"question": "Will Bitcoin dominance rise?"}) is None
