import { useCallback, useEffect, useMemo, useState } from 'react';
import Chart from './Chart.jsx';

const SYMBOLS = ['XAUUSD', 'EURUSD', 'GBPUSD'];

async function api(path) {
  const response = await fetch(path, { headers: { Accept: 'application/json' } });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${response.status}: ${detail}`);
  }
  return response.json();
}

function formatTime(value) {
  if (!value) return 'Not yet learned';
  return new Date(value).toLocaleString('en-ZA');
}

function PatternCard({ eyebrow, title, children }) {
  return (
    <article className="pattern-card">
      <span className="eyebrow">{eyebrow}</span>
      <h3>{title}</h3>
      <div>{children}</div>
    </article>
  );
}

export default function App() {
  const [symbol, setSymbol] = useState('XAUUSD');
  const [showHA, setShowHA] = useState(true);
  const [charts, setCharts] = useState({ M5: null, M1: null });
  const [journal, setJournal] = useState(null);
  const [status, setStatus] = useState(null);
  const [loadingCharts, setLoadingCharts] = useState(true);
  const [learning, setLearning] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setLoadingCharts(true);
    Promise.all([
      api(`/api/charts/data?symbol=${symbol}&timeframe=M5`),
      api(`/api/charts/data?symbol=${symbol}&timeframe=M1`),
    ]).then(([m5, m1]) => {
      if (active) setCharts({ M5: m5, M1: m1 });
    }).catch((reason) => {
      if (active) setError(`Chart load failed: ${reason.message}`);
    }).finally(() => {
      if (active) setLoadingCharts(false);
    });
    return () => { active = false; };
  }, [symbol]);

  const loadJournalState = useCallback(async () => {
    const [journalData, statusData] = await Promise.all([
      api('/api/journal/read-only'),
      api('/api/system/status'),
    ]);
    setJournal(journalData);
    setStatus(statusData);
  }, []);

  useEffect(() => {
    loadJournalState().catch((reason) => setError(`Journal load failed: ${reason.message}`));
  }, [loadJournalState]);

  const relearn = async () => {
    setLearning(true);
    setError('');
    try {
      await api('/api/patterns/analyze');
      await loadJournalState();
    } catch (reason) {
      setError(`Learning failed: ${reason.message}`);
    } finally {
      setLearning(false);
    }
  };

  const summary = useMemo(() => {
    const trades = journal?.trades ?? [];
    const totalR = trades.reduce((sum, trade) => sum + trade.pl_r, 0);
    const wins = trades.filter((trade) => trade.pl_r > 0).length;
    return {
      totalR,
      winRate: trades.length ? (wins / trades.length) * 100 : 0,
    };
  }, [journal]);

  const setup = status?.setup_learning;
  const execution = status?.execution_learning;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <div className="brand-line"><span className="brand-mark">JL</span><span>LOCAL LEARNING LAB</span></div>
          <h1>Trade Journal <span>Continuous Learning</span></h1>
          <p>Pattern research from your manual journal. Localhost only. Read-only by design.</p>
        </div>
        <div className="header-actions">
          <span className="local-pill"><i />LOCAL ONLY</span>
          <button className="primary-button" onClick={relearn} disabled={learning}>
            {learning ? 'Learning…' : 'Relearn journal'}
          </button>
        </div>
      </header>

      {error && <div className="error-banner" role="alert">{error}<button onClick={() => setError('')}>Dismiss</button></div>}

      <section className="control-deck">
        <div className="symbol-control">
          <label htmlFor="symbol">CHART SYMBOL · SYNCHRONIZED</label>
          <select id="symbol" value={symbol} onChange={(event) => setSymbol(event.target.value)}>
            {SYMBOLS.map((item) => <option key={item}>{item}</option>)}
          </select>
        </div>
        <div className="status-grid">
          <div className="status-item">
            <span>LAST LEARNED FROM JOURNAL</span>
            <strong>{formatTime(status?.last_learned_from_journal)}</strong>
          </div>
          <div className="status-item system-found">
            <span>LEARNED SYSTEM</span>
            <strong>{status?.system ?? 'System: Learning…'}</strong>
          </div>
          <div className="status-item">
            <span>JOURNAL ACCESS</span>
            <strong>{journal ? `${journal.count} trades · ${journal.access}` : 'Loading SELECT-only reader…'}</strong>
          </div>
        </div>
      </section>

      <main>
        <section className="charts-grid">
          <article className="chart-panel">
            <div className="chart-heading">
              <div><span className="panel-index">01</span><h2>SETUP - M5 HA</h2></div>
              <button className={`toggle ${showHA ? 'active' : ''}`} onClick={() => setShowHA((value) => !value)}>
                HA {showHA ? 'ON' : 'OFF'}
              </button>
            </div>
            <div className="chart-subline"><span>{symbol} / 5 MIN</span><span>{showHA ? 'HEIKIN ASHI' : 'STANDARD CANDLES'}</span></div>
            {loadingCharts && <div className="chart-loading">Loading local M5 data…</div>}
            {charts.M5 && <Chart data={charts.M5} useHA={showHA} priceFormat={charts.M5.price_format} />}
          </article>

          <article className="chart-panel">
            <div className="chart-heading">
              <div><span className="panel-index">02</span><h2>EXECUTION - M1</h2></div>
              <span className="execution-badge">CONFIRMATION</span>
            </div>
            <div className="chart-subline"><span>{symbol} / 1 MIN</span><span>STANDARD CANDLES</span></div>
            {loadingCharts && <div className="chart-loading">Loading local M1 data…</div>}
            {charts.M1 && <Chart data={charts.M1} useHA={false} priceFormat={charts.M1.price_format} />}
          </article>
        </section>
        <div className="data-disclosure">SIMULATED LOCAL OHLC · Formula-tested Heikin Ashi · No external market-data requests</div>

        <section className="learning-grid">
          <PatternCard eyebrow="M5 SETUP LOGIC · PLACEHOLDER" title={setup?.selected?.replace('_', ' ') ?? 'Learning setup'}>
            <p>{setup?.patterns?.[setup.selected]?.logic ?? 'HA trend + pullback'}</p>
            <div className="rule-metric"><span>Observed direction R</span><strong>{setup ? `${setup.patterns[setup.selected].total_r.toFixed(2)}R` : '—'}</strong></div>
          </PatternCard>
          <PatternCard eyebrow="M1 EXECUTION LOGIC · PLACEHOLDER" title="Confirmation">
            <p>{execution?.confirmation ?? 'HA reversal candle + volume spike'}</p>
            <div className="rule-metric"><span>Observed M1 journal trades</span><strong>{execution?.observed_m1_trades ?? '—'}</strong></div>
          </PatternCard>
          <PatternCard eyebrow="JOURNAL SNAPSHOT · SQLITE SELECT" title="Observed performance">
            <div className="snapshot-metrics">
              <div><strong>{summary.winRate.toFixed(1)}%</strong><span>Win rate</span></div>
              <div><strong className={summary.totalR >= 0 ? 'positive' : 'negative'}>{summary.totalR.toFixed(2)}R</strong><span>Total R</span></div>
              <div><strong>{journal?.count ?? '—'}</strong><span>Trades read</span></div>
            </div>
          </PatternCard>
        </section>

        <section className="journal-panel">
          <div className="section-heading">
            <div><span className="eyebrow">SOURCE PREVIEW</span><h2>Journal rows read locally</h2></div>
            <span className="readonly-badge">READ-ONLY · NO REMOTE WRITES</span>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Date</th><th>Pair</th><th>Direction</th><th>Setup</th><th>Session</th><th>Mistake</th><th>Result</th></tr></thead>
              <tbody>
                {(journal?.trades ?? []).slice(-8).reverse().map((trade) => (
                  <tr key={trade.source_row}>
                    <td>{new Date(trade.date).toLocaleDateString('en-ZA')}</td>
                    <td className="mono">{trade.pair}</td>
                    <td><span className={`direction ${trade.direction.toLowerCase()}`}>{trade.direction}</span></td>
                    <td>{trade.setup}</td>
                    <td>{trade.session}</td>
                    <td>{trade.mistake}</td>
                    <td className={`mono ${trade.pl_r >= 0 ? 'positive' : 'negative'}`}>{trade.pl_r > 0 ? '+' : ''}{trade.pl_r.toFixed(2)}R</td>
                  </tr>
                ))}
                {!journal && <tr><td colSpan="7">Reading local SQLite mirror…</td></tr>}
              </tbody>
            </table>
          </div>
        </section>
      </main>

      <footer><span>JOURNAL LEARNING SYSTEM / PHASE 1</span><span>Local SQLite · Encrypted learned rules · Simulated chart data</span></footer>
    </div>
  );
}
