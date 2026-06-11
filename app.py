from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from polyscanner.auth import KalshiCredentials, KalshiRequestSigner
from polyscanner.live import KalshiLiveClient
from polyscanner.opportunities import default_orchestrator, rank_opportunities
from polyscanner.providers import (
    CoinbasePublicClient,
    KalshiAccountClient,
    KalshiPublicClient,
)
from polyscanner.scanner import run_scan
from polyscanner.storage import SnapshotStore

st.set_page_config(page_title="Kalshi BTC Agent Control Room", page_icon="◎", layout="wide")
st.title("Kalshi BTC Agent Control Room")
st.caption("Ranked BTC opportunities · agent review · percentage sizing · paper decisions")

st.markdown(
    """
    <style>
    .stApp { background: #f4f1ea; color: #28312f; }
    [data-testid="stSidebar"] { background: #e8e5dc; }
    [data-testid="stMetric"] {
        background: #fbfaf6;
        border: 1px solid #d8d3c7;
        border-radius: 8px;
        padding: 0.8rem;
    }
    div[data-testid="stDataFrame"] { border: 1px solid #d8d3c7; }
    </style>
    """,
    unsafe_allow_html=True,
)

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
    st.divider()
    st.subheader("Kalshi connection")
    credentials = KalshiCredentials.from_env()
    if credentials is None:
        st.caption("Public market data connected")
        st.info("Add the two Kalshi values from `.env.example` to enable BRTI and account reads.")
    else:
        st.caption("API credentials found")
        if st.button("Test account + BRTI"):
            try:
                signer = KalshiRequestSigner(credentials)
                st.session_state.kalshi_balance = KalshiAccountClient(signer).balance()
                st.session_state.brti = KalshiLiveClient(signer).latest_brti()
            except Exception as error:
                st.error(f"Kalshi connection failed: {error}")
        balance_payload = st.session_state.get("kalshi_balance")
        if balance_payload:
            balance_cents = float(balance_payload.get("balance", 0))
            st.metric("Kalshi cash balance", f"${balance_cents / 100:,.2f}")
        brti = st.session_state.get("brti")
        if brti:
            st.metric("Live BRTI", f"${brti.value:,.2f}")
            st.caption(f"Received {brti.received_at:%H:%M:%S UTC}")
    st.warning("Order placement is not implemented or enabled.")


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
ranked = rank_opportunities(result.contracts, paper_equity, store=store())
paper_trades = [item for item in ranked if item.decision.action == "PAPER TRADE"]
watch_items = [item for item in ranked if item.decision.action == "WATCH"]


def microstructure_opinion(item):
    return next(
        (opinion for opinion in item.decision.opinions if opinion.agent == "Microstructure"),
        None,
    )


display_ranked = sorted(
    ranked,
    key=lambda item: (
        microstructure_opinion(item) is None
        or microstructure_opinion(item).summary.startswith("No recorded")
        or microstructure_opinion(item).summary.startswith("Recorded order-book evidence is stale"),
        -(item.estimate.edge_after_fee or -999),
    ),
)

cols = st.columns(4)
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
    "BTC contracts",
    len(result.contracts),
    help=(
        "Open Kalshi KXBTC price-range contracts closing within the next 14 days."
    ),
)
cols[3].metric(
    "Paper selections",
    len(paper_trades),
    help="Contracts that pass all agent checks and fit the portfolio exposure rules.",
)
st.caption(f"Last scan: {result.scanned_at:%Y-%m-%d %H:%M:%S UTC}")

recorder_status = store().recorder_status()
recent_feed = store().recent_feed_observations(limit=50)
st.subheader("Live signal recorder")
if recorder_status is None:
    st.info(
        "The continuous recorder has not been started. Run `kalshi-recorder` in a second terminal. "
        "It works with public data and automatically adds BRTI when Kalshi credentials exist."
    )
else:
    heartbeat = datetime.fromisoformat(str(recorder_status["heartbeat_at"]))
    heartbeat = heartbeat.replace(tzinfo=heartbeat.tzinfo or timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - heartbeat).total_seconds()
    state = str(recorder_status["state"])
    active_states = {"running", "public-rest", "reconnecting"}
    display_state = "STALE" if state in active_states and age_seconds > 15 else state.upper()
    recorder_cols = st.columns(4)
    recorder_cols[0].metric("Recorder", display_state)
    recorder_cols[1].metric("Tracked contracts", int(recorder_status["market_count"]))
    recorder_cols[2].metric("Observations", int(recorder_status["observation_count"]))
    recorder_cols[3].metric("Heartbeat age", f"{age_seconds:.0f}s")
    if recorder_status.get("last_error"):
        st.warning(f"Last recorder error: {recorder_status['last_error']}")
    if recent_feed:
        latest = recent_feed[0]
        if latest.get("coinbase_spot") is not None and latest.get("brti_value") is not None:
            basis = float(latest["coinbase_spot"]) - float(latest["brti_value"])
            st.caption(
                f"Latest synchronized Coinbase/BRTI basis: **${basis:+,.2f}**. "
                "Lag conclusions require accumulated order-book history, not one observation."
            )
        with st.expander("Recent synchronized observations"):
            st.dataframe(
                pd.DataFrame(recent_feed)[
                    [
                        "observed_at",
                        "source",
                        "market_ticker",
                        "coinbase_spot",
                        "brti_value",
                        "yes_bid",
                        "yes_ask",
                        "yes_bid_size",
                        "yes_ask_size",
                    ]
                ],
                width="stretch",
                hide_index=True,
            )

