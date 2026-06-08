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


if st.button("Scan now", type="primary"):
    st.cache_data.clear()

try:
    result = run_scan(PolymarketUSPublicClient(), CoinbasePublicClient(), store())
except Exception as error:
    st.error(f"Live scan failed: {error}")
    st.stop()

cols = st.columns(3)
cols[0].metric("BTC spot", f"${result.spot_usd:,.2f}")
cols[1].metric("30D realized volatility", f"{result.annualized_volatility:.1%}")
cols[2].metric("Eligible US contracts", len(result.contracts))

if not result.contracts:
    st.info(
        "Polymarket US currently returned no active BTC threshold contracts. "
        "This is a valid recorded observation; no international or synthetic markets were substituted."
    )
else:
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

with st.expander("Model and limitations"):
    st.write(
        "The benchmark assumes lognormal BTC returns and recent realized volatility. "
        "It does not model jumps, order-book imbalance, oracle differences, news, or volatility smiles. "
        "A positive modeled edge is not a recommendation and does not prove an executable advantage."
    )

history = store().recent_estimates()
if history:
    st.subheader("Recorded estimates")
    st.dataframe(pd.DataFrame(history), width="stretch", hide_index=True)
