from __future__ import annotations

import pandas as pd
import streamlit as st

from polyscanner.providers import CoinbasePublicClient, KalshiPublicClient
from polyscanner.scanner import run_scan
from polyscanner.storage import SnapshotStore

st.set_page_config(page_title="Kalshi BTC Probability Scanner", page_icon="◎", layout="wide")
st.title("BTC Probability Scanner")
st.caption("Read-only Kalshi research · next 14 days · no orders · no trading credentials")


@st.cache_resource
def store() -> SnapshotStore:
    return SnapshotStore()


scan_clicked = st.button("Run live scan", type="primary")

if scan_clicked or "scan_result" not in st.session_state:
    try:
        st.session_state.scan_result = run_scan(
            KalshiPublicClient(), CoinbasePublicClient(), store()
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
        "Standard deviation of five-minute logarithmic BTC returns over the latest "
        "24 hours, annualized with √(365×24×12). It describes recent variability; "
        "it is not a forecast."
    ),
)
cols[2].metric(
    "BTC price contracts found",
    len(result.contracts),
    help=(
        "Open Kalshi KXBTC price-range contracts closing within the next 14 days."
    ),
)
st.caption(f"Last scan: {result.scanned_at:%Y-%m-%d %H:%M:%S UTC}")

st.subheader("1. Kalshi BTC market discovery")
discovery = pd.DataFrame(
    [
        {
            "Stage": "KXBTC contracts in next 14 days",
            "Count": result.catalog_markets,
            "Meaning": "Contracts from open Kalshi KXBTC events closing within 14 days.",
        },
        {
            "Stage": "Recognized KXBTC contracts",
            "Count": result.bitcoin_markets,
            "Meaning": "Contracts identified by Kalshi's KXBTC series ticker.",
        },
        {
            "Stage": "Usable price-range contracts",
            "Count": result.threshold_contracts,
            "Meaning": "Contracts with lower/upper bounds, close time, quotes, and rules.",
        },
    ]
)
st.dataframe(discovery, width="stretch", hide_index=True)

if not result.contracts:
    st.warning(
        "No active Kalshi KXBTC price-range contract closing within 14 days was available."
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
                "Range cap": contract.cap_strike_usd,
                "Expiry": contract.expires_at,
                "YES ask": estimate.executable_price,
                "Ask size": contract.yes_ask_size,
                "Modeled probability": estimate.probability,
                "Raw edge": estimate.raw_edge,
                "Edge after fee": estimate.edge_after_fee,
            }
        )
    frame = pd.DataFrame(rows).sort_values("Edge after fee", ascending=False)
    rows_to_show = st.slider("Contracts to display", 10, 100, 30, 10)
    st.dataframe(
        frame.head(rows_to_show).style.format(
            {
                "Strike": "${:,.0f}",
                "Range cap": "${:,.0f}",
                "YES ask": "{:.1%}",
                "Modeled probability": "{:.1%}",
                "Raw edge": "{:+.1%}",
                "Edge after fee": "{:+.1%}",
            }
        ),
        width="stretch",
        hide_index=True,
    )
    ranked_contracts = sorted(
        result.contracts,
        key=lambda item: item[1].edge_after_fee
        if item[1].edge_after_fee is not None
        else float("-inf"),
        reverse=True,
    )
    st.subheader("Contract inspector")
    st.caption(
        "Verify what a selected contract actually settles on before trusting its model score."
    )
    contract_labels = {
        (
            f"{contract.expires_at:%b %d %H:%M UTC} · "
            f"${contract.strike_usd:,.0f}–${contract.cap_strike_usd:,.2f} · "
            f"YES {contract.best_ask:.0%}"
        ): (contract, estimate)
        for contract, estimate in ranked_contracts[:50]
        if contract.cap_strike_usd is not None and contract.best_ask is not None
    }
    selected_label = st.selectbox("Inspect a contract", list(contract_labels))
    selected_contract, selected_estimate = contract_labels[selected_label]
    detail_cols = st.columns(4)
    detail_cols[0].metric(
        "Settlement range",
        f"${selected_contract.strike_usd:,.0f}–${selected_contract.cap_strike_usd:,.2f}",
    )
    detail_cols[1].metric("Kalshi YES ask", f"{selected_contract.best_ask:.0%}")
    detail_cols[2].metric("Modeled probability", f"{selected_estimate.probability:.1%}")
    detail_cols[3].metric(
        "After-fee model gap",
        f"{selected_estimate.edge_after_fee:+.1%}",
    )
    st.info(
        f"**What must happen:** The simple average of 60 CF Benchmarks BRTI readings "
        f"during the final minute must be inside "
        f"**${selected_contract.strike_usd:,.0f}–${selected_contract.cap_strike_usd:,.2f}** "
        f"at **{selected_contract.expires_at:%Y-%m-%d %H:%M UTC}**."
    )
    st.warning(
        "The model uses Coinbase BTC-USD, but settlement uses CF Benchmarks BRTI. "
        "A small Coinbase/BRTI difference near a range boundary can change the outcome."
    )
    with st.expander("View official rule text"):
        st.write(selected_contract.rules)
        st.caption(
            f"Ticker: {selected_contract.market_id} | YES bid/ask: "
            f"{selected_contract.best_bid} / {selected_contract.best_ask} | "
            f"Ask size: {selected_contract.yes_ask_size}"
        )

st.subheader("2. Coinbase price and volatility input")
st.write(
    f"The scanner observed BTC at **${result.spot_usd:,.2f}**. It downloaded the latest "
    "24 hours of five-minute Coinbase candles, calculated each interval’s logarithmic return, "
    f"measured their sample standard deviation, and annualized it with √(365×24×12). The result is "
    f"**{result.annualized_volatility:.1%}**."
)
st.code(
    "5-minute return = ln(current close / prior close)\n"
    "annualized realized volatility = std(5-minute returns) × √(365 × 24 × 12)",
    language="text",
)

st.subheader("3. Threshold and expiry parsing")
st.write(
    "For each Kalshi KXBTC market, the parser extracts its lower and upper USD bounds, "
    "close time, executable YES bid/ask, displayed ask size, and settlement rules. "
    "Current hourly markets settle from the average of sixty CF Benchmarks BRTI readings "
    "immediately before the stated close."
)

st.subheader("4. Fee-aware probability comparison")
if result.contracts:
    st.write(
        "The table above compares the modeled probability of BTC landing inside each price "
        "range with the executable YES ask. "
        "Raw edge is modeled probability minus ask; edge after fee also deducts the market’s "
        "standard quadratic taker-fee estimate before order-level rounding."
    )
else:
    st.info("No probability comparison can be calculated until a parseable Kalshi BTC contract exists.")

with st.expander("Probability model and limitations"):
    st.write(
        "The benchmark assumes lognormal BTC returns and recent realized volatility. Coinbase "
        "is an analysis input, but Kalshi settles against CF Benchmarks BRTI, creating basis risk. "
        "It does not model jumps, order-book imbalance, news, or volatility smiles. "
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
st.success("Read-only: no Kalshi credentials, no order placement, and no account access.")
