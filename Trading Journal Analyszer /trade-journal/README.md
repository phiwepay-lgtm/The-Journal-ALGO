# Trade Journal System — Phase 1

A local Streamlit dashboard that turns a CSV or Excel trade journal into descriptive performance statistics and a downloadable draft rule sheet.

## Run

```bash
cd trade-journal
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Open the local URL printed by Streamlit (normally `http://localhost:8501`). Use **Explore sample journal** in the sidebar to try the app without uploading anything.

## Journal format

Required columns:

- `Date` — trade date or timestamp
- `Pair` — instrument, such as EURUSD or XAUUSD
- `Direction` — LONG or SHORT
- `Setup` — setup name
- `Entry`, `Exit` — prices
- `PL_R` — realized result in R multiples (for example, `2.5` or `-1`)

Optional columns: `Stop`, `Target`, `Timeframe`, `Session`, `Emotion`, `Mistake`, `Notes`.

Column matching is case-insensitive and ignores spaces, hyphens, and underscores. `R`, `R Multiple`, `Result in R`, and `PnL R` are also recognized as `PL_R`.

## Included

- Overall win rate, expectancy, profit factor, and maximum R drawdown
- Cumulative-R equity curve
- Setup, weekday, and session breakdowns
- Mistake and emotion summaries
- Planned versus achieved R:R
- Downloadable system draft and cleaned CSV
- CSV, XLSX, and XLS import
- Unit tests for ingestion and the supplied sample calculations

## Test

```bash
python -m unittest discover -s tests -v
```

The supplied ten-row sample totals **+11.75R**. FVG is its highest-R setup at **+5.95R**, and Friday contributes **+4.92R**. These values are descriptive only. The draft generator explicitly warns when fewer than 30 trades are available; a small journal cannot establish a statistically reliable trading edge.

## Notes

Analysis runs inside the app process. No LLM or external analytics service is called. This project is a journaling tool, not financial advice.
