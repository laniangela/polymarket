# Kalshi BTC Agent Control Room

A focused, PolyTerm-style Kalshi monitor for BTC price-range markets. It discovers the next 14 days
of `KXBTC` events, estimates probabilities, ranks executable gaps, runs structured specialist
agents, and sizes paper opportunities as a percentage of account equity.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
streamlit run app.py --server.port 8502
```

Public Kalshi and Coinbase data work without credentials.

## Optional read-only Kalshi connection

Create a Kalshi API key, keep the downloaded RSA private key outside the repository, then copy
`.env.example` to `.env` and set:

```text
KALSHI_ACCESS_KEY_ID=your-key-id
KALSHI_PRIVATE_KEY_PATH=/absolute/path/to/your-private-key.pem
```

The dashboard can then test account balance access and read the live CF Benchmarks BRTI feed used
by Kalshi settlement. It does not contain an order-placement method.

## Current agents

- Contract interpreter: validates event, range, expiry, and settlement rules.
- Quant: compares modeled probability with the executable YES ask after estimated fees.
- Market quality: checks displayed spread and ask size.
- Settlement risk: highlights Coinbase-to-BRTI basis risk.
- Skeptic: challenges contracts near settlement boundaries.

Paper sizing uses 5%, 7.5%, and 10% tiers, at most one selected range per event, and a 25% total
exposure ceiling. Estimates and scans are recorded locally in SQLite for later replay and testing.

## Safety boundary

- Public market data by default
- Optional authenticated account balance and BRTI reads
- No private key contents stored in the repository
- No order placement
- No autonomous trading

Sources:

- Kalshi API: `https://external-api.kalshi.com/trade-api/v2`
- Kalshi WebSocket: `wss://api.elections.kalshi.com/trade-api/ws/v2`
- Coinbase Exchange public candles and ticker APIs
