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


def test_parser_extracts_kalshi_range_and_rules():
    contract = parse_threshold_contract(
        {
            "ticker": "KXBTC-26JUN0917-B63625",
            "title": "Bitcoin price range on Jun 9, 2026?",
            "subtitle": "$63,500 to 63,749.99",
            "strike_type": "between",
            "floor_strike": 63500,
            "cap_strike": 63749.99,
            "close_time": "2026-06-09T21:00:00Z",
            "yes_bid_dollars": "0.0600",
            "yes_ask_dollars": "0.0800",
            "yes_ask_size_fp": "490.00",
            "rules_primary": "BRTI average must be in range.",
        }
    )
    assert contract is not None
    assert contract.direction == Direction.BETWEEN
    assert contract.cap_strike_usd == 63749.99
    assert contract.yes_ask_size == 490
    assert contract.rules == "BRTI average must be in range."
