# The-Journal-ALGO

Local-only trading-journal analysis tooling. Two independent apps live under
`Trading Journal Analyszer /` (the trailing space in that folder name is part of the name):

| Folder | What it is | Stack | Run |
| --- | --- | --- | --- |
| `trade-journal` | Descriptive performance stats and a draft rule sheet from a CSV/Excel journal | Streamlit + pandas + Plotly | `streamlit run app.py` → `http://localhost:8501` |
| `trade-journal-learning` | Continuous-learning system: read-only journal mirror, pattern placeholders, M5/M5-HA + M1 charts | FastAPI + SQLite + Vite/React + lightweight-charts | `uvicorn app:app` → `http://localhost:8000` |

Each folder has its own `README.md` with full setup, API, and security notes. Both projects are
deliberately offline: no remote journal is contacted, no market-data API is called, and nothing
writes to the sample journal.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate

pip install -r "Trading Journal Analyszer /trade-journal/requirements.txt"
pip install -r "Trading Journal Analyszer /trade-journal-learning/requirements.txt"

cd "Trading Journal Analyszer /trade-journal-learning/frontend"
npm ci && npm run build
```

Then start whichever app you want (see the table above).

## Tests

Run from each project directory (the `tests` folder is not a package, so discovery needs the
project root as the working directory):

```bash
cd "Trading Journal Analyszer /trade-journal"            && python -m unittest discover -s tests -v
cd "Trading Journal Analyszer /trade-journal-learning"   && python -m unittest discover -s tests -v
```

`trade-journal-learning` tests need the `.env` Fernet key described above.

## Never committed

`.env` (the Fernet key for `trade-journal-learning`) and everything under `data/` — the SQLite
mirror, report, encrypted learned rules, and security log are generated on first run. See
`.gitignore`.

These projects are journaling tools, not financial advice.