st.subheader("Microstructure validation")
validation_counts = store().validation_counts()
validation_summary = store().validation_summary()
validation_cols = st.columns(4)
validation_cols[0].metric("Signals recorded", validation_counts["signals"])
validation_cols[1].metric("SUPPORT signals", validation_counts["supports"])
validation_cols[2].metric("Horizons resolved", validation_counts["resolved"])
validation_cols[3].metric("Executable outcomes", validation_counts["executable"])
if not validation_summary:
    st.info(
        "No forward outcomes have been resolved yet. The recorder will evaluate each tracked "
        "contract and score its 5s, 15s, 30s, and 60s executable result."
    )
else:
    summary_frame = pd.DataFrame(validation_summary).rename(
        columns={
            "verdict": "Agent verdict",
            "horizon_seconds": "Target horizon",
            "outcomes": "Resolved",
            "executable": "Executable",
            "favorable_rate": "Positive after fees",
            "average_net_return": "Average net return",
            "average_elapsed_seconds": "Actual elapsed",
        }
    )
    st.dataframe(
        summary_frame.style.format(
            {
                "Target horizon": "{}s",
                "Positive after fees": "{:.1%}",
                "Average net return": "{:+.2%}",
                "Actual elapsed": "{:.1f}s",
            },
            na_rep="Not executable",
        ),
        width="stretch",
        hide_index=True,
    )
    st.caption(
        "Returns assume buying YES at the recorded ask and selling at the first recorded bid "
        "after the target horizon, less estimated entry and exit fees."
    )
with st.expander("Recent Microstructure Agent signals"):
    recent_signals = store().recent_microstructure_signals(limit=50)
    if recent_signals:
        st.dataframe(
            pd.DataFrame(recent_signals)[
                [
                    "evaluated_at",
                    "market_ticker",
                    "verdict",
                    "summary",
                    "entry_bid",
                    "entry_ask",
                    "spread",
                    "coinbase_momentum_60s_bps",
                    "repricing_delay_seconds",
                ]
            ],
            width="stretch",
            hide_index=True,
        )
    else:
        st.caption("No validation signals recorded yet.")

st.subheader("Best opportunities now")
st.write(
    "Every live BTC price bucket is reviewed automatically. The table ranks modeled gaps after "
    "estimated fees, applies agent vetoes, selects at most one bucket per settlement event, and "
    "stops allocating when the 25% paper exposure ceiling is reached."
)
feed_rows = []
for item in display_ranked[:20]:
    contract = item.contract
    estimate = item.estimate
    microstructure = microstructure_opinion(item)
    feed_rows.append(
        {
            "Rank": item.rank,
            "Decision": item.decision.action,
            "Settlement": contract.expires_at,
            "Price range": f"${contract.strike_usd:,.0f}–${contract.cap_strike_usd:,.2f}",
            "YES ask": estimate.executable_price,
            "Model": estimate.probability,
            "After-fee gap": estimate.edge_after_fee,
            "Paper stake": item.decision.stake_usd,
            "Microstructure": microstructure.summary if microstructure else "Not evaluated",
            "Event": contract.event_ticker,
        }
    )
feed_frame = pd.DataFrame(
    feed_rows,
    columns=[
        "Rank",
        "Decision",
        "Settlement",
        "Price range",
        "YES ask",
        "Model",
        "After-fee gap",
        "Paper stake",
        "Microstructure",
        "Event",
    ],
)
st.dataframe(
    feed_frame.style.format(
        {
            "YES ask": "{:.1%}",
            "Model": "{:.1%}",
            "After-fee gap": "{:+.1%}",
            "Paper stake": "${:,.2f}",
        }
    ),
    width="stretch",
    hide_index=True,
)
if paper_trades:
    total_stake = sum(item.decision.stake_usd for item in paper_trades)
    st.success(
        f"{len(paper_trades)} paper selection(s), reserving ${total_stake:,.2f} "
        f"({total_stake / paper_equity:.1%}) of the paper account."
    )
elif watch_items:
    st.info("No contract currently clears the strong-trade threshold. The closest candidates remain on watch.")
else:
    st.info("No current BTC contract passes the model and market-quality checks.")

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
    focus_item = paper_trades[0] if paper_trades else display_ranked[0]
    focus_event = focus_item.contract.event_ticker
    event_options = list(event_labels)
    default_event_index = next(
        (
            index
            for index, label in enumerate(event_options)
            if event_labels[label] == focus_event
        ),
        0,
    )
    selected_event_label = st.selectbox(
        "Choose a BTC event",
        event_options,
        index=default_event_index,
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
    contract_options = list(contract_labels)
    default_contract_index = next(
        (
            index
            for index, label in enumerate(contract_options)
            if contract_labels[label][0].market_id == focus_item.contract.market_id
        ),
        0,
    )
    selected_label = st.selectbox(
        "Inspect a contract",
        contract_options,
        index=default_contract_index,
    )
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
    orchestrator = default_orchestrator(store())
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

st.success(
    "Current safety boundary: public market data, optional read-only Kalshi account/BRTI access, "
    "paper decisions, and no order placement."
)
