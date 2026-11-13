import React, { useEffect, useState } from 'react';
import { Database, RefreshCw } from 'lucide-react';
import { formatCrores, formatINR, formatISTTime } from '../utils/formatters';
import { apiFetch } from '../utils/apiBridge';

interface Props {
  symbol: string;
  exchange: 'NSE' | 'BSE';
  onOpenScreener?: () => void;
}

export const FundamentalSection: React.FC<Props> = ({ symbol, exchange, onOpenScreener }) => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadFundamentals = async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch(
        `/api/fundamentals/${encodeURIComponent(symbol)}?exchange=${exchange}${refresh ? '&refresh=1' : ''}`
      );
      const json = await res.json();
      if (!json.available) throw new Error(json.error || `Fundamental filings unavailable for ${symbol}`);
      setData(json);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadFundamentals(false);
  }, [symbol, exchange]);

  if (loading && !data) {
    return (
      <div className="space-y-4">
        <div className="h-28 bg-[#0f1626] border border-slate-800 rounded-lg animate-pulse" />
        <div className="h-64 bg-[#0f1626] border border-slate-800 rounded-lg animate-pulse" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 bg-[#0f1626] border border-slate-800 rounded-lg text-sm">
        <div className="font-semibold text-amber-300 mb-1">Fundamental Data Notice ({symbol})</div>
        <p className="text-slate-400 text-xs mb-3">{error}</p>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => loadFundamentals(true)}
            className="px-4 py-2 text-xs font-medium bg-slate-800 text-slate-100 rounded hover:bg-slate-700"
          >
            Retry Fetch
          </button>
          {onOpenScreener && (
            <button
              type="button"
              onClick={onOpenScreener}
              className="px-4 py-2 text-xs font-semibold bg-amber-400 text-slate-950 rounded hover:bg-amber-300"
            >
              Import Screener.in Excel / CSV
            </button>
          )}
        </div>
      </div>
    );
  }

  const meta = data?.stock_meta || {};
  const prov = data?.provenance || {};
  const scores = data?.scores || {};
  const fm = data?.reported_financial_metrics || {};
  const val = data?.valuation || {};
  const est = data?.analyst_estimates_and_models || {};
  const dcf = est?.dcf_intrinsic_valuation;
  const biz = data?.business_analysis || {};
  const annual: any[] = data?.annual_results_cr || [];
  const quarterly: any[] = data?.quarterly_results_cr || [];
  const peers: any[] = data?.peer_comparison || [];
  const missing: string[] = data?.missing_fields || [];

  const fmtPct = (v: number | null | undefined) => (v !== null && v !== undefined ? `${v.toFixed(2)}%` : 'Unavailable');
  const fmtNum = (v: number | null | undefined, suffix = '') =>
    v !== null && v !== undefined ? `${v.toFixed(2)}${suffix}` : 'Unavailable';

  const scoreCards = [
    { key: 'business_quality', label: 'Business Quality' },
    { key: 'financial_strength', label: 'Financial Strength' },
    { key: 'growth', label: 'Growth Momentum' },
    { key: 'valuation', label: 'Valuation Comfort' },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-xl font-bold text-slate-100">
            {data?.company_name || symbol} ({data?.symbol || symbol} · {meta.exchange || exchange}) — Fundamental Analyst
          </h1>
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400 mt-1">
            {meta.isin && <span className="font-mono">ISIN: {meta.isin}</span>}
            {meta.bse_code && (
              <>
                <span aria-hidden="true">·</span>
                <span className="font-mono">BSE: {meta.bse_code}</span>
              </>
            )}
            <span aria-hidden="true">·</span>
            <span>{data?.sector}</span>
            <span aria-hidden="true">·</span>
            <span>{data?.industry}</span>
            {meta.cap_tier && (
              <>
                <span aria-hidden="true">·</span>
                <span>{meta.cap_tier}</span>
              </>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-400 mt-1">
            <span>Source: {prov.data_source || data?.source}</span>
            <span aria-hidden="true">·</span>
            <span>Period: {prov.reporting_period || 'Latest'}</span>
            <span aria-hidden="true">·</span>
            <span>Scope: {prov.statement_scope || 'Unspecified'}</span>
            <span aria-hidden="true">·</span>
            <span>{prov.actual_vs_estimated || 'Actual Reported Data'}</span>
            <span aria-hidden="true">·</span>
            <span className="font-mono">Updated {formatISTTime(prov.last_updated || data?.fetched_at_ist)}</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {onOpenScreener && (
            <button
              type="button"
              onClick={onOpenScreener}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-medium bg-[#131b2e] border border-slate-700 text-amber-300 rounded hover:bg-slate-800"
            >
              <Database className="w-3.5 h-3.5" />
              Screener.in Data Center
            </button>
          )}
          <button
            type="button"
            onClick={() => loadFundamentals(true)}
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-medium bg-[#131b2e] border border-slate-700 text-slate-200 rounded hover:bg-slate-800"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh Filings
          </button>
        </div>
      </div>

      {/* Evidenced 4-Pillar AI Fundamental Scores */}
      {scores.business_quality && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {scoreCards.map((sc) => {
            const obj = scores[sc.key] || { score: 0, evidence: [] };
            const tone =
              obj.score >= 70 ? 'text-emerald-400' : obj.score >= 50 ? 'text-amber-300' : 'text-rose-400';
            return (
              <div key={sc.key} className="bg-[#0f1626] border border-slate-800 rounded-lg p-4 space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">{sc.label}</span>
                  <span className={`font-mono text-base font-bold tabular-nums ${tone}`}>{obj.score}/100</span>
                </div>
                <div className="text-[11px] font-mono text-slate-300 leading-relaxed">
                  {(obj.evidence || []).join(' · ')}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Final AI Assessment + Governance + Bull/Bear/Risks */}
      {data?.final_assessment && (
        <div className="bg-[#0f1626] border border-slate-800 rounded-lg p-5 space-y-4 text-xs">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-display text-sm font-semibold text-slate-100">
              AI Fundamental Research Assessment ({(data?.classifications || []).join(' · ')})
            </h2>
            <span className="font-mono text-amber-300 font-semibold">
              Composite: {scores.composite_score ?? '—'}/100
            </span>
          </div>
          <p className="text-slate-200 leading-relaxed">{data.final_assessment}</p>
          <div className="text-slate-300 pt-2 border-t border-slate-800">
            <span className="font-semibold text-slate-100">Management & Governance: </span>
            {data.management_and_governance}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2 border-t border-slate-800">
            <div>
              <div className="font-semibold text-emerald-400 mb-1.5">Bullish Factors</div>
              <ul className="space-y-1 text-slate-300 list-disc list-inside">
                {(data.bullish_factors || []).map((b: string, i: number) => (
                  <li key={i}>{b}</li>
                ))}
              </ul>
            </div>
            <div>
              <div className="font-semibold text-amber-300 mb-1.5">Bearish Factors</div>
              <ul className="space-y-1 text-slate-300 list-disc list-inside">
                {(data.bearish_factors || []).map((b: string, i: number) => (
                  <li key={i}>{b}</li>
                ))}
              </ul>
            </div>
            <div>
              <div className="font-semibold text-rose-400 mb-1.5">Major Risks & Disclosures</div>
              <ul className="space-y-1 text-slate-300 list-disc list-inside">
                {(data.major_risks || []).map((r: string, i: number) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          </div>

          {missing.length > 0 && (
            <div className="p-3 bg-[#0a0f1c] border border-amber-900/50 rounded text-[11px] text-amber-200/90 flex flex-wrap items-center justify-between gap-2">
              <span>Missing financial data (not fabricated): {missing.join(', ')}</span>
              {onOpenScreener && (
                <button
                  type="button"
                  onClick={onOpenScreener}
                  className="text-amber-300 underline hover:text-amber-200"
                >
                  Upload Screener.in .xlsx/.csv
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* Classification & Market Cap Strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-[#0f1626] border border-slate-800 rounded-lg p-4">
          <div className="text-xs text-slate-400">Current Price</div>
          <div className="font-mono text-lg font-semibold text-slate-100 mt-1">{formatINR(data?.current_price_inr)}</div>
        </div>
        <div className="bg-[#0f1626] border border-slate-800 rounded-lg p-4">
          <div className="text-xs text-slate-400">Market Cap</div>
          <div className="font-mono text-lg font-semibold text-slate-100 mt-1">{formatCrores(data?.market_cap_cr)}</div>
        </div>
        <div className="bg-[#0f1626] border border-slate-800 rounded-lg p-4">
          <div className="text-xs text-slate-400">Order Book & Execution</div>
          <div className="text-xs font-medium text-slate-200 mt-1.5 leading-relaxed">
            {biz.order_book_and_execution_note}
          </div>
        </div>
        <div className="bg-[#0f1626] border border-slate-800 rounded-lg p-4">
          <div className="text-xs text-slate-400">DCF Model Estimate (Disclosed)</div>
          <div className="font-mono text-lg font-semibold text-sky-300 mt-1">
            {dcf ? formatINR(dcf.intrinsic_value_per_share_inr) : 'Unavailable'}
          </div>
          {dcf && (
            <div className="text-[11px] font-mono text-slate-400 mt-0.5">
              Implied {dcf.upside_downside_pct > 0 ? '+' : ''}
              {dcf.upside_downside_pct}% vs CMP
            </div>
          )}
        </div>
      </div>

      {/* Reported Financial Metrics vs Valuation & Analyst Estimates */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-[#0f1626] border border-slate-800 rounded-lg p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-display text-sm font-semibold text-slate-100">Reported Financial Metrics</h2>
            <span className="text-[11px] text-emerald-400 font-mono">Reported Historical Data</span>
          </div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-2.5 text-xs font-mono">
            {[
              ['5Y Sales CAGR', fmtPct(fm.sales_growth_5y_pct)],
              ['5Y Profit CAGR', fmtPct(fm.profit_growth_5y_pct)],
              ['Revenue Growth (YoY)', fmtPct(fm.revenue_growth_yoy_pct)],
              ['PAT Growth (YoY)', fmtPct(fm.pat_growth_yoy_pct)],
              ['Operating Margin', fmtPct(fm.operating_margin_pct)],
              ['EBITDA Margin', fmtPct(fm.ebitda_margin_pct)],
              ['ROE', fmtPct(fm.roe_pct)],
              ['ROCE', fmtPct(fm.roce_pct)],
              ['Debt-to-Equity', fmtNum(fm.debt_to_equity, 'x')],
              ['Free Cash Flow', fm.free_cash_flow_cr !== null ? formatCrores(fm.free_cash_flow_cr) : 'Unavailable'],
              ['Operating Cash Flow', fm.operating_cash_flow_cr !== null ? formatCrores(fm.operating_cash_flow_cr) : 'Unavailable'],
              ['Working Capital', fm.working_capital_cr !== null ? formatCrores(fm.working_capital_cr) : 'Unavailable'],
              ['Promoter / Insider Holding', fmtPct(fm.promoter_insider_holding_pct)],
              ['Institutional Holding', fmtPct(fm.institutional_holding_pct)],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between border-b border-slate-800/70 pb-1.5">
                <span className="text-slate-400 font-sans">{k}</span>
                <span className="text-slate-100 tabular-nums">{v}</span>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-slate-400 mt-3">
            Pledged Shares:{' '}
            <span className="text-amber-300">
              {fm.pledged_shares_pct !== null && fm.pledged_shares_pct !== undefined
                ? `${fm.pledged_shares_pct}%`
                : 'Not reported in feed'}
            </span>{' '}
            — {fm.pledged_shares_note}
          </p>
        </div>

        <div className="bg-[#0f1626] border border-slate-800 rounded-lg p-5 space-y-4">
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-display text-sm font-semibold text-slate-100">Valuation Multiples & Model Estimates</h2>
              <span className="text-[11px] text-sky-400 font-mono">Estimates Clearly Separated</span>
            </div>
            <div className="grid grid-cols-2 gap-x-6 gap-y-2.5 text-xs font-mono">
              {[
                ['Trailing P/E (Reported)', fmtNum(val.pe_trailing, 'x')],
                ['Forward P/E (Analyst Est.)', fmtNum(val.forward_pe, 'x')],
                ['Price / Book (P/B)', fmtNum(val.pb_ratio, 'x')],
                ['EV / EBITDA', fmtNum(val.ev_ebitda, 'x')],
                ['PEG Ratio', fmtNum(val.peg_ratio)],
                ['Price / Sales', fmtNum(val.price_to_sales, 'x')],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between border-b border-slate-800/70 pb-1.5">
                  <span className="text-slate-400 font-sans">{k}</span>
                  <span className="text-slate-100 tabular-nums">{v}</span>
                </div>
              ))}
            </div>
          </div>

          {dcf && (
            <div className="bg-[#0a0f1c] border border-slate-800 rounded p-3.5 text-xs space-y-1.5">
              <div className="font-semibold text-sky-300">{dcf.classification_tag}</div>
              <div className="text-slate-400 font-mono">
                Assumptions: WACC {dcf.assumptions.discount_rate_wacc_pct}% · 5Y FCF Growth{' '}
                {dcf.assumptions['5y_fcf_growth_pct']}% · Terminal Growth {dcf.assumptions.terminal_growth_pct}% · Base
                FCF {formatCrores(dcf.assumptions.base_fcf_cr)}
              </div>
            </div>
          )}

          <div className="text-xs text-slate-300 space-y-1.5 pt-1">
            <div className="font-semibold text-slate-200">Business & Capital Allocation</div>
            <p className="text-slate-400 leading-relaxed line-clamp-4">{biz.business_model}</p>
            <p className="text-slate-300 font-mono text-[11px]">{biz.capital_allocation}</p>
          </div>
        </div>
      </div>

      {/* Annual & Quarterly Results in INR Crores */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {[
          { title: 'Annual Reported Results (₹ Crores)', rows: annual },
          { title: 'Quarterly Reported Results (₹ Crores)', rows: quarterly },
        ].map((tbl) => (
          <div key={tbl.title} className="bg-[#0f1626] border border-slate-800 rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-800 font-display text-sm font-semibold text-slate-100">
              {tbl.title}
            </div>
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400 font-sans">
                  <th className="text-left px-4 py-2 font-medium">Period End</th>
                  <th className="text-right px-4 py-2 font-medium">Revenue (Cr)</th>
                  <th className="text-right px-4 py-2 font-medium">EBIT / Op. Profit</th>
                  <th className="text-right px-4 py-2 font-medium">PAT (Cr)</th>
                </tr>
              </thead>
              <tbody>
                {tbl.rows.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-4 text-center text-slate-500 font-sans">
                      Period breakdown not available yet. Upload Screener.in .xlsx export for 5–10Y history.
                    </td>
                  </tr>
                ) : (
                  tbl.rows.map((r, i) => (
                    <tr key={i} className="border-b border-slate-800/60">
                      <td className="px-4 py-2.5 text-slate-200">{r.period}</td>
                      <td className="px-4 py-2.5 text-right text-slate-100">{formatCrores(r.revenue_cr)}</td>
                      <td className="px-4 py-2.5 text-right text-slate-200">{formatCrores(r.ebit_cr)}</td>
                      <td className="px-4 py-2.5 text-right text-emerald-300">{formatCrores(r.pat_cr)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        ))}
      </div>

      {/* Peer Comparison */}
      <div className="bg-[#0f1626] border border-slate-800 rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-800 font-display text-sm font-semibold text-slate-100">
          Sector Peer Comparison ({data?.sector})
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 font-sans">
                <th className="text-left px-4 py-2.5 font-medium">Symbol</th>
                <th className="text-right px-4 py-2.5 font-medium">CMP (₹)</th>
                <th className="text-right px-4 py-2.5 font-medium">Mkt Cap</th>
                <th className="text-right px-4 py-2.5 font-medium">P/E</th>
                <th className="text-right px-4 py-2.5 font-medium">P/B</th>
                <th className="text-right px-4 py-2.5 font-medium">ROE %</th>
                <th className="text-right px-4 py-2.5 font-medium">OPM %</th>
                <th className="text-right px-4 py-2.5 font-medium">D/E</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-slate-800 bg-slate-800/30">
                <td className="px-4 py-2.5 font-semibold text-amber-300">{data?.symbol || symbol} (Target)</td>
                <td className="px-4 py-2.5 text-right">{formatINR(data?.current_price_inr)}</td>
                <td className="px-4 py-2.5 text-right">{formatCrores(data?.market_cap_cr)}</td>
                <td className="px-4 py-2.5 text-right">{fmtNum(val.pe_trailing)}</td>
                <td className="px-4 py-2.5 text-right">{fmtNum(val.pb_ratio)}</td>
                <td className="px-4 py-2.5 text-right">{fmtPct(fm.roe_pct)}</td>
                <td className="px-4 py-2.5 text-right">{fmtPct(fm.operating_margin_pct)}</td>
                <td className="px-4 py-2.5 text-right">{fmtNum(fm.debt_to_equity)}</td>
              </tr>
              {peers.map((p) => (
                <tr key={p.symbol} className="border-b border-slate-800/60">
                  <td className="px-4 py-2.5 text-slate-100">{p.symbol}</td>
                  <td className="px-4 py-2.5 text-right">{formatINR(p.price_inr)}</td>
                  <td className="px-4 py-2.5 text-right">{formatCrores(p.market_cap_cr)}</td>
                  <td className="px-4 py-2.5 text-right">{fmtNum(p.pe)}</td>
                  <td className="px-4 py-2.5 text-right">{fmtNum(p.pb)}</td>
                  <td className="px-4 py-2.5 text-right">{fmtPct(p.roe_pct)}</td>
                  <td className="px-4 py-2.5 text-right">{fmtPct(p.op_margin_pct)}</td>
                  <td className="px-4 py-2.5 text-right">{fmtNum(p.debt_to_equity)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
