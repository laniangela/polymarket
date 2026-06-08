# Polymarket US BTC Probability Scanner

Read-only research software that compares Polymarket US Bitcoin threshold
contracts with a probability estimate derived from Coinbase BTC-USD spot,
realized volatility, and time to expiry.

The first milestone does not place orders and does not require trading
credentials. It records public market snapshots and model outputs to SQLite.

## What it measures

For a contract such as “Will Bitcoin be above $64,000 at 4 PM ET?”:

```text
estimated edge = modeled probability - executable YES ask
```

The modeled probability is a deliberately simple lognormal estimate using
recent realized volatility. It is a benchmark, not a guarantee or trading
recommendation.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
streamlit run app.py
```

The Polymarket US public catalog currently may contain no active crypto
contracts. In that case the dashboard reports zero eligible markets and stores
the observation without substituting international or synthetic markets.

## Safety boundary

- Read-only
- No API secrets
- No order placement
- No autonomous trading
- No synthetic replacement for unavailable US markets

Sources:

- Polymarket US public API: `https://gateway.polymarket.us`
- Coinbase Exchange public candles and ticker APIs
