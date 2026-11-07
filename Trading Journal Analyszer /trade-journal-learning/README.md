# Trade Journal Continuous Learning System — Phase 1

A **new, separate, local-only** FastAPI + React application. It learns descriptive placeholders from a local mock of a manual trading journal and displays synchronized-symbol M5/M5-HA and M1 charts.

**The Vercel journal is never contacted.** There is no remote HTTP client, credential, endpoint, or write adapter in this project. `template.csv` stands in for a future read-only API or Supabase replica.

## Run at localhost:8000

From this project directory:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cd frontend
npm install
npm run build
cd ..

uvicorn app:app --reload
```

Open **http://localhost:8000**. FastAPI serves both the API and the compiled React frontend. API documentation is at **http://localhost:8000/docs**.

### Generating the Fernet key

`.env` is git-ignored and is **not** part of the repository, so you must create it once on a fresh clone — the app refuses to learn without it (`LEARNED_SYSTEM_FERNET_KEY is missing from .env`). Generate the key, then do not commit or share the file:

```bash
python -c "from pathlib import Path; from cryptography.fernet import Fernet; Path('.env').write_text('LEARNED_SYSTEM_FERNET_KEY=' + Fernet.generate_key().decode() + '\n')"
```

Generating a new key makes the previous `data/learned_system.json` undecryptable. Delete that file and restart to re-learn and encrypt with the new key.

## Vite development mode

Keep the backend running on port 8000, then use a second terminal:

```bash
cd frontend && npm run dev
```

Open **http://localhost:5173**. Vite proxies only relative `/api` requests to `127.0.0.1:8000`. The browser never calls a remote journal or market-data service.

## API

| Method | Endpoint | Behavior |
|---|---|---|
| GET | `/api/journal/read-only` | Reads the local SQLite mirror using `mode=ro`, `PRAGMA query_only=ON`, and one `SELECT` query |
| GET | `/api/patterns/analyze` | Re-reads `template.csv`, refreshes the local mirror, recalculates the report, and encrypts learned rules |
| GET | `/api/charts/data?symbol=XAUUSD&timeframe=M5` | Returns 180 deterministic simulated OHLC candles plus calculated HA candles |
| GET | `/api/system/status` | Returns the last learning timestamp, selected placeholder, and setup/execution rules |
| GET | `/api/health` | Reports local-only/read-only service health |

Supported chart symbols are `XAUUSD`, `EURUSD`, and `GBPUSD`; supported chart timeframes are `M1` and `M5`. One symbol selector updates both charts.

## Continuous learning

Learning runs:

1. On FastAPI startup.
2. Whenever `/api/patterns/analyze` is called.
3. Automatically when the local CSV fingerprint changes; the app polls every two seconds.

Outputs — everything under `data/` is generated locally and git-ignored, so a fresh clone starts with no `data/` directory and the app creates it on first run:

- `data/report.json` — plaintext overall win rate, setup/time breakdowns, common mistakes, and loss reasons.
- `data/trades.db` — local SQLite mirror of the journal.
- `data/learned_system.json` — **Fernet-encrypted bytes**, despite the `.json` suffix. Decrypt only with the key in `.env`, which is why it is never committed.
- `data/security.log` — blocked Vercel mutation attempts.

The M5 placeholders are:

- `Pattern_A`: HA uptrend + pullback.
- `Pattern_B`: HA downtrend + pullback.

The M1 placeholder confirmation is `HA reversal candle + volume spike`. These are scaffolding for later research, not validated trading signals.

## Heikin Ashi calculation

For each candle:

```text
HA_Close = (Open + High + Low + Close) / 4
HA_Open  = (previous HA_Open + previous HA_Close) / 2
HA_High  = max(High, HA_Open, HA_Close)
HA_Low   = min(Low, HA_Open, HA_Close)
```

The first HA open is seeded as `(Open + Close) / 2`. The left chart's **HA ON/OFF** control switches between backend-calculated HA and standard candles. The right chart always shows standard M1 candles.

**Chart prices are simulated locally.** They are not live or historical market data. This is necessary because the current phase prohibits external calls.

## Read-only security boundary

- No code writes to `template.csv` during normal application operation.
- Only the local SQLite mirror is inserted into/refreshed during learning.
- `read_trades_select_only()` uses a SQLite read-only URI, query-only pragma, authorizer, and a `SELECT` statement.
- `security.py` provides `enforce_read_only_request(method, url)`. It raises `ReadOnlyViolation` for `POST`, `PUT`, `PATCH`, or `DELETE` to a `.vercel.app` host and logs exactly `READ-ONLY VIOLATION BLOCKED`.
- Any future remote read adapter must pass through that guard before constructing a request. No such remote adapter exists in Phase 1.
- API responses carry `X-Data-Policy: LOCAL-ONLY; JOURNAL-READ-ONLY`.

## Tests

```bash
python -m unittest discover -s tests -v
cd frontend && npm run build
```

The tests cover journal loading, report sections, SQLite query-only enforcement, learned-rule encryption, exact HA math, deterministic/valid OHLC, and Vercel POST blocking.

A headless Chromium smoke test also verified two rendered chart panels, a pixel-changing HA toggle, synchronized symbol selection, journal/status rendering, zero browser errors, and zero external requests. Chart localization is pinned to `en-ZA` so rendering does not depend on an invalid operating-system locale.

The live integration test also appended one **temporary** row to `template.csv`, called `/api/patterns/analyze`, and verified:

```text
10 -> 11 trades
report.json updated to 63.64% win rate and +13.02R
journal endpoint returned 11 rows through SELECT_ONLY
baseline restored to 10 trades afterward
```

## Project layout

```text
app.py                  FastAPI API, simulated OHLC, HA math, frontend hosting
analyser.py             CSV loader, SQLite mirror, pattern brain, encrypted learning
security.py             Vercel mutation guard and security log
template.csv            Local read-only journal mock
frontend/               Vite + React + official lightweight-charts package
tests/test_system.py    Backend and security tests
data/                   Generated DB, report, encrypted rules, and logs
```
