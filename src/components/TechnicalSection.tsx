import React, { useEffect, useState } from 'react';
import { CheckCircle2, Sparkles } from 'lucide-react';
import { CandlestickTerminalChart } from './CandlestickTerminalChart';
import { ApprovalModal } from './ApprovalModal';
import { formatINR, formatISTTime, formatVolume } from '../utils/formatters';
import { apiFetch } from '../utils/apiBridge';

interface Props {
  symbol: string;
  exchange: 'NSE' | 'BSE';
  onChangeExchange: (ex: 'NSE' | 'BSE') => void;
}

export const TechnicalSection: React.FC<Props> = ({ symbol, exchange, onChangeExchange }) => {
  const [timeframe, setTimeframe] = useState('1d');
  const [chartData, setChartData] = useState<any>(null);
  const [entryData, setEntryData] = useState<any>(null);
  const [exitData, setExitData] = useState<any>(null);
  const [sizingData, setSizingData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Order Execution State
  const [product, setProduct] = useState<'MIS' | 'CNC'>('MIS');
  const [orderSide, setOrderSide] = useState<'BUY' | 'SELL'>('BUY');
  const [execBroker, setExecBroker] = useState<'paper' | 'zerodha' | 'upstox' | 'dhan'>('paper');
  const [modalOpen, setModalOpen] = useState(false);
  const [previewData, setPreviewData] = useState<any>(null);
  const [orderResult, setOrderResult] = useState<any>(null);
  const [submitting, setSubmitting] = useState(false);

  // Gemini AI Synthesis State
  const [aiReport, setAiReport] = useState<any>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  const loadTechnicals = async () => {
    setLoading(true);
    setError(null);
    setAiReport(null);
    setOrderResult(null);
    try {
      const [cRes, enRes, exRes] = await Promise.all([
        apiFetch(`/api/chart/${encodeURIComponent(symbol)}?timeframe=${timeframe}&exchange=${exchange}`),
        apiFetch(`/api/entry/${encodeURIComponent(symbol)}?timeframe=${timeframe}&exchange=${exchange}`),
        apiFetch(`/api/exit/${encodeURIComponent(symbol)}?timeframe=${timeframe}&product=${product}&exchange=${exchange}`),
      ]);
      const [cJson, enJson, exJson] = await Promise.all([cRes.json(), enRes.json(), exRes.json()]);
      if (!cJson.available) throw new Error(cJson.error || `Market data unavailable for ${symbol}`);
      setChartData(cJson);
      setEntryData(enJson);
      setExitData(exJson);

      if (exJson?.available && exJson.entry_price && exJson.initial_stop_loss) {
        const riskRes = await apiFetch('/api/risk');
        const riskJson = await riskRes.json();
        const cap = riskJson?.total_capital_inr || 1000000;
        const rPct = riskJson?.config?.max_risk_per_trade_pct || 1.0;
        const szRes = await apiFetch('/api/budget/calculate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            capital_inr: cap,
            risk_pct: rPct,
            entry_price: exJson.entry_price,
            stop_loss: exJson.initial_stop_loss,
            trade_type: product === 'CNC' ? 'equity_delivery' : 'equity_intraday',
          }),
        });
        setSizingData(await szRes.json());
      }
    } catch (e: any) {
      setError(e.message || 'Failed to load technical analysis');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTechnicals();
  }, [symbol, timeframe, exchange, product]);

  const openApproval = async () => {
    if (!exitData?.available) return;
    const qty = Math.max(1, sizingData?.quantity || 1);
    const draft = {
      symbol,
      exchange,
      side: orderSide,
      quantity: qty,
      price: exitData.entry_price,
      stop_loss: exitData.initial_stop_loss,
      target: exitData.target_2,
      product,
      order_type: 'LIMIT',
      broker: execBroker,
    };
    const prevRes = await apiFetch('/api/orders/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(draft),
    });
    setPreviewData(await prevRes.json());
    setModalOpen(true);
  };

  const confirmOrder = async (approved: boolean) => {
    if (!exitData?.available) return;
    setSubmitting(true);
    try {
      const qty = Math.max(1, sizingData?.quantity || 1);
      const mode = execBroker === 'paper' ? 'paper' : 'live';
      const res = await apiFetch('/api/orders/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode,
          broker: execBroker,
          explicit_user_approval: approved,
          order: {
            symbol,
            exchange,
            side: orderSide,
            quantity: qty,
            price: exitData.entry_price,
            stop_loss: exitData.initial_stop_loss,
            target: exitData.target_2,
            product,
            order_type: 'LIMIT',
            strategy: 'Technical Setup',
          },
        }),
      });
      const json = await res.json();
      setOrderResult(json);
      setModalOpen(false);
    } finally {
      setSubmitting(false);
    }
  };

  const runGeminiResearch = async () => {
    setAiLoading(true);
    setAiError(null);
    try {
      const res = await apiFetch('/api/ai/research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol,
          context: {
            price: chartData?.indicators?.latest,
            entry: entryData,
            exit: exitData,
            support_resistance: chartData?.indicators?.support_resistance,
            patterns: chartData?.indicators?.patterns,
          },
        }),
      });
      const json = await res.json();
      if (!res.ok || json.error) throw new Error(json.error || 'Gemini analysis unavailable');
      setAiReport(json.synthesis);
    } catch (e: any) {
      setAiError(e.message);
    } finally {
      setAiLoading(false);
    }
  };

  const latest = chartData?.indicators?.latest || {};
  const entryStatus = entryData?.status || 'WAIT';
  const entryColor =
    entryStatus === 'ENTRY TRIGGERED'
      ? 'text-emerald-400'
      : entryStatus === 'WATCH'
      ? 'text-amber-400'
      : entryStatus === 'SETUP INVALIDATED'
      ? 'text-rose-400'
      : 'text-slate-300';

  const sm = chartData?.stock_meta || {};

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-xl font-bold text-slate-100">
            {sm.company_name || chartData?.meta?.longName || symbol} ({chartData?.symbol || symbol} · {sm.exchange || exchange}) — Technicals & Entry/Exit
          </h1>
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400 mt-1">
            {sm.isin && <span className="font-mono">ISIN: {sm.isin}</span>}
            {sm.bse_code && (
              <>
                <span aria-hidden="true">·</span>
                <span className="font-mono">BSE: {sm.bse_code}</span>
              </>
            )}
            {sm.sector && (
              <>
                <span aria-hidden="true">·</span>
                <span>{sm.sector}</span>
              </>
            )}
            <span aria-hidden="true">·</span>
            <span>Source: {chartData?.source || 'Yahoo Finance (Unofficial)'}</span>
            {chartData?.is_delayed && (
              <>
                <span aria-hidden="true">·</span>
                <span>Delayed / EOD Feed</span>
              </>
            )}
            {chartData?.fetched_at_ist && (
              <>
                <span aria-hidden="true">·</span>
                <span className="font-mono">Updated {formatISTTime(chartData.fetched_at_ist)}</span>
              </>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center p-0.5 bg-[#0f1626] border border-slate-800 rounded">
            {(['NSE', 'BSE'] as const).map((ex) => (
              <button
                key={ex}
                type="button"
                onClick={() => onChangeExchange(ex)}
                className={`px-3 py-1 text-xs font-mono rounded ${
                  exchange === ex ? 'bg-slate-800 text-slate-100 font-semibold' : 'text-slate-400'
                }`}
              >
                {ex}
              </button>
            ))}
          </div>

          <div className="flex items-center p-0.5 bg-[#0f1626] border border-slate-800 rounded">
            {['1m', '5m', '15m', '30m', '1h', '1d'].map((tf) => (
              <button
                key={tf}
                type="button"
                onClick={() => setTimeframe(tf)}
                className={`px-2.5 py-1 text-xs font-mono rounded ${
                  timeframe === tf ? 'bg-slate-800 text-slate-100 font-semibold' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={runGeminiResearch}
            disabled={aiLoading || !chartData}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-medium bg-indigo-500/20 border border-indigo-500/40 text-indigo-200 rounded hover:bg-indigo-500/30 disabled:opacity-50 whitespace-nowrap"
          >
            <Sparkles className="w-3.5 h-3.5" />
            {aiLoading ? 'Synthesizing...' : 'AI Desk Thesis'}
          </button>
        </div>
      </div>

      {chartData?.stale && (
        <div className="p-3 bg-amber-950/40 border border-amber-800/60 rounded text-xs text-amber-200">
          Stale Data Notice: {chartData.stale_reason}
        </div>
      )}

      {error && (
        <div className="p-4 bg-rose-950/40 border border-rose-800 rounded text-xs text-rose-200">{error}</div>
      )}

      {/* Key Technical Telemetry Row */}
      {chartData && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {[
            { label: 'Last Price', val: formatINR(latest.close) },
            { label: 'Session VWAP', val: formatINR(latest.vwap) },
            { label: 'EMA 9 / 21', val: `${formatINR(latest.ema9)} / ${formatINR(latest.ema21)}` },
            { label: 'RSI (14)', val: latest.rsi14 ? latest.rsi14.toFixed(2) : '—' },
            { label: 'ATR (14)', val: formatINR(latest.atr14) },
            { label: 'Volume / Ratio', val: `${formatVolume(latest.volume)} (${latest.volume_ratio ?? '—'}x)` },
          ].map((m) => (
            <div key={m.label} className="bg-[#0f1626] border border-slate-800 rounded-lg p-3.5">
              <div className="text-[11px] text-slate-400">{m.label}</div>
              <div className="font-mono text-sm font-semibold text-slate-100 mt-1 tabular-nums">{m.val}</div>
            </div>
          ))}
        </div>
      )}

      {/* Main Chart */}
      {loading && !chartData ? (
        <div className="h-[520px] bg-[#0f1626] border border-slate-800 rounded-lg animate-pulse" />
      ) : chartData?.candles?.length ? (
        <CandlestickTerminalChart
          symbol={`${symbol} (${timeframe})`}
          candles={chartData.candles}
          series={chartData.indicators?.series}
          supportResistance={chartData.indicators?.support_resistance}
        />
      ) : null}

      {/* Gemini AI Research Note (when triggered) */}
      {aiError && (
        <div className="p-4 bg-amber-950/30 border border-amber-800/60 rounded text-xs text-amber-200">{aiError}</div>
      )}
      {aiReport && (
        <div className="bg-[#0f1626] border border-indigo-500/40 rounded-lg p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-sm font-semibold text-indigo-200">
              AI Research Synthesis — {aiReport.thesis_headline}
            </h2>
            <span className="text-xs text-slate-400 font-mono">Gemini Analytical Desk</span>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed">{aiReport.technical_stance}</p>
          <p className="text-xs text-slate-300 leading-relaxed">{aiReport.fundamental_assessment}</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 border-t border-slate-800 text-xs">
            <div>
              <div className="text-emerald-400 font-semibold mb-1">Key Catalysts</div>
              <ul className="space-y-1 text-slate-300 list-disc list-inside">
                {(aiReport.key_catalysts || []).map((c: string, i: number) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
            <div>
              <div className="text-rose-400 font-semibold mb-1">Key Risks</div>
              <ul className="space-y-1 text-slate-300 list-disc list-inside">
                {(aiReport.key_risks || []).map((r: string, i: number) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          </div>
          <div className="text-xs text-amber-200 bg-[#0a0f1c] border border-slate-800 rounded p-3">
            {aiReport.actionable_desk_note}
          </div>
        </div>
      )}

      {/* Entry Timing Engine + Exit Planner + Execution Box */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Module 3: Entry Timing Engine */}
        <div className="bg-[#0f1626] border border-slate-800 rounded-lg p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-sm font-semibold text-slate-100">Entry Timing Engine</h2>
            <span className={`font-mono text-xs font-bold ${entryColor}`}>{entryStatus}</span>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed">{entryData?.summary || 'Evaluating candles...'}</p>
          {entryData?.available && (
            <div className="space-y-2 pt-2 border-t border-slate-800 text-xs font-mono">
              <div className="flex justify-between">
                <span className="text-slate-400">Ideal Entry</span>
                <span className="text-slate-100">{formatINR(entryData.ideal_entry_price)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">VWAP Position</span>
                <span className="text-slate-200">{entryData.checks?.vwap_position}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">EMA Alignment</span>
                <span className="text-slate-200">{entryData.checks?.ema_alignment}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Volume Confirmed</span>
                <span className={entryData.checks?.volume_confirmation ? 'text-emerald-400' : 'text-amber-400'}>
                  {entryData.checks?.volume_confirmation ? 'YES' : 'NO'} ({entryData.checks?.volume_ratio}x)
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Completed Bar</span>
                <span className="text-slate-300">{entryData.confirmation_candle?.date}</span>
              </div>
            </div>
          )}
        </div>

        {/* Module 4: Exit Planner */}
        <div className="bg-[#0f1626] border border-slate-800 rounded-lg p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-sm font-semibold text-slate-100">Exit Planner</h2>
            <span className="text-xs font-mono text-slate-400">
              R:R 1:{exitData?.risk_reward?.target_2_rr ?? '—'}
            </span>
          </div>
          {exitData?.available && (
            <div className="space-y-2 text-xs font-mono">
              <div className="flex justify-between">
                <span className="text-slate-400">Initial Stop-Loss</span>
                <span className="text-rose-400 font-semibold">{formatINR(exitData.initial_stop_loss)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Trailing SL (ATR)</span>
                <span className="text-amber-300">{formatINR(exitData.trailing_stop_loss)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Target 1 ({exitData.risk_reward?.target_1_rr}R)</span>
                <span className="text-emerald-400">{formatINR(exitData.target_1)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Target 2 ({exitData.risk_reward?.target_2_rr}R)</span>
                <span className="text-emerald-400 font-semibold">{formatINR(exitData.target_2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Target 3 ({exitData.risk_reward?.target_3_rr}R)</span>
                <span className="text-emerald-300">{formatINR(exitData.target_3)}</span>
              </div>
              <div className="pt-2 border-t border-slate-800 text-[11px] font-sans text-slate-400 leading-relaxed">
                {exitData.time_based_exit}
              </div>
            </div>
          )}
        </div>

        {/* Trade Sizing & Execution Ticket */}
        <div className="bg-[#0f1626] border border-slate-800 rounded-lg p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-sm font-semibold text-slate-100">Order Ticket & Sizing</h2>
            <span className="text-xs font-mono text-emerald-400">
              {execBroker === 'paper' ? 'PAPER MODE' : `LIVE (${execBroker.toUpperCase()})`}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <label className="block text-slate-400 mb-1">Side</label>
              <div className="flex p-0.5 bg-[#0a0f1c] border border-slate-700 rounded">
                {(['BUY', 'SELL'] as const).map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setOrderSide(s)}
                    className={`flex-1 py-1 font-mono rounded ${
                      orderSide === s
                        ? s === 'BUY'
                          ? 'bg-emerald-500/20 text-emerald-300'
                          : 'bg-rose-500/20 text-rose-300'
                        : 'text-slate-400'
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Product</label>
              <div className="flex p-0.5 bg-[#0a0f1c] border border-slate-700 rounded">
                {(['MIS', 'CNC'] as const).map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setProduct(p)}
                    className={`flex-1 py-1 font-mono rounded ${
                      product === p ? 'bg-slate-700 text-slate-100' : 'text-slate-400'
                    }`}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Execution Destination</label>
            <select
              value={execBroker}
              onChange={(e) => setExecBroker(e.target.value as any)}
              className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-100"
            >
              <option value="paper">Paper Trading Engine (Default Safe)</option>
              <option value="zerodha">Zerodha Kite Connect (Requires Env Token)</option>
              <option value="upstox">Upstox API v2</option>
              <option value="dhan">DhanHQ API v2</option>
            </select>
          </div>

          {sizingData?.allowed && (
            <div className="text-xs font-mono space-y-1 pt-2 border-t border-slate-800">
              <div className="flex justify-between">
                <span className="text-slate-400">Risk-Sized Qty</span>
                <span className="text-slate-100 font-semibold">{sizingData.quantity} shares</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Position Value</span>
                <span className="text-slate-200">{formatINR(sizingData.position_value_inr)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Est. Risk + Charges</span>
                <span className="text-rose-400">{formatINR(sizingData.total_monetary_risk_inr)}</span>
              </div>
            </div>
          )}

          <button
            type="button"
            onClick={openApproval}
            disabled={!exitData?.available}
            className="w-full py-2.5 text-xs font-semibold bg-amber-400 text-slate-950 rounded hover:bg-amber-300 disabled:opacity-50"
          >
            Review & Place {execBroker === 'paper' ? 'Paper' : 'Live'} Order
          </button>

          {orderResult && (
            <div
              className={`p-2.5 rounded border text-xs ${
                orderResult.blocked_by_risk || orderResult.blocked_reason
                  ? 'bg-rose-950/40 border-rose-800 text-rose-200'
                  : 'bg-emerald-950/40 border-emerald-800 text-emerald-200'
              }`}
            >
              {orderResult.blocked_by_risk ? (
                <div>
                  <div className="font-semibold">Blocked by Risk Management Engine</div>
                  <div>{orderResult.risk_check?.violations?.[0]}</div>
                </div>
              ) : orderResult.blocked_reason ? (
                <div>{orderResult.blocked_reason}</div>
              ) : (
                <div className="flex items-center gap-1.5">
                  <CheckCircle2 className="w-4 h-4 shrink-0" />
                  <span>
                    Order {orderResult.order_id} {orderResult.status} ({orderResult.quantity} {orderResult.symbol} @{' '}
                    {formatINR(orderResult.price)})
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <ApprovalModal
        open={modalOpen}
        order={
          exitData?.available
            ? {
                symbol,
                exchange,
                side: orderSide,
                quantity: Math.max(1, sizingData?.quantity || 1),
                price: exitData.entry_price,
                stop_loss: exitData.initial_stop_loss,
                target: exitData.target_2,
                product,
                order_type: 'LIMIT',
                broker: execBroker,
                mode: execBroker === 'paper' ? 'paper' : 'live',
              }
            : null
        }
        preview={previewData}
        onClose={() => setModalOpen(false)}
        onConfirm={confirmOrder}
        submitting={submitting}
      />
    </div>
  );
};
