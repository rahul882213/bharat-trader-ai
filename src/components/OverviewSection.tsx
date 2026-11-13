import React, { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { formatINR, formatISTTime, formatPct, formatVolume } from '../utils/formatters';
import { apiFetch } from '../utils/apiBridge';

interface Props {
  onSelectSymbol: (sym: string) => void;
}

export const OverviewSection: React.FC<Props> = ({ onSelectSymbol }) => {
  const [overview, setOverview] = useState<any>(null);
  const [briefing, setBriefing] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const [ovRes, brRes] = await Promise.all([
        apiFetch(`/api/market/overview${refresh ? '?refresh=1' : ''}`),
        apiFetch('/api/report/daily'),
      ]);
      const ov = await ovRes.json();
      const br = await brRes.json();
      if (ov.error) throw new Error(ov.error);
      setOverview(ov);
      setBriefing(br);
    } catch (e: any) {
      setError(e.message || 'Failed to load market intelligence');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData(false);
  }, []);

  if (loading && !overview) {
    return (
      <div className="space-y-4">
        <div className="h-24 bg-[#0f1626] border border-slate-800 rounded-lg animate-pulse" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="h-44 bg-[#0f1626] border border-slate-800 rounded-lg animate-pulse" />
          <div className="h-44 bg-[#0f1626] border border-slate-800 rounded-lg animate-pulse" />
          <div className="h-44 bg-[#0f1626] border border-slate-800 rounded-lg animate-pulse" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 bg-[#0f1626] border border-rose-900/60 rounded-lg text-sm text-rose-300">
        <div className="font-semibold mb-1">Market Data Unavailable</div>
        <p className="text-slate-400 mb-3">{error}</p>
        <button
          type="button"
          onClick={() => loadData(true)}
          className="px-4 py-2 text-xs font-medium bg-slate-800 text-slate-100 rounded hover:bg-slate-700"
        >
          Retry Feed
        </button>
      </div>
    );
  }

  const cal = overview?.market_calendar || {};
  const indices: any[] = overview?.indices || [];
  const sectors: any[] = overview?.sector_rotation || [];
  const macros: any[] = overview?.global_macro || [];
  const gainers: any[] = overview?.top_gainers || [];
  const losers: any[] = overview?.top_losers || [];
  const heatmap: any[] = overview?.heatmap || [];
  const breadth = overview?.market_breadth || {};

  return (
    <div className="space-y-6">
      {/* Header Metadata & Refresh */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-xl font-bold text-slate-100">Indian Market Overview & Intelligence</h1>
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400 mt-1">
            <span>{cal.session_label || 'NSE / BSE Session'}</span>
            <span aria-hidden="true">·</span>
            <span>Next Trading Day: {cal.next_trading_day || '—'}</span>
            <span aria-hidden="true">·</span>
            <span>Source: {overview?.data_source || 'Yahoo Finance (Unofficial)'}</span>
            <span aria-hidden="true">·</span>
            <span className="font-mono">Updated {formatISTTime(overview?.generated_at_ist)}</span>
          </div>
        </div>
        <button
          type="button"
          onClick={() => loadData(true)}
          disabled={loading}
          className="inline-flex items-center gap-2 px-4 py-2 text-xs font-medium bg-[#131b2e] border border-slate-700 text-slate-200 rounded hover:bg-slate-800 whitespace-nowrap"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh Market Data
        </button>
      </div>

      {/* Live NIFTY, BANK NIFTY, FINNIFTY, SENSEX, INDIA VIX */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {indices.map((idx) => {
          const pos = (idx.change_pct ?? 0) >= 0;
          return (
            <div key={idx.id} className="bg-[#0f1626] border border-slate-800 rounded-lg p-4">
              <div className="text-xs text-slate-400 font-medium">{idx.name}</div>
              <div className="font-mono text-lg font-semibold text-slate-100 mt-1 tabular-nums">
                {idx.price !== null && idx.price !== undefined
                  ? idx.price.toLocaleString('en-IN', { maximumFractionDigits: 2 })
                  : 'Unavailable'}
              </div>
              <div className={`font-mono text-xs mt-1 tabular-nums ${pos ? 'text-emerald-400' : 'text-rose-400'}`}>
                {idx.change !== null && idx.change !== undefined ? `${idx.change > 0 ? '+' : ''}${idx.change.toFixed(2)}` : '—'}{' '}
                ({formatPct(idx.change_pct)})
              </div>
            </div>
          );
        })}
      </div>

      {/* Daily Indian Market Briefing + Breadth + Macro Cues */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-[#0f1626] border border-slate-800 rounded-lg p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-display text-sm font-semibold text-slate-100">
              {briefing?.headline || 'Daily Indian Market Briefing'}
            </h2>
            <span className="text-xs text-slate-400 font-mono">
              {overview?.nifty_trend} · {overview?.volatility_regime}
            </span>
          </div>
          <ul className="space-y-2 text-sm text-slate-300">
            {(briefing?.bullet_summary || []).map((line: string, i: number) => (
              <li key={i} className="leading-relaxed">
                {line}
              </li>
            ))}
          </ul>
          <p className="text-xs text-slate-500 mt-4 pt-3 border-t border-slate-800/80">
            {overview?.institutional_flow_note}
          </p>
        </div>

        <div className="bg-[#0f1626] border border-slate-800 rounded-lg p-5 space-y-4">
          <div>
            <h2 className="font-display text-sm font-semibold text-slate-100 mb-2">Market Breadth & Global Cues</h2>
            <div className="grid grid-cols-3 gap-2 font-mono text-xs">
              <div className="bg-[#0a0f1c] border border-slate-800 rounded p-2.5">
                <div className="text-slate-400">Advances</div>
                <div className="text-emerald-400 text-base font-semibold mt-0.5">{breadth.advances ?? '—'}</div>
              </div>
              <div className="bg-[#0a0f1c] border border-slate-800 rounded p-2.5">
                <div className="text-slate-400">Declines</div>
                <div className="text-rose-400 text-base font-semibold mt-0.5">{breadth.declines ?? '—'}</div>
              </div>
              <div className="bg-[#0a0f1c] border border-slate-800 rounded p-2.5">
                <div className="text-slate-400">A/D Ratio</div>
                <div className="text-slate-100 text-base font-semibold mt-0.5">{breadth.advance_decline_ratio ?? '—'}</div>
              </div>
            </div>
          </div>

          <div className="space-y-2 pt-2 border-t border-slate-800">
            {macros.map((m) => {
              const pos = (m.change_pct ?? 0) >= 0;
              return (
                <div key={m.id} className="flex items-center justify-between text-xs">
                  <span className="text-slate-300">{m.name}</span>
                  <span className="font-mono tabular-nums text-slate-100">
                    {m.unit === '₹' ? `₹${m.price?.toFixed(2) ?? '—'}` : `${m.unit === '$' ? '$' : ''}${m.price?.toFixed(2) ?? '—'}`}{' '}
                    <span className={pos ? 'text-emerald-400' : 'text-rose-400'}>({formatPct(m.change_pct)})</span>
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Sector Rotation & Market Heatmap */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-[#0f1626] border border-slate-800 rounded-lg p-5">
          <h2 className="font-display text-sm font-semibold text-slate-100 mb-3">Sector Rotation</h2>
          <div className="space-y-2.5">
            {sectors.map((sec) => {
              const pct = sec.change_pct ?? 0;
              const pos = pct >= 0;
              const width = Math.min(Math.abs(pct) * 22, 100);
              return (
                <div key={sec.id} className="text-xs">
                  <div className="flex justify-between mb-1">
                    <span className="text-slate-300">{sec.name}</span>
                    <span className={`font-mono tabular-nums ${pos ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {formatPct(pct)}
                    </span>
                  </div>
                  <div className="h-1.5 bg-slate-800 rounded overflow-hidden">
                    <div
                      className={`h-full ${pos ? 'bg-emerald-500' : 'bg-rose-500'}`}
                      style={{ width: `${Math.max(width, 6)}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="lg:col-span-2 bg-[#0f1626] border border-slate-800 rounded-lg p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-display text-sm font-semibold text-slate-100">NSE NIFTY 50 Heatmap</h2>
            <span className="text-xs text-slate-400">Click any stock to open Technicals</span>
          </div>
          <div className="grid grid-cols-3 sm:grid-cols-5 md:grid-cols-6 gap-2">
            {heatmap.map((item) => {
              const chg = item.change_pct ?? 0;
              const bg =
                chg >= 2
                  ? 'bg-emerald-900/70 border-emerald-700/70 text-emerald-100'
                  : chg > 0
                  ? 'bg-emerald-950/50 border-emerald-800/50 text-emerald-200'
                  : chg <= -2
                  ? 'bg-rose-900/70 border-rose-700/70 text-rose-100'
                  : chg < 0
                  ? 'bg-rose-950/50 border-rose-800/50 text-rose-200'
                  : 'bg-slate-900 border-slate-800 text-slate-200';
              return (
                <button
                  key={item.symbol}
                  type="button"
                  onClick={() => onSelectSymbol(item.symbol)}
                  className={`p-2.5 rounded border text-left transition-transform hover:scale-[1.02] ${bg}`}
                >
                  <div className="font-mono text-xs font-semibold truncate">{item.symbol}</div>
                  <div className="font-mono text-[11px] tabular-nums opacity-90 mt-0.5">{formatPct(chg)}</div>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Top Gainers & Top Losers */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {[
          { title: 'Top Gainers (NSE)', rows: gainers, positive: true },
          { title: 'Top Losers (NSE)', rows: losers, positive: false },
        ].map((grp) => (
          <div key={grp.title} className="bg-[#0f1626] border border-slate-800 rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
              <h2 className="font-display text-sm font-semibold text-slate-100">{grp.title}</h2>
              <span className="text-xs text-slate-500">INR (₹)</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400">
                    <th className="text-left px-4 py-2.5 font-medium">Symbol</th>
                    <th className="text-left px-4 py-2.5 font-medium">Sector</th>
                    <th className="text-right px-4 py-2.5 font-medium">LTP</th>
                    <th className="text-right px-4 py-2.5 font-medium">Change</th>
                    <th className="text-right px-4 py-2.5 font-medium">Volume</th>
                  </tr>
                </thead>
                <tbody>
                  {grp.rows.map((r) => (
                    <tr
                      key={r.symbol}
                      onClick={() => onSelectSymbol(r.symbol)}
                      className="border-b border-slate-800/60 hover:bg-slate-800/40 cursor-pointer"
                    >
                      <td className="px-4 py-2.5 font-mono font-semibold text-slate-100">{r.symbol}</td>
                      <td className="px-4 py-2.5 text-slate-400">{r.sector}</td>
                      <td className="px-4 py-2.5 text-right font-mono tabular-nums text-slate-100">
                        {formatINR(r.price)}
                      </td>
                      <td
                        className={`px-4 py-2.5 text-right font-mono tabular-nums ${
                          (r.change_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                        }`}
                      >
                        {formatPct(r.change_pct)}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono tabular-nums text-slate-400">
                        {formatVolume(r.volume)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
