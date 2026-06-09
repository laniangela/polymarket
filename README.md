# Kalshi BTC Probability Scanner

Read-only research software that compares Kalshi Bitcoin price-range contracts
closing within 14 days with a probability estimate derived from Coinbase
BTC-USD spot, realized volatility, and time to expiry.

The first milestone does not place orders and does not require trading
credentials. It records public market snapshots and model outputs to SQLite.

## What it measures

For a contract such as “Will Bitcoin be between $63,500 and $63,749.99 at 5 PM ET?”:

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

Kalshi's public market and order-book REST endpoints do not require an API key.
The scanner discovers open `KXBTC` events and retains those closing within the
next 14 days.

## Safety boundary

- Read-only
- No Kalshi API secrets
- No order placement
- No autonomous trading
- No synthetic replacement for unavailable US markets

Sources:

- Kalshi public API: `https://external-api.kalshi.com/trade-api/v2`
- Coinbase Exchange public candles and ticker APIs
