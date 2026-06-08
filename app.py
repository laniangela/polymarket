from __future__ import annotations

import pandas as pd
import streamlit as st

from polyscanner.providers import CoinbasePublicClient, PolymarketUSPublicClient
from polyscanner.scanner import run_scan
from polyscanner.storage import SnapshotStore

st.set_page_config(page_title="BTC Probability Scanner", page_icon="◎", layout="wide")
st.title("BTC Probability Scanner")
st.caption("Read-only Polymarket US research · no orders · no trading credentials")


@st.cache_resource
def store() -> SnapshotStore:
    return SnapshotStore()


scan_clicked = st.button("Run live scan", type="primary")

if scan_clicked or "scan_result" not in st.session_state:
    try:
        st.session_state.scan_result = run_scan(
            PolymarketUSPublicClient(), CoinbasePublicClient(), store()
        )
    except Exception as error:
        st.error(f"Live scan failed: {error}")
        st.stop()

result = st.session_state.scan_result
cols = st.columns(3)
cols[0].metric(
    "Coinbase BTC spot",
    f"${result.spot_usd:,.2f}",
    help="Latest BTC-USD ticker price from Coinbase Exchange.",
)
cols[1].metric(
    "Recent BTC volatility",
    f"{result.annualized_volatility:.1%}",
    help=(
        "Standard deviation of daily logarithmic BTC returns from the latest "
        "31 Coinbase daily closes, multiplied by √365. It describes recent "
        "price variability; it is not a forecast."
    ),
)
cols[2].metric(
    "BTC price contracts found",
    len(result.contracts),
    help=(
        "Active Polymarket US contracts that mention BTC/Bitcoin and contain "
        "a parseable above/below USD threshold plus an expiry."
    ),
)
st.caption(f"Last scan: {result.scanned_at:%Y-%m-%d %H:%M:%S UTC}")

st.subheader("1. Polymarket US market discovery")
discovery = pd.DataFrame(
    [
        {
            "Stage": "Active US crypto catalog",
            "Count": result.catalog_markets,
            "Meaning": "Markets returned by the public US API using active=true and category=crypto.",
        },
        {
            "Stage": "BTC / Bitcoin matches",
            "Count": result.bitcoin_markets,
            "Meaning": "Catalog entries whose question, description, slug, category, or tags mention BTC/Bitcoin.",
        },
        {
            "Stage": "Usable price-threshold contracts",
            "Count": result.threshold_contracts,
            "Meaning": "BTC matches with a USD strike, above/below direction, and expiry.",
        },
    ]
)
st.dataframe(discovery, width="stretch", hide_index=True)

if not result.contracts:
    st.warning(
        "No active Polymarket US BTC above/below price contract was available in this scan. "
        "The scanner did not substitute international or synthetic markets."
    )
else:
    st.subheader("2. Parsed contracts and probability estimates")
    rows = []
    for contract, estimate in result.contracts:
        rows.append(
            {
                "Question": contract.question,
                "Direction": contract.direction.value,
                "Strike": contract.strike_usd,
                "Expiry": contract.expires_at,
                "YES ask": estimate.executable_price,
                "Modeled probability": estimate.probability,
                "Raw edge": estimate.raw_edge,
                "Edge after fee": estimate.edge_after_fee,
            }
        )
    frame = pd.DataFrame(rows).sort_values("Edge after fee", ascending=False)
    st.dataframe(
        frame.style.format(
            {
                "Strike": "${:,.0f}",
                "YES ask": "{:.1%}",
                "Modeled probability": "{:.1%}",
                "Raw edge": "{:+.1%}",
                "Edge after fee": "{:+.1%}",
            }
        ),
        width="stretch",
        hide_index=True,
    )

st.subheader("2. Coinbase price and volatility input")
st.write(
    f"The scanner observed BTC at **${result.spot_usd:,.2f}**. It downloaded the latest "
    "31 daily Coinbase closing prices, calculated each day’s logarithmic return, measured "
    f"their sample standard deviation, and annualized it with √365. The result is "
    f"**{result.annualized_volatility:.1%}**."
)
st.code(
    "daily returns = ln(today close / prior close)\n"
    "annualized realized volatility = std(daily returns) × √365",
    language="text",
)

st.subheader("3. Threshold and expiry parsing")
st.write(
    "For each BTC market, the parser extracts the USD strike, whether the contract resolves "
    "above or below that strike, its expiry timestamp, and the executable YES bid/ask. "
    "Contracts with ambiguous wording are rejected instead of guessed."
)

st.subheader("4. Fee-aware probability comparison")
if result.contracts:
    st.write(
        "The table above compares the modeled probability with the executable YES ask. "
        "Raw edge is modeled probability minus ask; edge after fee also deducts the market’s "
        "published fee coefficient."
    )
else:
    st.info("No probability comparison can be calculated until a parseable US BTC contract exists.")

with st.expander("Probability model and limitations"):
    st.write(
        "The benchmark assumes lognormal BTC returns and recent realized volatility. "
        "It does not model jumps, order-book imbalance, oracle differences, news, or volatility smiles. "
        "A positive modeled edge is not a recommendation and does not prove an executable advantage."
    )

st.subheader("5. SQLite recording")
st.write(
    "Every live scan is stored locally in `data/scanner.db`, including scans that find zero "
    "contracts. Contract-level estimates are stored separately when contracts exist."
)
scan_history = store().recent_scans()
if scan_history:
    st.caption("Recent catalog scans")
    st.dataframe(pd.DataFrame(scan_history), width="stretch", hide_index=True)

history = store().recent_estimates()
if history:
    st.caption("Recent contract estimates")
    st.dataframe(pd.DataFrame(history), width="stretch", hide_index=True)
else:
    st.caption("No contract estimates recorded yet because no usable US BTC contract has been found.")

st.subheader("6. Safety boundary")
st.success("Read-only: no Polymarket credentials, no order placement, and no account access.")
