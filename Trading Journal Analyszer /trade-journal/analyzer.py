"""Trade Journal Analyzer — Phase 1 core engine.

Reads a CSV/Excel journal, calculates descriptive performance statistics,
and drafts candidate trading rules from the observed data.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


REQUIRED_COLS = ["Date", "Pair", "Direction", "Setup", "Entry", "Exit", "PL_R"]
OPTIONAL_COLS = [
    "Stop",
    "Target",
    "Timeframe",
    "Session",
    "Emotion",
    "Mistake",
    "Notes",
]


def _column_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


# Matching is case-insensitive and ignores spaces, hyphens, and underscores.
_COLUMN_ALIASES = {
    **{_column_key(col): col for col in REQUIRED_COLS + OPTIONAL_COLS},
    "r": "PL_R",
    "plr": "PL_R",
    "pnlr": "PL_R",
    "resultinr": "PL_R",
    "riskmultiple": "PL_R",
    "rmultiple": "PL_R",
    "timeframe": "Timeframe",
    "timeframes": "Timeframe",
    "comment": "Notes",
    "comments": "Notes",
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    columns = []
    for original in df.columns:
        stripped = str(original).strip()
        columns.append(_COLUMN_ALIASES.get(_column_key(stripped), stripped))

    duplicates = sorted({col for col in columns if columns.count(col) > 1})
    if duplicates:
        raise ValueError(f"Duplicate columns after normalization: {duplicates}")

    df = df.copy()
    df.columns = columns
    return df


def load_journal(file: Any) -> pd.DataFrame:
    """Load a journal from an uploaded file object or a local CSV/Excel path."""
    name = str(getattr(file, "name", file)).lower()
    if name.endswith(".csv"):
        df = pd.read_csv(file)
    elif name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(file)
    else:
        raise ValueError("Unsupported file type. Use .csv, .xlsx, or .xls.")

    df = _normalize_columns(df)
    missing = [col for col in REQUIRED_COLS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    return clean(df)


def _clean_text(series: pd.Series, *, title: bool = False, upper: bool = False) -> pd.Series:
    result = series.astype("string").str.strip()
    if title:
        result = result.str.title()
    if upper:
        result = result.str.upper()
    return result


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize journal types, derive analysis columns, and sort by date."""
    df = df.copy()
    original_rows = len(df)

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", format="mixed")
    df["Pair"] = _clean_text(df["Pair"], upper=True).fillna("Unspecified")
    df["Direction"] = _clean_text(df["Direction"], upper=True).fillna("Unspecified")
    df["Setup"] = _clean_text(df["Setup"], title=True)
    df["Setup"] = df["Setup"].replace("", "Unspecified").fillna("Unspecified")

    for col in ["Entry", "Exit", "PL_R"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ["Stop", "Target"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ["Timeframe", "Session", "Emotion", "Mistake"]:
        if col in df.columns:
            df[col] = _clean_text(df[col], title=(col != "Timeframe"))

    if "Session" in df.columns:
        df["Session"] = df["Session"].replace("", "Unspecified").fillna("Unspecified")
    if "Emotion" in df.columns:
        df["Emotion"] = df["Emotion"].replace("", "Unspecified").fillna("Unspecified")
    if "Mistake" in df.columns:
        df["Mistake"] = df["Mistake"].replace("", "None").fillna("None")
    if "Notes" in df.columns:
        df["Notes"] = _clean_text(df["Notes"]).fillna("")

    df["DayOfWeek"] = df["Date"].dt.day_name()
    df["Hour"] = df["Date"].dt.hour
    df["IsWin"] = df["PL_R"] > 0
    df["IsLoss"] = df["PL_R"] < 0

    if "Stop" in df.columns and "Target" in df.columns:
        risk = (df["Entry"] - df["Stop"]).abs()
        reward = (df["Target"] - df["Entry"]).abs()
        df["Planned_RR"] = reward.div(risk.where(risk > 0))

    df = df.dropna(subset=["Date", "PL_R"])
    df = df.sort_values("Date").reset_index(drop=True)
    df.attrs["rows_dropped"] = original_rows - len(df)

    if df.empty:
        raise ValueError("No valid trades remain. Check the Date and PL_R values.")

    return df


def overall_stats(df: pd.DataFrame) -> dict[str, Any]:
    total = len(df)
    wins = int(df["IsWin"].sum())
    losses = int(df["IsLoss"].sum())
    breakeven = total - wins - losses

    if total == 0:
        return {
            "Total Trades": 0,
            "Wins": 0,
            "Losses": 0,
            "Breakeven": 0,
            "Win Rate": "N/A",
            "Total R": "0.00R",
            "Avg R per Trade": "N/A",
            "Best Trade": "N/A",
            "Worst Trade": "N/A",
            "Avg Win": "N/A",
            "Avg Loss": "N/A",
            "Profit Factor": "N/A",
            "Max Drawdown": "N/A",
        }

    winning_r = df.loc[df["IsWin"], "PL_R"]
    losing_r = df.loc[df["IsLoss"], "PL_R"]
    gross_profit = winning_r.sum()
    gross_loss = abs(losing_r.sum())
    equity = df["PL_R"].cumsum()
    running_peak = equity.cummax().clip(lower=0)
    max_drawdown = (running_peak - equity).max()

    if gross_loss > 0:
        profit_factor = f"{gross_profit / gross_loss:.2f}"
    elif gross_profit > 0:
        profit_factor = "∞"
    else:
        profit_factor = "N/A"

    return {
        "Total Trades": total,
        "Wins": wins,
        "Losses": losses,
        "Breakeven": breakeven,
        "Win Rate": f"{wins / total * 100:.1f}%",
        "Total R": f"{df['PL_R'].sum():.2f}R",
        "Avg R per Trade": f"{df['PL_R'].mean():.2f}R",
        "Best Trade": f"{df['PL_R'].max():.2f}R",
        "Worst Trade": f"{df['PL_R'].min():.2f}R",
        "Avg Win": f"{winning_r.mean():.2f}R" if wins else "N/A",
        "Avg Loss": f"{losing_r.mean():.2f}R" if losses else "N/A",
        "Profit Factor": profit_factor,
        "Max Drawdown": f"{max_drawdown:.2f}R",
    }


def _finish_grouped(grouped: pd.DataFrame, *, include_avg: bool = True) -> pd.DataFrame:
    grouped = grouped.copy()
    grouped["Wins"] = grouped["Wins"].astype(int)
    grouped["WinRate"] = (grouped["WinRate"] * 100).round(1).astype(str) + "%"
    grouped["TotalR"] = grouped["TotalR"].round(2)
    if include_avg and "AvgR" in grouped.columns:
        grouped["AvgR"] = grouped["AvgR"].round(2)
    return grouped


def winrate_by_setup(df: pd.DataFrame) -> pd.DataFrame:
    if "Setup" not in df.columns:
        return pd.DataFrame()
    grouped = df.groupby("Setup").agg(
        Trades=("IsWin", "count"),
        Wins=("IsWin", "sum"),
        WinRate=("IsWin", "mean"),
        TotalR=("PL_R", "sum"),
        AvgR=("PL_R", "mean"),
    )
    grouped = grouped.sort_values("TotalR", ascending=False)
    return _finish_grouped(grouped)


def winrate_by_day(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("DayOfWeek").agg(
        Trades=("IsWin", "count"),
        Wins=("IsWin", "sum"),
        WinRate=("IsWin", "mean"),
        TotalR=("PL_R", "sum"),
    )
    weekday_order = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    ordered = [day for day in weekday_order if day in grouped.index]
    ordered += sorted(set(grouped.index) - set(ordered))
    grouped = grouped.reindex(ordered)
    return _finish_grouped(grouped, include_avg=False)


def winrate_by_session(df: pd.DataFrame) -> pd.DataFrame:
    if "Session" not in df.columns:
        return pd.DataFrame()
    grouped = df.groupby("Session").agg(
        Trades=("IsWin", "count"),
        Wins=("IsWin", "sum"),
        WinRate=("IsWin", "mean"),
        TotalR=("PL_R", "sum"),
    )
    grouped = grouped.sort_values("TotalR", ascending=False)
    return _finish_grouped(grouped, include_avg=False)


def mistake_analysis(df: pd.DataFrame) -> pd.DataFrame:
    if "Mistake" not in df.columns:
        return pd.DataFrame()
    mistake_names = df["Mistake"].astype("string").str.strip()
    mistakes = df[~mistake_names.str.lower().isin(["none", "", "nan", "<na>"])].copy()
    if mistakes.empty:
        return pd.DataFrame()
    grouped = mistakes.groupby("Mistake").agg(
        Count=("PL_R", "count"),
        TotalRLost=("PL_R", "sum"),
        AvgR=("PL_R", "mean"),
    )
    grouped = grouped.sort_values("TotalRLost")
    grouped["TotalRLost"] = grouped["TotalRLost"].round(2)
    grouped["AvgR"] = grouped["AvgR"].round(2)
    return grouped


def emotion_analysis(df: pd.DataFrame) -> pd.DataFrame:
    if "Emotion" not in df.columns:
        return pd.DataFrame()
    grouped = df.groupby("Emotion").agg(
        Trades=("IsWin", "count"),
        WinRate=("IsWin", "mean"),
        TotalR=("PL_R", "sum"),
        AvgR=("PL_R", "mean"),
    )
    grouped = grouped.sort_values("TotalR", ascending=False)
    grouped["WinRate"] = (grouped["WinRate"] * 100).round(1).astype(str) + "%"
    grouped["TotalR"] = grouped["TotalR"].round(2)
    grouped["AvgR"] = grouped["AvgR"].round(2)
    return grouped


def rr_analysis(df: pd.DataFrame) -> dict[str, str]:
    result: dict[str, str] = {}
    if "Planned_RR" in df.columns:
        planned = df["Planned_RR"].replace([np.inf, -np.inf], np.nan).dropna()
        if not planned.empty:
            result["Avg Planned R:R"] = f"{planned.mean():.2f}"

    actual_wins = df.loc[df["IsWin"], "PL_R"]
    actual_losses = df.loc[df["IsLoss"], "PL_R"]
    if not actual_wins.empty:
        result["Actual Avg Win R"] = f"{actual_wins.mean():.2f}"
    if not actual_losses.empty:
        result["Actual Avg Loss R"] = f"{abs(actual_losses.mean()):.2f}"
    if not actual_wins.empty and not actual_losses.empty:
        result["Actual R:R Achieved"] = (
            f"{actual_wins.mean() / abs(actual_losses.mean()):.2f}"
        )
    return result


def generate_system_draft(df: pd.DataFrame) -> str:
    """Generate a plain-text candidate rule sheet from descriptive statistics."""
    lines = [
        "=" * 58,
        "   YOUR TRADING SYSTEM — DRAFT v1",
        "   Auto-generated from your journal data",
        "=" * 58,
        f"Sample: {len(df)} trades | {df['Date'].min().date()} to {df['Date'].max().date()}",
        "",
    ]

    setup_df = winrate_by_setup(df)
    if not setup_df.empty:
        best = setup_df["TotalR"].idxmax()
        best_r = setup_df.loc[best, "TotalR"]
        lines.extend(["✅ DO:", f"   • Study and repeat your {best} process ({best_r:+.2f}R total).", ""])
        if len(setup_df) > 1:
            worst = setup_df["TotalR"].idxmin()
            worst_r = setup_df.loc[worst, "TotalR"]
            if worst_r < 0:
                lines.extend([
                    "🚫 DON'T:",
                    f"   • Trade {worst} unchanged; it lost {abs(worst_r):.2f}R. Review or pause it.",
                    "",
                ])
            else:
                lines.extend([
                    "🔎 REVIEW:",
                    f"   • {worst} is your lowest-R setup, but still net positive ({worst_r:+.2f}R).",
                    "   • Do not discard it without a larger sample and trade-level review.",
                    "",
                ])

    day_df = winrate_by_day(df)
    if not day_df.empty:
        best_day = day_df["TotalR"].idxmax()
        worst_day = day_df["TotalR"].idxmin()
        lines.extend([
            "✅ TIMING:",
            f"   • Review why {best_day} produced your strongest result ({day_df.loc[best_day, 'TotalR']:+.2f}R).",
        ])
        if worst_day != best_day and day_df.loc[worst_day, "TotalR"] < 0:
            lines.append(f"   • Avoid forcing {worst_day} trades; it is your weakest day ({day_df.loc[worst_day, 'TotalR']:+.2f}R).")
        else:
            lines.append(f"   • {worst_day} has the lowest total R; no weekday in this sample is net negative.")
        lines.append("")

    session_df = winrate_by_session(df)
    if not session_df.empty:
        best_session = session_df["TotalR"].idxmax()
        lines.extend([
            "✅ SESSION FOCUS:",
            f"   • Start your review with {best_session} ({session_df.loc[best_session, 'TotalR']:+.2f}R total).",
            "",
        ])

    mistakes_df = mistake_analysis(df)
    if not mistakes_df.empty:
        worst_mistake = mistakes_df["TotalRLost"].idxmin()
        cost = mistakes_df.loc[worst_mistake, "TotalRLost"]
        lines.append("🚫 BIGGEST LOGGED LEAK:")
        if cost < 0:
            lines.append(f"   • '{worst_mistake}' trades netted {cost:.2f}R.")
        else:
            lines.append(f"   • '{worst_mistake}' has the lowest R among logged mistakes ({cost:+.2f}R).")
        lines.extend([
            "   • Candidate rule: if you catch yourself repeating it, stop and reassess before another entry.",
            "",
        ])

    emotions_df = emotion_analysis(df)
    if not emotions_df.empty:
        worst_emotion = emotions_df["TotalR"].idxmin()
        emotion_r = emotions_df.loc[worst_emotion, "TotalR"]
        lines.extend([
            "⚠️ EMOTION CHECK:",
            f"   • '{worst_emotion}' has the lowest observed total ({emotion_r:+.2f}R).",
            "   • Candidate rule: reduce size or walk away until you can follow your checklist.",
            "",
        ])

    rr = rr_analysis(df)
    if rr:
        lines.append("📊 R:R REALITY CHECK:")
        lines.extend(f"   • {key}: {value}" for key, value in rr.items())
        lines.extend([
            "   • Candidate rule: test requiring planned R:R ≥ 2.0; validate it on more trades.",
            "",
        ])

    if len(df) < 30:
        lines.extend([
            "⚠️ SAMPLE-SIZE WARNING:",
            "   • Fewer than 30 trades can describe your journal, but cannot establish a reliable edge.",
            "   • Treat every rule above as a hypothesis to test, not proof of causation.",
            "",
        ])

    lines.extend([
        "=" * 58,
        "Draft v1 evolves as you add trades. Descriptive analysis only; not financial advice.",
        "=" * 58,
    ])
    return "\n".join(lines)


def full_report(df: pd.DataFrame) -> dict[str, Any]:
    """Return every analysis section needed by the Streamlit frontend."""
    return {
        "overall": overall_stats(df),
        "by_setup": winrate_by_setup(df),
        "by_day": winrate_by_day(df),
        "by_session": winrate_by_session(df),
        "mistakes": mistake_analysis(df),
        "emotions": emotion_analysis(df),
        "rr": rr_analysis(df),
        "system_draft": generate_system_draft(df),
    }
