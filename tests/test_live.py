from polyscanner.live import OrderBookState, parse_brti_message, parse_rest_orderbook


def test_parse_brti_message():
    snapshot = parse_brti_message(
        {
            "type": "cfbenchmarks_value",
            "msg": {
                "index_id": "BRTI",
                "received_at": 1_710_000_000_123,
                "data": '{"type":"value","id":"BRTI","time":1710000000123,"value":"68000.12"}',
                "avg_60s_data": {"value": "67998.40"},
                "last_60s_windowed_average_15min": {"value": "68000.23"},
            },
        }
    )
    assert snapshot is not None
    assert snapshot.value == 68000.12
    assert snapshot.trailing_60s_average == 67998.40
    assert snapshot.settlement_window_average == 68000.23


def test_orderbook_snapshot_and_delta_reconstruct_executable_quote():
    state = OrderBookState()
    quote = state.apply(
        {
            "type": "orderbook_snapshot",
            "msg": {
                "market_ticker": "KXBTC-RANGE",
                "yes_dollars_fp": [["0.31", "12"], ["0.32", "8"]],
                "no_dollars_fp": [["0.64", "20"], ["0.65", "7"]],
            },
        }
    )
    assert quote is not None
    assert quote.yes_bid == 0.32
    assert quote.yes_ask == 0.35
    assert quote.yes_bid_size == 8
    assert quote.yes_ask_size == 7

    quote = state.apply(
        {
            "type": "orderbook_delta",
            "msg": {
                "market_ticker": "KXBTC-RANGE",
                "side": "no",
                "price_dollars": "0.65",
                "delta_fp": "-7",
            },
        }
    )
    assert quote is not None
    assert quote.yes_ask == 0.36


def test_parse_public_rest_orderbook():
    quote = parse_rest_orderbook(
        "KXBTC-RANGE",
        {
            "orderbook_fp": {
                "yes_dollars": [["0.31", "12.00"]],
                "no_dollars": [["0.65", "7.00"]],
            }
        },
    )
    assert quote.yes_bid == 0.31
    assert quote.yes_ask == 0.35
