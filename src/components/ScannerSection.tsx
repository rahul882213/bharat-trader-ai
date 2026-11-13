import React, { useEffect, useState } from 'react';
import { Globe, Play, Radar } from 'lucide-react';
import { formatCrores, formatINR, formatISTTime, formatPct } from '../utils/formatters';

interface Props {
  onSelectSymbol: (sym: string) => void;
  initialMode?: 'technical' | 'market_wide';
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

export const ScannerSection: React.FC<Props> = ({ onSelectSymbol, initialMode = 'technical' }) => {
  const [scanMode, setScanMode] = useState<'technical' | 'market_wide'>(initialMode);

  // Mode 1 Technical Controls
  const [strategy, setStrategy] = useState('all');
  const [timeframe, setTimeframe] = useState('1d');
  const [universe, setUniverse] = useState('nifty50');

  // Mode 2 Market-Wide Filters
  const [capTier, setCapTier] = useState('ALL');
  const [sector, setSector] = useState('ALL');
  const [industry, setIndustry] = useState('ALL');
  const [mwUniverse, setMwUniverse] = useState('all');
  const [minMcap, setMinMcap] = useState('');
  const [maxMcap, setMaxMcap] = useState('');
  const [minPrice, setMinPrice] = useState('');
  const [maxPrice, setMaxPrice] = useState('');
  const [minVolume, setMinVolume] = useState('');
  const [masterStats, setMasterStats] = useState<{ total_stocks?: number; sectors?: string[]; industries?: string[] }>({});

  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setScanMode(initialMode);
  }, [initialMode]);

  useEffect(() => {
    fetch('/api/stocks/master/stats')
      .then((r) => r.json())
      .then((j) => setMasterStats(j || {}))
      .catch(() => {});
  }, []);

  const runScan = async (refresh = false, modeOverride?: 'technical' | 'market_wide') => {
    const activeMode = modeOverride || scanMode;
    setLoading(true);
    setError(null);
    try {
      let url = '';
      if (activeMode === 'technical') {
        url = `/api/scanner?strategy=${encodeURIComponent(strategy)}&timeframe=${encodeURIComponent(timeframe)}&universe=${encodeURIComponent(universe)}&limit=30${refresh ? '&refresh=1' : ''}`;
      } else {
        const params = new URLSearchParams({
          cap_tier: capTier,
          sector,
          industry,
          strategy,
          timeframe,
          universe: mwUniverse,
          limit: '45',
        });
        if (minMcap) params.set('min_mcap', minMcap);
        if (maxMcap) params.set('max_mcap', maxMcap);
        if (minPrice) params.set('min_price', minPrice);
        if (maxPrice) params.set('max_price', maxPrice);
        if (minVolume) params.set('min_volume', minVolume);
        if (refresh) params.set('refresh', '1');
        url = `/api/scanner/market-wide?${params.toString()}`;
      }
      const res = await fetch(url);
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
    runScan(false, scanMode);
  }, [scanMode]);

  const rows: any[] = scanMode === 'market_wide' ? data?.results || [] : data?.signals || [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-xl font-bold text-slate-100">
            {scanMode === 'market_wide'
              ? 'Market-Wide Multi-Factor Scanner & AI Stock Rankings'
              : 'AI Technical Setup Scanner (NSE / BSE)'}
          </h1>
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400 mt-1">
            <span>Stock Master Universe: {masterStats.total_stocks ?? '2,600+'} listed stocks</span>
            <span aria-hidden="true">·</span>
            <span>Source: {data?.data_source || 'Central Stock Master + Screener DB + Yahoo Finance (Unofficial)'}</span>
            {data?.generated_at && (
              <>
                <span aria-hidden="true">·</span>
                <span className="font-mono">Scanned {formatISTTime(data.generated_at)}</span>
              </>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center p-0.5 bg-[#0f1626] border border-slate-800 rounded">
            <button
              type="button"
              onClick={() => setScanMode('technical')}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded ${
                scanMode === 'technical' ? 'bg-slate-800 text-slate-100' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Radar className="w-3.5 h-3.5" />
              Technical Setups
            </button>
            <button
              type="button"
              onClick={() => setScanMode('market_wide')}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded ${
                scanMode === 'market_wide' ? 'bg-slate-800 text-amber-300' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Globe className="w-3.5 h-3.5" />
              Market-Wide Scan
            </button>
          </div>

          <button
            type="button"
            onClick={() => runScan(true)}
            disabled={loading}
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold bg-amber-400 text-slate-950 rounded hover:bg-amber-300 disabled:opacity-50 whitespace-nowrap"
          >
            <Play className="w-3.5 h-3.5" />
            {loading ? 'Scanning Market...' : scanMode === 'market_wide' ? 'Scan Entire Market' : 'Run Live Scan'}
          </button>
        </div>
      </div>

      {/* Controls */}
      {scanMode === 'technical' ? (
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
              <option value="all">Full NSE Master (Priority Sample)</option>
            </select>
          </div>
        </div>
      ) : (
        <div className="bg-[#0f1626] border border-slate-800 rounded-lg p-4 space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-xs">
            <div>
              <label className="block text-slate-400 mb-1">Cap Tier</label>
              <select
                value={capTier}
                onChange={(e) => setCapTier(e.target.value)}
                className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-1.5 text-slate-100"
              >
                <option value="ALL">All Caps</option>
                <option value="Large Cap">Large-Cap (≥ ₹20,000 Cr)</option>
                <option value="Mid Cap">Mid-Cap (₹5,000–20,000 Cr)</option>
                <option value="Small Cap">Small-Cap (₹500–5,000 Cr)</option>
                <option value="Micro Cap">Micro-Cap (&lt; ₹500 Cr)</option>
              </select>
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Sector</label>
              <select
                value={sector}
                onChange={(e) => setSector(e.target.value)}
                className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-1.5 text-slate-100"
              >
                <option value="ALL">All Sectors</option>
                {(masterStats.sectors || []).map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Industry</label>
              <select
                value={industry}
                onChange={(e) => setIndustry(e.target.value)}
                className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-1.5 text-slate-100"
              >
                <option value="ALL">All Industries</option>
                {(masterStats.industries || []).map((ind) => (
                  <option key={ind} value={ind}>
                    {ind}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Scan Scope</label>
              <select
                value={mwUniverse}
                onChange={(e) => setMwUniverse(e.target.value)}
                className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-1.5 text-slate-100"
              >
                <option value="all">Full Supported Universe</option>
                <option value="screener_imported">Screener.in Imported Only</option>
              </select>
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Technical Filter</label>
              <select
                value={strategy}
                onChange={(e) => setStrategy(e.target.value)}
                className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-1.5 text-slate-100"
              >
                {STRATEGY_OPTIONS.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-xs">
            <div>
              <label className="block text-slate-400 mb-1">Min Market Cap (Cr)</label>
              <input
                type="number"
                value={minMcap}
                onChange={(e) => setMinMcap(e.target.value)}
                placeholder="e.g. 500"
                className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-1.5 font-mono text-slate-100"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Max Market Cap (Cr)</label>
              <input
                type="number"
                value={maxMcap}
                onChange={(e) => setMaxMcap(e.target.value)}
                placeholder="e.g. 50000"
                className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-1.5 font-mono text-slate-100"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Min Price (₹)</label>
              <input
                type="number"
                value={minPrice}
                onChange={(e) => setMinPrice(e.target.value)}
                placeholder="e.g. 50"
                className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-1.5 font-mono text-slate-100"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Max Price (₹)</label>
              <input
                type="number"
                value={maxPrice}
                onChange={(e) => setMaxPrice(e.target.value)}
                placeholder="e.g. 10000"
                className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-1.5 font-mono text-slate-100"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Min Volume</label>
              <input
                type="number"
                value={minVolume}
                onChange={(e) => setMinVolume(e.target.value)}
                placeholder="e.g. 50000"
                className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-1.5 font-mono text-slate-100"
              />
            </div>
          </div>
        </div>
      )}

      {data?.completeness_note && (
        <div className="px-4 py-2.5 bg-[#0f1626] border border-slate-800 rounded text-xs text-slate-300">
          {data.completeness_note}
        </div>
      )}

      {error && (
        <div className="p-4 bg-rose-950/40 border border-rose-800 rounded text-xs text-rose-200">{error}</div>
      )}

      {/* Ranked Opportunities Table */}
      <div className="bg-[#0f1626] border border-slate-800 rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-800 flex flex-wrap items-center justify-between gap-2 text-xs">
          <span className="font-display font-semibold text-sm text-slate-100">
            AI Stock Rankings ({rows.length} ranked · {data?.scanned_available_count ?? data?.scanned_count ?? 0} verified ·{' '}
            {data?.unavailable_count ?? 0} unavailable)
          </span>
          <span className="text-slate-400">Click any stock to load full Technical + Fundamental analysis</span>
        </div>

        {loading && !rows.length ? (
          <div className="p-8 text-center text-xs text-slate-400">Scanning live Indian equities...</div>
        ) : rows.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-400">
            No stocks matched the current filter criteria. Broaden filters or import Screener CSV data for deeper fundamental coverage.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400">
                  <th className="text-left px-4 py-2.5 font-medium">Stock</th>
                  <th className="text-left px-4 py-2.5 font-medium">Sector / Cap</th>
                  <th className="text-right px-4 py-2.5 font-medium">Price (₹)</th>
                  <th className="text-right px-4 py-2.5 font-medium">Chg %</th>
                  <th className="text-right px-4 py-2.5 font-medium">Vol Ratio</th>
                  <th className="text-right px-4 py-2.5 font-medium">AI Rank</th>
                  <th className="text-right px-4 py-2.5 font-medium">Fund / Val</th>
                  <th className="text-left px-4 py-2.5 font-medium">Setups, Catalysts & Reason</th>
                  <th className="text-right px-4 py-2.5 font-medium">Action</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.symbol}
                    onClick={() => onSelectSymbol(row.symbol)}
                    className="border-b border-slate-800/60 hover:bg-slate-800/40 cursor-pointer"
                  >
                    <td className="px-4 py-3">
                      <div className="font-mono font-semibold text-slate-100">{row.symbol}</div>
                      <div className="text-[11px] text-slate-400 truncate max-w-[170px]">{row.company_name}</div>
                    </td>
                    <td className="px-4 py-3 text-slate-300">
                      <div>{row.sector}</div>
                      <div className="text-[11px] text-slate-500">
                        {row.cap_tier || (row.market_cap_cr ? formatCrores(row.market_cap_cr) : 'Unclassified')}
                      </div>
                    </td>
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
                    <td className="px-4 py-3 text-right font-mono tabular-nums font-semibold text-amber-300">
                      {row.score}
                    </td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums text-slate-300">
                      {row.fundamental_score ?? '—'} / {row.valuation_score ?? '—'}
                    </td>
                    <td className="px-4 py-3 text-slate-300 max-w-md">
                      {row.matched_strategies?.length > 0 && (
                        <div className="font-mono text-[11px] text-amber-300 mb-0.5">
                          {row.matched_strategies.join(' · ')}
                        </div>
                      )}
                      {row.catalysts?.length > 0 && (
                        <div className="font-mono text-[11px] text-emerald-300 mb-0.5">{row.catalysts.join(' · ')}</div>
                      )}
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
