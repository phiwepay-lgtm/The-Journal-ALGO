"""Trade Journal System — Phase 1: The Journal Analyzer.

Run: streamlit run app.py
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analyzer import full_report, load_journal


BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR / "template.csv"
POSITIVE = "#16c79a"
NEGATIVE = "#ff5c73"
AMBER = "#f6b73c"
COLOR_SCALE = [NEGATIVE, AMBER, POSITIVE]

st.set_page_config(page_title="Trade Journal Analyzer", page_icon="📊", layout="wide")

st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; padding-bottom: 3rem; max-width: 1450px;}
      [data-testid="stMetric"] {
        background: rgba(127, 127, 127, 0.07);
        border: 1px solid rgba(127, 127, 127, 0.18);
        border-radius: 12px;
        padding: 14px 16px;
      }
      [data-testid="stMetricValue"] {font-size: 1.65rem;}
      .app-kicker {color: #16c79a; font-weight: 700; letter-spacing: .12em; font-size: .78rem;}
      .app-subtitle {opacity: .75; font-size: 1.05rem; margin-top: -.4rem;}
      .small-note {opacity: .7; font-size: .88rem;}
      section[data-testid="stSidebar"] .block-container {padding-top: 2rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="app-kicker">TRADE JOURNAL SYSTEM · PHASE 1</div>', unsafe_allow_html=True)
st.title("Your journal. Your patterns. Your system.")
st.markdown(
    '<p class="app-subtitle">Upload your trades to see what is working, what is leaking R, '
    "and which rules deserve testing next.</p>",
    unsafe_allow_html=True,
)
st.divider()

# Sidebar: data source and reusable template.
st.sidebar.header("📁 Journal data")
st.sidebar.caption("Your file is analyzed in this app session; no external AI service is used.")
uploaded = st.sidebar.file_uploader(
    "Upload CSV or Excel",
    type=["csv", "xlsx", "xls"],
    help="Required columns: Date, Pair, Direction, Setup, Entry, Exit, and PL_R.",
)

if TEMPLATE_PATH.exists():
    st.sidebar.download_button(
        "⬇️ Download CSV template",
        data=TEMPLATE_PATH.read_bytes(),
        file_name="trade_journal_template.csv",
        mime="text/csv",
        width="stretch",
    )

if "show_sample" not in st.session_state:
    st.session_state.show_sample = False

if st.sidebar.button("✨ Explore sample journal", width="stretch"):
    st.session_state.show_sample = True

st.sidebar.divider()
st.sidebar.markdown("**Required columns**")
st.sidebar.caption("Date, Pair, Direction, Setup, Entry, Exit, PL_R")
st.sidebar.markdown("**Optional context**")
st.sidebar.caption("Stop, Target, Timeframe, Session, Emotion, Mistake, Notes")

if uploaded is not None:
    st.session_state.show_sample = False
    source = uploaded
    source_name = uploaded.name
elif st.session_state.show_sample:
    source = TEMPLATE_PATH
    source_name = "sample journal"
else:
    source = None
    source_name = ""

if source is None:
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        st.subheader("Start with your trade history")
        st.markdown(
            """
            1. **Download the template** or export your existing journal.
            2. **Upload a CSV or Excel file** using the sidebar.
            3. **Review the patterns**, then download your draft rule sheet.

            No journal ready? Choose **Explore sample journal** to try the complete dashboard.
            """
        )
        st.info("Your PL_R column should contain each trade's realized result in R multiples: 2.5 for +2.5R, -1 for -1R.")
    with right:
        st.subheader("What you’ll get")
        st.markdown(
            """
            | Section | What it reveals |
            |---|---|
            | **Overview** | Expectancy, equity curve, drawdown, R:R |
            | **Setups** | Net R, win rate, and average R by setup |
            | **Timing** | Weekday and session performance |
            | **Psychology** | Mistake costs and emotional context |
            | **System draft** | Candidate DO / DON’T rules from your data |
            | **Raw data** | Cleaned, exportable journal rows |
            """
        )
    st.stop()

try:
    df = load_journal(source)
except Exception as exc:
    st.error(f"Could not read the journal: {exc}")
    st.session_state.show_sample = False
    st.stop()

report = full_report(df)
rows_dropped = df.attrs.get("rows_dropped", 0)
st.success(
    f"Loaded {len(df)} valid trades from {source_name} · "
    f"{df['Date'].min().date()} → {df['Date'].max().date()}"
)
if rows_dropped:
    st.warning(f"Skipped {rows_dropped} row(s) with an invalid date or PL_R value.")

tabs = st.tabs([
    "📈 Overview",
    "🔧 Setups",
    "📅 Timing",
    "🧠 Psychology",
    "📋 System Draft",
    "📄 Raw Data",
])


def finish_bar(fig, height: int = 360):
    fig.add_hline(y=0, line_color="rgba(127,127,127,.35)", line_width=1)
    fig.update_layout(
        height=height,
        template="plotly_dark",
        coloraxis_showscale=False,
        margin=dict(l=20, r=20, t=55, b=20),
    )
    return fig


with tabs[0]:
    st.subheader("Overall performance")
    overall = report["overall"]
    metrics = [
        ("Total trades", overall["Total Trades"]),
        ("Win rate", overall["Win Rate"]),
        ("Net result", overall["Total R"]),
        ("Expectancy / trade", overall["Avg R per Trade"]),
        ("Profit factor", overall["Profit Factor"]),
    ]
    for column, (label, value) in zip(st.columns(5), metrics):
        column.metric(label, value)

    chart_col, detail_col = st.columns([2.1, 1], gap="large")
    with chart_col:
        st.markdown("#### Equity curve · cumulative R")
        curve = df[["Date", "PL_R"]].copy()
        curve["CumR"] = curve["PL_R"].cumsum()
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=curve["Date"],
                y=curve["CumR"],
                mode="lines+markers",
                line=dict(color=POSITIVE, width=2.5),
                marker=dict(size=6),
                fill="tozeroy",
                fillcolor="rgba(22,199,154,.10)",
                customdata=curve["PL_R"],
                hovertemplate="%{x|%Y-%m-%d}<br>Cumulative: %{y:.2f}R<br>Trade: %{customdata:.2f}R<extra></extra>",
            )
        )
        fig.add_hline(y=0, line_color="rgba(127,127,127,.35)")
        fig.update_layout(
            height=360,
            template="plotly_dark",
            xaxis_title=None,
            yaxis_title="Cumulative R",
            margin=dict(l=20, r=20, t=20, b=20),
            hovermode="x unified",
        )
        st.plotly_chart(fig, width="stretch")

    with detail_col:
        st.markdown("#### Performance detail")
        details = pd.DataFrame(
            {
                "Metric": ["Wins", "Losses", "Breakeven", "Average win", "Average loss", "Best trade", "Worst trade", "Max drawdown"],
                "Value": [
                    overall["Wins"], overall["Losses"], overall["Breakeven"],
                    overall["Avg Win"], overall["Avg Loss"], overall["Best Trade"],
                    overall["Worst Trade"], overall["Max Drawdown"],
                ],
            }
        )
        details["Value"] = details["Value"].astype(str)
        st.dataframe(details, hide_index=True, width="stretch")

    rr = report["rr"]
    if rr:
        st.markdown("#### R:R reality check")
        for column, (label, value) in zip(st.columns(len(rr)), rr.items()):
            column.metric(label, value)
    st.caption("Win rate = positive-R trades ÷ all valid trades. Results are descriptive, not financial advice.")

with tabs[1]:
    st.subheader("Performance by setup")
    setup_df = report["by_setup"]
    if setup_df.empty:
        st.warning("No Setup data found.")
    else:
        st.dataframe(setup_df, width="stretch")
        fig = px.bar(
            setup_df.reset_index(),
            x="Setup",
            y="TotalR",
            color="TotalR",
            color_continuous_scale=COLOR_SCALE,
            title="Net R by setup",
            hover_data=["Trades", "WinRate", "AvgR"],
        )
        st.plotly_chart(finish_bar(fig, 400), width="stretch")

with tabs[2]:
    st.subheader("Performance by day and session")
    day_col, session_col = st.columns(2, gap="large")
    with day_col:
        st.markdown("#### Day of week")
        day_df = report["by_day"]
        st.dataframe(day_df, width="stretch")
        fig = px.bar(
            day_df.reset_index(),
            x="DayOfWeek",
            y="TotalR",
            color="TotalR",
            color_continuous_scale=COLOR_SCALE,
            title="Net R by weekday",
        )
        st.plotly_chart(finish_bar(fig, 330), width="stretch")

    with session_col:
        st.markdown("#### Session")
        session_df = report["by_session"]
        if session_df.empty:
            st.info("Add a Session column to unlock session analysis.")
        else:
            st.dataframe(session_df, width="stretch")
            fig = px.pie(
                session_df.reset_index(),
                values="Trades",
                names="Session",
                title="Trade distribution by session",
                template="plotly_dark",
                hole=0.4,
            )
            fig.update_layout(height=330, margin=dict(l=20, r=20, t=55, b=20))
            st.plotly_chart(fig, width="stretch")

with tabs[3]:
    st.subheader("Psychology and mistakes")
    mistake_col, emotion_col = st.columns(2, gap="large")
    with mistake_col:
        st.markdown("#### Logged mistake outcomes")
        mistakes_df = report["mistakes"]
        if mistakes_df.empty:
            st.success("No mistakes logged, or every row is marked None.")
        else:
            st.dataframe(mistakes_df, width="stretch")
            fig = px.bar(
                mistakes_df.reset_index(),
                x="Mistake",
                y="TotalRLost",
                color="TotalRLost",
                color_continuous_scale=COLOR_SCALE,
                title="Net R on trades with each mistake",
            )
            st.plotly_chart(finish_bar(fig), width="stretch")
            st.caption("Net R is not necessarily the causal cost of a mistake; review the underlying trades.")

    with emotion_col:
        st.markdown("#### Emotional context")
        emotions_df = report["emotions"]
        if emotions_df.empty:
            st.info("Add an Emotion column to unlock this analysis.")
        else:
            st.dataframe(emotions_df, width="stretch")
            fig = px.bar(
                emotions_df.reset_index(),
                x="Emotion",
                y="TotalR",
                color="TotalR",
                color_continuous_scale=COLOR_SCALE,
                title="Net R by logged emotion",
            )
            st.plotly_chart(finish_bar(fig), width="stretch")

with tabs[4]:
    st.subheader("Your system · draft v1")
    st.markdown(
        "These are **candidate rules**, not conclusions. Small samples can make normal variance look like an edge."
    )
    st.code(report["system_draft"], language="text")
    st.download_button(
        "⬇️ Download system draft",
        data=report["system_draft"],
        file_name="my_system_draft_v1.txt",
        mime="text/plain",
    )

with tabs[5]:
    st.subheader("Cleaned journal data")
    st.dataframe(df, width="stretch", height=500)
    st.download_button(
        "⬇️ Download cleaned data",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="cleaned_trade_journal.csv",
        mime="text/csv",
    )
