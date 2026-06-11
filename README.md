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

## Continuous signal recorder

Run the recorder in a second terminal while the dashboard is open:

```bash
source .venv/bin/activate
kalshi-recorder --max-markets 12
```

Without credentials it records Coinbase spot and periodically polls public Kalshi order books. With
credentials it automatically upgrades to synchronized Coinbase, BRTI, and WebSocket order-book
updates. Observations are written to `data/scanner.db`. It follows the nearest price buckets in the
earliest BTC events, maintains a heartbeat, and reconnects with bounded exponential backoff. The
dashboard reports recorder health and recent observations. This process is read-only and has no
order endpoint.

The recorder also samples the Microstructure Agent every 15 seconds per tracked contract. Each
signal is evaluated at 5, 15, 30, and 60-second horizons using the recorded entry ask and first
available exit bid after the horizon. The validation report separates resolved observations from
actually executable outcomes and subtracts estimated fees from hypothetical returns.

## 15-minute outcome settlement test

Run the actual hold-to-settlement strategy for two hours (about eight sequential BTC markets):

```bash
source .venv/bin/activate
kalshi-15m-paper --duration 7200 --equity 1000
```

Run the parallel model-only cohort in another terminal:

```bash
kalshi-15m-paper --database data/model_only.db --strategy model-only --duration 7200 --equity 1000
```

This process evaluates each active `KXBTC15M` market and records why it entered or stayed out. A
paper bet requires at least 4% estimated edge after the entry fee, a spread no wider than 5%, at
least 10 contracts at the ask, and a Microstructure Agent `SUPPORT` verdict based on measured
Coinbase-to-Kalshi repricing delay. Open exposure is capped at 25% of current paper equity. An
entered contract is never resold: it remains open until Kalshi reports the final YES/NO result,
then payout and P&L are calculated from that result. The dashboard shows every market evaluated,
all rejection reasons, open bets, and settled outcomes.

## Current agents

- Contract interpreter: validates event, range, expiry, and settlement rules.
- Quant: compares modeled probability with the executable YES ask after estimated fees.
- Market quality: checks displayed spread and ask size.
- Microstructure: consumes recorded quote freshness, spread, depth imbalance, BTC momentum, quote
  movement, and observed repricing delay. Unrecorded or stale contracts are vetoed, and a paper
  trade requires positive microstructure support rather than a neutral watch verdict.
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
