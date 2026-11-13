import React, { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { formatINR, formatISTTime } from '../utils/formatters';
import { apiFetch } from '../utils/apiBridge';

export const PortfolioRiskSection: React.FC = () => {
  const [portfolioData, setPortfolioData] = useState<any>(null);
  const [riskData, setRiskData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [savingRisk, setSavingRisk] = useState(false);

  // Editable risk settings
  const [riskForm, setRiskForm] = useState<any>({
    total_capital_inr: 1000000,
    max_risk_per_trade_pct: 1.0,
    max_daily_loss_pct: 3.0,
    min_risk_reward_ratio: 2.0,
    max_trades_per_day: 5,
    max_open_positions: 4,
    max_sector_exposure_pct: 30.0,
    max_portfolio_exposure_pct: 80.0,
    fno_enabled: false,
  });

  // Position Size Calculator State
  const [calcInput, setCalcInput] = useState({
    entry_price: 500,
    stop_loss: 480,
    segment: 'cash_equity',
    trade_type: 'equity_intraday',
    lot_size: 25,
  });
  const [calcResult, setCalcResult] = useState<any>(null);

  const loadAll = async (liveLtp = false) => {
    setLoading(true);
    try {
      const [pRes, rRes] = await Promise.all([
        apiFetch(`/api/portfolio${liveLtp ? '?live=1' : ''}`),
        apiFetch('/api/risk'),
      ]);
      const [pJson, rJson] = await Promise.all([pRes.json(), rRes.json()]);
      setPortfolioData(pJson);
      setRiskData(rJson);
      if (rJson?.config) {
        setRiskForm({
          total_capital_inr: rJson.config.total_capital_inr,
          max_risk_per_trade_pct: rJson.config.max_risk_per_trade_pct,
          max_daily_loss_pct: rJson.config.max_daily_loss_pct,
          min_risk_reward_ratio: rJson.config.min_risk_reward_ratio,
          max_trades_per_day: rJson.config.max_trades_per_day,
          max_open_positions: rJson.config.max_open_positions,
          max_sector_exposure_pct: rJson.config.max_sector_exposure_pct,
          max_portfolio_exposure_pct: rJson.config.max_portfolio_exposure_pct,
          fno_enabled: Boolean(rJson.config.fno_enabled),
        });
      }
    } finally {
      setLoading(false);
    }
  };

  const calculateSize = async () => {
    const res = await apiFetch('/api/budget/calculate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        capital_inr: riskForm.total_capital_inr,
        risk_pct: riskForm.max_risk_per_trade_pct,
        entry_price: calcInput.entry_price,
        stop_loss: calcInput.stop_loss,
        segment: calcInput.segment,
        trade_type: calcInput.trade_type,
        lot_size: calcInput.lot_size,
        fno_enabled: riskForm.fno_enabled,
      }),
    });
    setCalcResult(await res.json());
  };

  useEffect(() => {
    loadAll(false);
    calculateSize();
  }, []);

  const saveRiskSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingRisk(true);
    try {
      await apiFetch('/api/risk/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(riskForm),
      });
      await loadAll(false);
      await calculateSize();
    } finally {
      setSavingRisk(false);
    }
  };

  const squareOff = async (pos: any) => {
    await apiFetch('/api/positions/close', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        symbol: pos.symbol,
        exchange: pos.exchange,
        product: pos.product,
      }),
    });
    await loadAll(true);
  };

  const port = portfolioData?.portfolio || {};
  const positions: any[] = portfolioData?.positions || [];
  const journal: any[] = portfolioData?.journal || [];
  const orders: any[] = portfolioData?.orders || [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-xl font-bold text-slate-100">
            Portfolio, Open Positions, Risk Dashboard & Trade Journal
          </h1>
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400 mt-1">
            <span>Mode: {port.mode === 'paper' ? 'Paper Trading Engine (Default)' : 'Live Broker'}</span>
            <span aria-hidden="true">·</span>
            <span>Currency: INR (₹)</span>
            {port.updated_at_ist && (
              <>
                <span aria-hidden="true">·</span>
                <span className="font-mono">Updated {formatISTTime(port.updated_at_ist)}</span>
              </>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={() => loadAll(true)}
          disabled={loading}
          className="inline-flex items-center gap-2 px-4 py-2 text-xs font-medium bg-[#131b2e] border border-slate-700 text-slate-200 rounded hover:bg-slate-800"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh Live MTM
        </button>
      </div>

      {/* Portfolio KPI Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {[
          { label: 'Total Equity', val: formatINR(port.total_equity_inr), cls: 'text-slate-100' },
          { label: 'Available Cash', val: formatINR(port.available_cash_inr), cls: 'text-slate-100' },
          { label: 'Deployed Capital', val: formatINR(port.deployed_margin_inr), cls: 'text-sky-300' },
          {
            label: 'Realized P&L',
            val: formatINR(port.realized_pnl_inr),
            cls: (port.realized_pnl_inr ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400',
          },
          {
            label: 'Unrealized MTM',
            val: formatINR(port.unrealized_pnl_inr),
            cls: (port.unrealized_pnl_inr ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400',
          },
          {
            label: 'Daily Risk Status',
            val: riskData?.status || 'NOMINAL',
            cls: riskData?.status === 'BLOCKED' ? 'text-rose-400' : 'text-emerald-400',
          },
        ].map((k) => (
          <div key={k.label} className="bg-[#0f1626] border border-slate-800 rounded-lg p-3.5">
            <div className="text-[11px] text-slate-400">{k.label}</div>
            <div className={`font-mono text-base font-semibold mt-1 tabular-nums ${k.cls}`}>{k.val}</div>
          </div>
        ))}
      </div>

      {/* Open Positions */}
      <div className="bg-[#0f1626] border border-slate-800 rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
          <h2 className="font-display text-sm font-semibold text-slate-100">Open Positions ({positions.length})</h2>
          <span className="text-xs text-slate-400">Real-time NSE/BSE square-off available</span>
        </div>
        {positions.length === 0 ? (
          <div className="p-6 text-center text-xs text-slate-400">
            No open positions. Use the Technicals & Entry/Exit tab to place a risk-checked paper order.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400 font-sans">
                  <th className="text-left px-4 py-2.5">Symbol</th>
                  <th className="text-left px-4 py-2.5">Side / Prod</th>
                  <th className="text-right px-4 py-2.5">Qty</th>
                  <th className="text-right px-4 py-2.5">Avg Price</th>
                  <th className="text-right px-4 py-2.5">LTP</th>
                  <th className="text-right px-4 py-2.5">SL / Target</th>
                  <th className="text-right px-4 py-2.5">Unrealized P&L</th>
                  <th className="text-right px-4 py-2.5">Action</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos) => (
                  <tr key={`${pos.symbol}-${pos.product}`} className="border-b border-slate-800/60">
                    <td className="px-4 py-2.5 font-semibold text-slate-100">{pos.symbol}</td>
                    <td className="px-4 py-2.5 text-slate-300">
                      {pos.side} · {pos.product}
                    </td>
                    <td className="px-4 py-2.5 text-right">{pos.quantity}</td>
                    <td className="px-4 py-2.5 text-right">{formatINR(pos.avg_price)}</td>
                    <td className="px-4 py-2.5 text-right">{formatINR(pos.ltp)}</td>
                    <td className="px-4 py-2.5 text-right text-slate-400">
                      {formatINR(pos.stop_loss)} / {formatINR(pos.target)}
                    </td>
                    <td
                      className={`px-4 py-2.5 text-right ${
                        pos.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {formatINR(pos.unrealized_pnl)}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <button
                        type="button"
                        onClick={() => squareOff(pos)}
                        className="px-3 py-1 text-xs font-sans font-medium bg-rose-950/60 border border-rose-800 text-rose-200 rounded hover:bg-rose-900/60"
                      >
                        Square Off
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Risk Management Rules + Position Size Calculator */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <form onSubmit={saveRiskSettings} className="bg-[#0f1626] border border-slate-800 rounded-lg p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-sm font-semibold text-slate-100">Risk Management Engine Rules</h2>
            <span className="text-xs font-mono text-slate-400">
              Trades Today: {riskData?.trades_today ?? 0}/{riskForm.max_trades_per_day}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3 text-xs">
            {[
              { key: 'total_capital_inr', label: 'Trading Capital (₹)' },
              { key: 'max_risk_per_trade_pct', label: 'Max Risk / Trade (%)' },
              { key: 'max_daily_loss_pct', label: 'Max Daily Loss (%)' },
              { key: 'min_risk_reward_ratio', label: 'Min R:R Ratio (1:X)' },
              { key: 'max_trades_per_day', label: 'Max Trades / Day' },
              { key: 'max_open_positions', label: 'Max Open Positions' },
              { key: 'max_sector_exposure_pct', label: 'Max Sector Exposure (%)' },
              { key: 'max_portfolio_exposure_pct', label: 'Max Portfolio Exposure (%)' },
            ].map((fld) => (
              <div key={fld.key}>
                <label className="block text-slate-400 mb-1">{fld.label}</label>
                <input
                  type="number"
                  step="any"
                  value={riskForm[fld.key]}
                  onChange={(e) => setRiskForm({ ...riskForm, [fld.key]: Number(e.target.value) })}
                  className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-1.5 font-mono text-slate-100"
                />
              </div>
            ))}
          </div>

          <div className="flex items-center justify-between pt-2 border-t border-slate-800">
            <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={riskForm.fno_enabled}
                onChange={(e) => setRiskForm({ ...riskForm, fno_enabled: e.target.checked })}
              />
              Enable F&O Module (Disabled by default)
            </label>
            <button
              type="submit"
              disabled={savingRisk}
              className="px-4 py-2 text-xs font-semibold bg-amber-400 text-slate-950 rounded hover:bg-amber-300"
            >
              {savingRisk ? 'Saving...' : 'Save Risk Limits'}
            </button>
          </div>
        </form>

        {/* Position Size Calculator */}
        <div className="bg-[#0f1626] border border-slate-800 rounded-lg p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-sm font-semibold text-slate-100">Position Size Calculator (INR)</h2>
            <span className="text-xs font-mono text-slate-400">
              Budget: {formatINR((riskForm.total_capital_inr * riskForm.max_risk_per_trade_pct) / 100)}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <label className="block text-slate-400 mb-1">Segment</label>
              <select
                value={calcInput.segment}
                onChange={(e) => setCalcInput({ ...calcInput, segment: e.target.value })}
                className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-1.5 text-slate-100"
              >
                <option value="cash_equity">Cash Equity</option>
                <option value="fno">F&O (Requires Opt-in)</option>
              </select>
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Trade Type</label>
              <select
                value={calcInput.trade_type}
                onChange={(e) => setCalcInput({ ...calcInput, trade_type: e.target.value })}
                className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-1.5 text-slate-100"
              >
                <option value="equity_intraday">Equity Intraday (MIS)</option>
                <option value="equity_delivery">Equity Delivery (CNC)</option>
              </select>
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Entry Price (₹)</label>
              <input
                type="number"
                step="0.05"
                value={calcInput.entry_price}
                onChange={(e) => setCalcInput({ ...calcInput, entry_price: Number(e.target.value) })}
                className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-1.5 font-mono text-slate-100"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Stop-Loss (₹)</label>
              <input
                type="number"
                step="0.05"
                value={calcInput.stop_loss}
                onChange={(e) => setCalcInput({ ...calcInput, stop_loss: Number(e.target.value) })}
                className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-1.5 font-mono text-slate-100"
              />
            </div>
          </div>

          <button
            type="button"
            onClick={calculateSize}
            className="w-full py-2 text-xs font-medium bg-slate-800 border border-slate-700 text-slate-100 rounded hover:bg-slate-700"
          >
            Calculate Quantity & Statutory Charges
          </button>

          {calcResult && (
            <div className="bg-[#0a0f1c] border border-slate-800 rounded p-3.5 text-xs font-mono space-y-1.5">
              {!calcResult.allowed ? (
                <div className="text-rose-400 font-sans">{calcResult.error}</div>
              ) : (
                <>
                  <div className="flex justify-between">
                    <span className="text-slate-400 font-sans">Max Compliant Quantity</span>
                    <span className="text-emerald-400 font-semibold">{calcResult.quantity} shares</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400 font-sans">Position Value</span>
                    <span className="text-slate-100">{formatINR(calcResult.position_value_inr)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400 font-sans">Est. Brokerage + STT + GST + Stamp</span>
                    <span className="text-amber-300">{formatINR(calcResult.estimated_charges_inr)}</span>
                  </div>
                  <div className="flex justify-between pt-1 border-t border-slate-800">
                    <span className="text-slate-300 font-sans">Total Monetary Risk (Stop + Charges)</span>
                    <span className="text-rose-400 font-semibold">{formatINR(calcResult.total_monetary_risk_inr)}</span>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Trade Journal & Order History */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-[#0f1626] border border-slate-800 rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-800 font-display text-sm font-semibold text-slate-100">
            Trade Journal ({journal.length})
          </div>
          {journal.length === 0 ? (
            <div className="p-6 text-center text-xs text-slate-400">
              Closed trades will appear here with realized gross P&L, Indian charges, and net P&L.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 font-sans">
                    <th className="text-left px-4 py-2">Symbol</th>
                    <th className="text-right px-4 py-2">Qty</th>
                    <th className="text-right px-4 py-2">Entry → Exit</th>
                    <th className="text-right px-4 py-2">Charges</th>
                    <th className="text-right px-4 py-2">Net P&L</th>
                  </tr>
                </thead>
                <tbody>
                  {journal.map((t) => (
                    <tr key={t.trade_id} className="border-b border-slate-800/60">
                      <td className="px-4 py-2 text-slate-100">{t.symbol}</td>
                      <td className="px-4 py-2 text-right">{t.quantity}</td>
                      <td className="px-4 py-2 text-right text-slate-300">
                        {formatINR(t.entry_price)} → {formatINR(t.exit_price)}
                      </td>
                      <td className="px-4 py-2 text-right text-amber-300">{formatINR(t.charges_inr)}</td>
                      <td className={`px-4 py-2 text-right ${t.net_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {formatINR(t.net_pnl)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="bg-[#0f1626] border border-slate-800 rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-800 font-display text-sm font-semibold text-slate-100">
            Recent Orders ({orders.length})
          </div>
          {orders.length === 0 ? (
            <div className="p-6 text-center text-xs text-slate-400">No paper or live orders logged yet.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 font-sans">
                    <th className="text-left px-4 py-2">Order ID</th>
                    <th className="text-left px-4 py-2">Symbol / Side</th>
                    <th className="text-right px-4 py-2">Qty @ Price</th>
                    <th className="text-right px-4 py-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((o) => (
                    <tr key={o.order_id} className="border-b border-slate-800/60">
                      <td className="px-4 py-2 text-slate-400">{o.order_id}</td>
                      <td className="px-4 py-2 text-slate-100">
                        {o.symbol} ({o.side} · {o.product})
                      </td>
                      <td className="px-4 py-2 text-right">
                        {o.quantity} @ {formatINR(o.price)}
                      </td>
                      <td className="px-4 py-2 text-right text-emerald-400">{o.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
