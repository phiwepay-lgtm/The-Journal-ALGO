"""Local pattern brain for the Trade Journal Continuous Learning System.

The journal source is a local CSV mock. A refresh may write the local SQLite
mirror, but every journal read performed by read_trades_select_only() uses a
SQLite read-only connection and a SELECT statement. No remote client exists.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
JOURNAL_PATH = BASE_DIR / "template.csv"
DB_PATH = DATA_DIR / "trades.db"
REPORT_PATH = DATA_DIR / "report.json"
LEARNED_PATH = DATA_DIR / "learned_system.json"
ENV_PATH = BASE_DIR / ".env"

DATA_DIR.mkdir(parents=True, exist_ok=True)
load_dotenv(ENV_PATH)

REQUIRED_COLUMNS = ["Date", "Pair", "Direction", "Setup", "Entry", "Exit", "PL_R"]
LEARNING_LOCK = threading.RLock()


def journal_fingerprint() -> str:
    """Return a SHA-256 fingerprint used to detect new/changed CSV entries."""
    return hashlib.sha256(JOURNAL_PATH.read_bytes()).hexdigest()


def _column_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


COLUMN_ALIASES = {
    "date": "Date",
    "pair": "Pair",
    "symbol": "Pair",
    "direction": "Direction",
    "side": "Direction",
    "setup": "Setup",
    "entry": "Entry",
    "stop": "Stop",
    "target": "Target",
    "exit": "Exit",
    "plr": "PL_R",
    "r": "PL_R",
    "rmultiple": "PL_R",
    "resultinr": "PL_R",
    "timeframe": "Timeframe",
    "session": "Session",
    "emotion": "Emotion",
    "mistake": "Mistake",
    "notes": "Notes",
}


def load_journal() -> pd.DataFrame:
    """Read and clean template.csv without modifying the source file."""
    df = pd.read_csv(JOURNAL_PATH)
    df.columns = [COLUMN_ALIASES.get(_column_key(col), str(col).strip()) for col in df.columns]

    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Journal is missing required columns: {missing}")

    original_rows = len(df)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", format="mixed")
    df["Pair"] = df["Pair"].astype("string").str.strip().str.upper().fillna("UNSPECIFIED")
    df["Direction"] = df["Direction"].astype("string").str.strip().str.upper().fillna("UNSPECIFIED")
    df["Setup"] = df["Setup"].astype("string").str.strip().replace("", "Unspecified").fillna("Unspecified")

    for column in ["Entry", "Exit", "PL_R", "Stop", "Target"]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    if "Timeframe" in df.columns:
        df["Timeframe"] = df["Timeframe"].astype("string").str.strip().str.upper().fillna("UNSPECIFIED")
    else:
        df["Timeframe"] = "UNSPECIFIED"

    for column in ["Session", "Emotion", "Mistake"]:
        if column not in df.columns:
            df[column] = "None" if column == "Mistake" else "Unspecified"
        df[column] = df[column].astype("string").str.strip()
        blank = df[column].eq("") | df[column].isna()
        df.loc[blank, column] = "None" if column == "Mistake" else "Unspecified"

    if "Notes" not in df.columns:
        df["Notes"] = ""
    df["Notes"] = df["Notes"].astype("string").fillna("")

    df = df.dropna(subset=["Date", "PL_R"]).sort_values("Date").reset_index(drop=True)
    if df.empty:
        raise ValueError("No valid journal rows remain; check Date and PL_R.")

    df["IsWin"] = df["PL_R"] > 0
    df["IsLoss"] = df["PL_R"] < 0
    df["DayOfWeek"] = df["Date"].dt.day_name()
    df["Hour"] = df["Date"].dt.hour
    df.attrs["rows_dropped"] = original_rows - len(df)
    return df


def _nullable(value: Any) -> Any:
    return None if pd.isna(value) else value


def refresh_local_sqlite(df: pd.DataFrame) -> None:
    """Refresh the LOCAL mirror. This function never connects to a remote app."""
    records = []
    for source_row, (_, row) in enumerate(df.iterrows(), start=2):
        records.append(
            (
                source_row,
                row["Date"].isoformat(),
                str(row["Pair"]),
                str(row["Direction"]),
                str(row["Setup"]),
                float(row["Entry"]) if pd.notna(row["Entry"]) else None,
                float(row["Stop"]) if "Stop" in row and pd.notna(row["Stop"]) else None,
                float(row["Target"]) if "Target" in row and pd.notna(row["Target"]) else None,
                float(row["Exit"]) if pd.notna(row["Exit"]) else None,
                float(row["PL_R"]),
                str(row["Timeframe"]),
                str(row["Session"]),
                str(row["Emotion"]),
                str(row["Mistake"]),
                str(row["Notes"]),
                str(row["DayOfWeek"]),
                int(row["Hour"]),
            )
        )

    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS trades (
                source_row INTEGER PRIMARY KEY,
                date TEXT NOT NULL,
                pair TEXT NOT NULL,
                direction TEXT NOT NULL,
                setup TEXT NOT NULL,
                entry REAL,
                stop REAL,
                target REAL,
                exit REAL,
                pl_r REAL NOT NULL,
                timeframe TEXT,
                session TEXT,
                emotion TEXT,
                mistake TEXT,
                notes TEXT,
                day_of_week TEXT,
                hour INTEGER
            );
            """
        )
        connection.execute("DELETE FROM trades")
        connection.executemany(
            """
            INSERT INTO trades (
                source_row, date, pair, direction, setup, entry, stop, target,
                exit, pl_r, timeframe, session, emotion, mistake, notes,
                day_of_week, hour
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            records,
        )


def read_trades_select_only() -> list[dict[str, Any]]:
    """Read the local mirror through a SQLite SELECT-only connection."""
    if not DB_PATH.exists():
        refresh_local_sqlite(load_journal())

    connection = sqlite3.connect(f"{DB_PATH.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")

    denied_actions = {
        sqlite3.SQLITE_INSERT,
        sqlite3.SQLITE_UPDATE,
        sqlite3.SQLITE_DELETE,
        sqlite3.SQLITE_CREATE_TABLE,
        sqlite3.SQLITE_DROP_TABLE,
        sqlite3.SQLITE_ALTER_TABLE,
    }
    connection.set_authorizer(
        lambda action, *_: sqlite3.SQLITE_DENY if action in denied_actions else sqlite3.SQLITE_OK
    )
    try:
        rows = connection.execute(
            """
            SELECT source_row, date, pair, direction, setup, entry, stop, target,
                   exit, pl_r, timeframe, session, emotion, mistake, notes,
                   day_of_week, hour
            FROM trades
            ORDER BY date ASC, source_row ASC
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _overall(df: pd.DataFrame) -> dict[str, Any]:
    wins = int(df["IsWin"].sum())
    losses = int(df["IsLoss"].sum())
    return {
        "trades": len(df),
        "wins": wins,
        "losses": losses,
        "breakeven": len(df) - wins - losses,
        "win_rate": round(wins / len(df) * 100, 2),
        "total_r": round(float(df["PL_R"].sum()), 2),
        "average_r": round(float(df["PL_R"].mean()), 3),
    }


def _group_stats(df: pd.DataFrame, column: str) -> list[dict[str, Any]]:
    if df.empty:
        return []
    grouped = df.groupby(column, dropna=False).agg(
        trades=("PL_R", "size"),
        wins=("IsWin", "sum"),
        losses=("IsLoss", "sum"),
        total_r=("PL_R", "sum"),
        average_r=("PL_R", "mean"),
    )
    records = []
    for label, row in grouped.iterrows():
        records.append(
            {
                column.lower(): str(label),
                "trades": int(row["trades"]),
                "wins": int(row["wins"]),
                "losses": int(row["losses"]),
                "win_rate": round(float(row["wins"] / row["trades"] * 100), 2),
                "total_r": round(float(row["total_r"]), 2),
                "average_r": round(float(row["average_r"]), 3),
            }
        )
    return sorted(records, key=lambda item: item["total_r"], reverse=True)


def _common_mistakes(df: pd.DataFrame) -> list[dict[str, Any]]:
    mask = ~df["Mistake"].astype("string").str.strip().str.lower().isin(["none", "", "nan", "<na>"])
    records = _group_stats(df.loc[mask], "Mistake")
    return sorted(records, key=lambda item: (-item["trades"], item["total_r"]))


def _loss_reasons(df: pd.DataFrame) -> list[dict[str, Any]]:
    losses = df.loc[df["IsLoss"]].copy()
    if losses.empty:
        return []
    losses["LossReason"] = losses["Mistake"].astype("string")
    no_reason = losses["LossReason"].str.strip().str.lower().isin(["none", "", "nan", "<na>"])
    losses.loc[no_reason, "LossReason"] = "No mistake logged"
    records = _group_stats(losses, "LossReason")
    return sorted(records, key=lambda item: item["total_r"])


def learn_setup_pattern(df: pd.DataFrame | None = None) -> dict[str, Any]:
    """M5 setup placeholders, ranked by observed LONG versus SHORT outcomes."""
    df = load_journal() if df is None else df
    direction_stats = {
        direction: df.loc[df["Direction"].eq(direction), "PL_R"] for direction in ["LONG", "SHORT"]
    }
    summaries = {
        direction: {
            "observed_trades": len(values),
            "win_rate": round(float((values > 0).mean() * 100), 2) if len(values) else 0.0,
            "total_r": round(float(values.sum()), 2),
        }
        for direction, values in direction_stats.items()
    }
    selected = "Pattern_A" if summaries["LONG"]["total_r"] >= summaries["SHORT"]["total_r"] else "Pattern_B"
    return {
        "timeframe": "M5",
        "selected": selected,
        "status": selected.replace("_", " ") + " found",
        "placeholder_logic": True,
        "patterns": {
            "Pattern_A": {
                "logic": "HA uptrend + pullback",
                "direction": "LONG",
                **summaries["LONG"],
            },
            "Pattern_B": {
                "logic": "HA downtrend + pullback",
                "direction": "SHORT",
                **summaries["SHORT"],
            },
        },
    }


def learn_execution_pattern(df: pd.DataFrame | None = None) -> dict[str, Any]:
    """M1 execution placeholder; no claim that confirmation has been validated."""
    df = load_journal() if df is None else df
    m1 = df.loc[df["Timeframe"].eq("M1")]
    return {
        "timeframe": "M1",
        "name": "Execution_Confirmation",
        "confirmation": "HA reversal candle + volume spike",
        "placeholder_logic": True,
        "observed_m1_trades": len(m1),
        "observed_m1_win_rate": round(float(m1["IsWin"].mean() * 100), 2) if len(m1) else 0.0,
    }


def _fernet() -> Fernet:
    key = os.getenv("LEARNED_SYSTEM_FERNET_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "LEARNED_SYSTEM_FERNET_KEY is missing from .env. Create that file with the line "
            "'LEARNED_SYSTEM_FERNET_KEY=<key>' where <key> comes from Fernet.generate_key() "
            "(see README: Generating a new key)."
        )
    return Fernet(key.encode("utf-8"))


def read_learned_system() -> dict[str, Any]:
    """Decrypt learned_system.json for local API use."""
    if not LEARNED_PATH.exists():
        raise FileNotFoundError("Learned system has not been generated yet.")
    try:
        payload = _fernet().decrypt(LEARNED_PATH.read_bytes())
    except InvalidToken as exc:
        raise RuntimeError(
            f"{LEARNED_PATH.name} was encrypted with a different key. Delete it and restart "
            "to re-learn and encrypt with the key in .env."
        ) from exc
    return json.loads(payload.decode("utf-8"))


def continuous_learning() -> dict[str, Any]:
    """Rebuild the report and learned rules from the latest CSV contents."""
    with LEARNING_LOCK:
        df = load_journal()
        refresh_local_sqlite(df)
        generated_at = datetime.now(timezone.utc).isoformat()
        fingerprint = journal_fingerprint()
        setup = learn_setup_pattern(df)
        execution = learn_execution_pattern(df)

        report = {
            "generated_at": generated_at,
            "source": {
                "type": "LOCAL_CSV_MOCK",
                "file": "template.csv",
                "sha256": fingerprint,
                "remote_access": "NONE",
                "local_journal_query": "SELECT_ONLY",
            },
            "overall": _overall(df),
            "win_rate_by_setup": _group_stats(df, "Setup"),
            "win_rate_by_time": {
                "by_hour": _group_stats(df.assign(Hour=df["Hour"].map(lambda h: f"{h:02d}:00")), "Hour"),
                "by_day": _group_stats(df, "DayOfWeek"),
                "by_session": _group_stats(df, "Session"),
            },
            "common_mistakes": _common_mistakes(df),
            "loss_reasons": _loss_reasons(df),
        }
        learned = {
            "version": 1,
            "last_learned_from_journal": generated_at,
            "journal_sha256": fingerprint,
            "journal_trade_count": len(df),
            "system_status": setup["status"],
            "setup_learning": setup,
            "execution_learning": execution,
        }

        report_tmp = REPORT_PATH.with_suffix(".json.tmp")
        report_tmp.write_text(json.dumps(report, indent=2), encoding="utf-8")
        os.replace(report_tmp, REPORT_PATH)

        encrypted = _fernet().encrypt(json.dumps(learned, indent=2).encode("utf-8"))
        learned_tmp = LEARNED_PATH.with_suffix(".json.tmp")
        learned_tmp.write_bytes(encrypted)
        os.replace(learned_tmp, LEARNED_PATH)
        return report
