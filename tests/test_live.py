from polyscanner.live import parse_brti_message


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
