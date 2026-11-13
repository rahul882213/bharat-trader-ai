import React, { useEffect, useState } from 'react';
import { Play } from 'lucide-react';
import { formatINR, formatISTTime, formatPct } from '../utils/formatters';

interface Props {
  onSelectSymbol: (sym: string) => void;
}

const STRATEGY_OPTIONS = [
  { id: 'all', label: 'All Quantitative Setups' },
  { id: 'orb', label: 'Opening Range Breakout (ORB)' },
  { id: 'vwap-breakout', label: 'VWAP Breakout' },
  { id: 'ema-crossover', label: 'EMA Crossover (9/21/50)' },
  { id: 'rsi-oversold', label: 'RSI Oversold Reversal' },
  { id: 'macd-crossover', label: 'MACD Bullish Crossover' },
  { id: 'bb-squeeze', label: 'Bollinger Band Squeeze' },
  { id: 'volume-breakout', label: 'Volume Breakout' },
  { id: 'relative-strength', label: 'Relative Strength vs NIFTY' },
  { id: '52w-high', label: '52-Week High Breakout' },
  { id: 'sr-breakout', label: 'S/R Breakout' },
  { id: 'chart-patterns', label: 'Candlestick & Chart Patterns' },
  { id: 'gap', label: 'Gap-Up / Gap-Down' },
  { id: 'momentum', label: 'Momentum Stocks' },
  { id: 'unusual-volume', label: 'Unusual Volume Activity' },
];

export const ScannerSection: React.FC<Props> = ({ onSelectSymbol }) => {
  const [strategy, setStrategy] = useState('all');
  const [timeframe, setTimeframe] = useState('1d');
  const [universe, setUniverse] = useState('nifty50');
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runScan = async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/scanner?strategy=${encodeURIComponent(strategy)}&timeframe=${encodeURIComponent(timeframe)}&universe=${encodeURIComponent(universe)}&limit=30${refresh ? '&refresh=1' : ''}`
      );
      const json = await res.json();
      if (json.error) throw new Error(json.error);
      setData(json);
    } catch (e: any) {
      setError(e.message || 'Scan failed');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    runScan(false);
  }, []);

  const signals: any[] = data?.signals || [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-xl font-bold text-slate-100">AI Stock Scanner & Trading Opportunities</h1>
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400 mt-1">
            <span>NSE Equity Universe</span>
            <span aria-hidden="true">·</span>
            <span>Source: {data?.data_source || 'Yahoo Finance (Unofficial)'}</span>
            {data?.generated_at && (
              <>
                <span aria-hidden="true">·</span>
                <span className="font-mono">Scanned {formatISTTime(data.generated_at)}</span>
              </>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={() => runScan(true)}
          disabled={loading}
          className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold bg-amber-400 text-slate-950 rounded hover:bg-amber-300 disabled:opacity-50 whitespace-nowrap"
        >
          <Play className="w-3.5 h-3.5" />
          {loading ? 'Scanning NSE...' : 'Run Live Scan'}
        </button>
      </div>

      {/* Scanner Controls */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 bg-[#0f1626] border border-slate-800 rounded-lg p-4">
        <div>
          <label className="block text-xs text-slate-400 mb-1.5">Setup / Strategy</label>
          <select
            value={strategy}
            onChange={(e) => setStrategy(e.target.value)}
            className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-3 py-2 text-xs text-slate-100"
          >
            {STRATEGY_OPTIONS.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-1.5">Candle Timeframe</label>
          <div className="flex items-center gap-1 p-1 bg-[#0a0f1c] border border-slate-700 rounded">
            {['1m', '5m', '15m', '30m', '1h', '1d'].map((tf) => (
              <button
                key={tf}
                type="button"
                onClick={() => setTimeframe(tf)}
                className={`flex-1 py-1 text-xs font-mono rounded transition-colors ${
                  timeframe === tf ? 'bg-slate-700 text-slate-100 font-semibold' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-1.5">Indian Index / Universe</label>
          <select
            value={universe}
            onChange={(e) => setUniverse(e.target.value)}
            className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-3 py-2 text-xs text-slate-100"
          >
            <option value="nifty50">NIFTY 50</option>
            <option value="banknifty">BANK NIFTY</option>
            <option value="finnifty">FIN NIFTY</option>
            <option value="niftynext50">NIFTY NEXT 50</option>
            <option value="nifty100">NIFTY 100</option>
            <option value="midcap_smallcap">Midcap / Smallcap Active</option>
            <option value="all">Full NSE Master (Top 30 Sample)</option>
          </select>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-rose-950/40 border border-rose-800 rounded text-xs text-rose-200">{error}</div>
      )}

      {/* Ranked Opportunities Table */}
      <div className="bg-[#0f1626] border border-slate-800 rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between text-xs">
          <span className="font-display font-semibold text-sm text-slate-100">
            Ranked Trading Opportunities ({signals.length} matched / {data?.scanned_count ?? 0} scanned)
          </span>
          <span className="text-slate-400">Click row to run Technical & Entry/Exit Analysis</span>
        </div>

        {loading && !signals.length ? (
          <div className="p-8 text-center text-xs text-slate-400">Scanning live NSE market candles...</div>
        ) : signals.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-400">
            No stocks matched "{strategy}" on {timeframe}. Try broadening to All Setups or 1d timeframe.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400">
                  <th className="text-left px-4 py-2.5 font-medium">Symbol</th>
                  <th className="text-left px-4 py-2.5 font-medium">Sector</th>
                  <th className="text-right px-4 py-2.5 font-medium">Price (₹)</th>
                  <th className="text-right px-4 py-2.5 font-medium">Chg %</th>
                  <th className="text-right px-4 py-2.5 font-medium">Vol Ratio</th>
                  <th className="text-right px-4 py-2.5 font-medium">RSI(14)</th>
                  <th className="text-left px-4 py-2.5 font-medium">Setups & Quantitative Reason</th>
                  <th className="text-right px-4 py-2.5 font-medium">Action</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((row) => (
                  <tr
                    key={row.symbol}
                    onClick={() => onSelectSymbol(row.symbol)}
                    className="border-b border-slate-800/60 hover:bg-slate-800/40 cursor-pointer"
                  >
                    <td className="px-4 py-3 font-mono font-semibold text-slate-100">{row.symbol}</td>
                    <td className="px-4 py-3 text-slate-400">{row.sector}</td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums text-slate-100">
                      {formatINR(row.price)}
                    </td>
                    <td
                      className={`px-4 py-3 text-right font-mono tabular-nums ${
                        (row.change_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {formatPct(row.change_pct)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums text-slate-200">
                      {row.volume_ratio?.toFixed(2)}x
                    </td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums text-slate-300">
                      {row.rsi14 ?? '—'}
                    </td>
                    <td className="px-4 py-3 text-slate-300 max-w-md">
                      <div className="font-mono text-[11px] text-amber-300 mb-0.5">
                        {row.matched_strategies.join(' · ')}
                      </div>
                      <div className="text-slate-400 truncate">{row.reasons?.[0]}</div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectSymbol(row.symbol);
                        }}
                        className="px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-100 rounded whitespace-nowrap"
                      >
                        Analyse
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
