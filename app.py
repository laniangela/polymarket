from __future__ import annotations

import pandas as pd
import streamlit as st

from polyscanner.agents import (
    ContractAgent,
    MarketQualityAgent,
    QuantAgent,
    SettlementAgent,
    SkepticAgent,
)
from polyscanner.orchestrator import OpportunityOrchestrator
from polyscanner.providers import CoinbasePublicClient, KalshiPublicClient
from polyscanner.scanner import run_scan
from polyscanner.storage import SnapshotStore

st.set_page_config(page_title="Kalshi BTC Agent Control Room", page_icon="◎", layout="wide")
st.title("Kalshi BTC Agent Control Room")
st.caption("Live opportunities · agent review · percentage sizing · paper decisions only")

with st.sidebar:
    st.subheader("Paper account")
    paper_equity = st.number_input(
        "Account equity",
        min_value=100.0,
        value=1_000.0,
        step=100.0,
        help="Position sizes are percentages of this paper balance.",
    )
    st.caption("Standard 5% · Strong 7.5% · Exceptional 10%")
    st.warning("Live order placement is not enabled.")


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
with st.expander("Developer diagnostics: Kalshi feed coverage"):
    st.dataframe(discovery, width="stretch", hide_index=True)

if not result.contracts:
    st.warning(
        "No active Kalshi KXBTC price-range contract closing within 14 days was available."
    )
else:
    st.subheader("Available Bitcoin bets")
    st.write(
        "A **Kalshi event** is the dated question, such as “BTC price range on June 9 at "
        "5 PM EDT.” A **contract** is one YES/NO price bucket inside that event, such as "
        "“BTC settles between $63,500 and $63,749.99.” One event therefore contains many "
        "mutually exclusive contracts."
    )
    rows = []
    for contract, estimate in result.contracts:
        rows.append(
            {
                "Event ticker": contract.event_ticker,
                "Event time": contract.expires_at,
                "Event": contract.event_title,
                "Event subtitle": contract.event_subtitle,
                "Price range": f"${contract.strike_usd:,.0f}–${contract.cap_strike_usd:,.2f}",
                "Range floor": contract.strike_usd,
                "Range cap": contract.cap_strike_usd,
                "YES ask": estimate.executable_price,
                "Ask size": contract.yes_ask_size,
                "Modeled probability": estimate.probability,
                "Raw edge": estimate.raw_edge,
                "Edge after fee": estimate.edge_after_fee,
            }
        )
    frame = pd.DataFrame(rows)
    events = (
        frame[["Event ticker", "Event", "Event subtitle", "Event time"]]
        .drop_duplicates("Event ticker")
        .sort_values("Event time")
    )
    event_labels = {
        f"{row['Event subtitle']} · {row['Event ticker']}": row["Event ticker"]
        for _, row in events.iterrows()
    }
    selected_event_label = st.selectbox(
        "Choose a BTC event",
        list(event_labels),
        help="Each event is one settlement date/time containing many mutually exclusive price buckets.",
    )
    selected_event_ticker = event_labels[selected_event_label]
    event_frame = frame[frame["Event ticker"] == selected_event_ticker].sort_values("Range floor")
    selected_event_time = event_frame["Event time"].iloc[0]
    selected_event_title = event_frame["Event"].iloc[0]
    st.markdown(f"### {selected_event_title}")
    st.caption(f"Kalshi event: `{selected_event_ticker}`")
    summary_cols = st.columns(3)
    summary_cols[0].metric("Settlement time", selected_event_time.strftime("%b %d · %H:%M UTC"))
    summary_cols[1].metric("Price buckets", len(event_frame))
    positive_edges = int((event_frame["Edge after fee"] > 0).sum())
    summary_cols[2].metric("Positive model gaps", positive_edges)
    st.dataframe(
        event_frame[
            [
                "Price range",
                "YES ask",
                "Ask size",
                "Modeled probability",
                "Raw edge",
                "Edge after fee",
            ]
        ].style.format(
            {
                "YES ask": "{:.1%}",
                "Ask size": "{:,.0f}",
                "Modeled probability": "{:.1%}",
                "Raw edge": "{:+.1%}",
                "Edge after fee": "{:+.1%}",
            }
        ),
        width="stretch",
        hide_index=True,
    )
    ranked_contracts = sorted(
        [
            item
            for item in result.contracts
            if item[0].event_ticker == selected_event_ticker
        ],
        key=lambda item: item[1].edge_after_fee
        if item[1].edge_after_fee is not None
        else float("-inf"),
        reverse=True,
    )
    st.subheader("Selected bet")
    st.caption(
        "Select one price bucket from this event and verify what its YES contract settles on."
    )
    contract_labels = {
        (
            f"{contract.expires_at:%b %d %H:%M UTC} · "
            f"${contract.strike_usd:,.0f}–${contract.cap_strike_usd:,.2f} · "
            f"YES {contract.best_ask:.0%}"
        ): (contract, estimate)
        for contract, estimate in ranked_contracts
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

    st.subheader("Agent decision")
    orchestrator = OpportunityOrchestrator(
        [
            ContractAgent(),
            QuantAgent(),
            MarketQualityAgent(),
            SettlementAgent(),
            SkepticAgent(),
        ]
    )
    decision = orchestrator.decide(
        selected_contract,
        selected_estimate,
        equity=paper_equity,
    )
    decision_cols = st.columns(3)
    decision_cols[0].metric("Decision", decision.action)
    decision_cols[1].metric("Paper allocation", f"{decision.allocation_pct:.1%}")
    decision_cols[2].metric("Paper stake", f"${decision.stake_usd:,.2f}")
    for opinion in decision.opinions:
        status = {
            "support": "PASS",
            "watch": "CAUTION",
            "veto": "VETO",
        }[opinion.verdict.value]
        st.markdown(f"**{opinion.agent} · {status}** — {opinion.summary}")
        st.caption(" | ".join(opinion.evidence))
    st.caption("This is a structured paper decision. No Kalshi order is created.")

with st.expander("How the BTC probability input is calculated"):
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

with st.expander("Probability model and limitations"):
    st.write(
        "The benchmark assumes lognormal BTC returns and recent realized volatility. Coinbase "
        "is an analysis input, but Kalshi settles against CF Benchmarks BRTI, creating basis risk. "
        "It does not model jumps, order-book imbalance, news, or volatility smiles. "
        "A positive modeled edge is not a recommendation and does not prove an executable advantage."
    )

with st.expander("Recorded scanner history"):
    scan_history = store().recent_scans()
    if scan_history:
        st.caption("Recent catalog scans")
        st.dataframe(pd.DataFrame(scan_history), width="stretch", hide_index=True)
    history = store().recent_estimates()
    if history:
        st.caption("Recent contract estimates")
        st.dataframe(pd.DataFrame(history), width="stretch", hide_index=True)

st.success("Current safety boundary: live data, paper decisions, no Kalshi account access or orders.")
