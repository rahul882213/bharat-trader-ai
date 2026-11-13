import React, { useEffect, useState } from 'react';
import { Play } from 'lucide-react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { formatINR } from '../utils/formatters';

interface Props {
  symbol: string;
}

export const BacktestSection: React.FC<Props> = ({ symbol }) => {
  const [strategy, setStrategy] = useState('ema_crossover');
  const [timeframe, setTimeframe] = useState('1d');
  const [tradeType, setTradeType] = useState('equity_intraday');
  const [capital, setCapital] = useState(1000000);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runBacktest = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/backtest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol,
          strategy,
          timeframe,
          trade_type: tradeType,
          capital,
          runs: 10000,
        }),
      });
      const json = await res.json();
      if (!json.available) throw new Error(json.error || 'Backtest failed');
      setData(json);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    runBacktest();
  }, [symbol]);

  const m = data?.metrics || {};
  const mc = data?.monte_carlo || {};

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-xl font-bold text-slate-100">
            AI Backtesting Engine & 10,000-Run Monte Carlo ({symbol})
          </h1>
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400 mt-1">
            <span>Walk-forward Bar-by-Bar Execution (Look-Ahead Bias Prevented)</span>
            <span aria-hidden="true">·</span>
            <span>Includes Indian STT, GST, SEBI & Stamp Duty</span>
          </div>
        </div>
        <button
          type="button"
          onClick={runBacktest}
          disabled={loading}
          className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold bg-amber-400 text-slate-950 rounded hover:bg-amber-300 disabled:opacity-50"
        >
          <Play className="w-3.5 h-3.5" />
          {loading ? 'Running 10,000 Sims...' : 'Run Backtest'}
        </button>
      </div>

      {/* Parameters */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 bg-[#0f1626] border border-slate-800 rounded-lg p-4 text-xs">
        <div>
          <label className="block text-slate-400 mb-1">Strategy</label>
          <select
            value={strategy}
            onChange={(e) => setStrategy(e.target.value)}
            className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-2 text-slate-100"
          >
            <option value="ema_crossover">EMA Crossover (9 / 21)</option>
            <option value="orb">Opening Range / 3-Bar Breakout</option>
            <option value="vwap_breakout">VWAP Breakout</option>
            <option value="rsi_reversal">RSI Oversold Reversal</option>
            <option value="macd_crossover">MACD Crossover</option>
          </select>
        </div>
        <div>
          <label className="block text-slate-400 mb-1">Timeframe</label>
          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-2 text-slate-100 font-mono"
          >
            <option value="1d">1d (2Y Daily)</option>
            <option value="1h">1h (3M Intraday)</option>
            <option value="15m">15m (1M Intraday)</option>
            <option value="5m">5m (1M Intraday)</option>
          </select>
        </div>
        <div>
          <label className="block text-slate-400 mb-1">Charge Profile</label>
          <select
            value={tradeType}
            onChange={(e) => setTradeType(e.target.value)}
            className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-2 text-slate-100"
          >
            <option value="equity_intraday">Equity Intraday (MIS)</option>
            <option value="equity_delivery">Equity Delivery (CNC)</option>
          </select>
        </div>
        <div>
          <label className="block text-slate-400 mb-1">Initial Capital (₹)</label>
          <input
            type="number"
            value={capital}
            onChange={(e) => setCapital(Number(e.target.value) || 1000000)}
            className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-2 text-slate-100 font-mono"
          />
        </div>
      </div>

      {error && (
        <div className="p-4 bg-rose-950/40 border border-rose-800 rounded text-xs text-rose-200">{error}</div>
      )}

      {data && (
        <>
          {/* Metrics Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
            {[
              { label: 'Net P&L', val: formatINR(data.net_pnl), cls: data.net_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400' },
              { label: 'Win Rate', val: `${m.win_rate_pct ?? 0}%`, cls: 'text-slate-100' },
              { label: 'Profit Factor', val: String(m.profit_factor ?? 0), cls: 'text-slate-100' },
              { label: 'Max Drawdown', val: `${m.max_drawdown_pct ?? 0}%`, cls: 'text-rose-400' },
              { label: 'Sharpe Ratio', val: String(m.sharpe_ratio ?? 0), cls: 'text-slate-100' },
              { label: 'Total Charges (₹)', val: formatINR(m.total_charges_inr), cls: 'text-amber-300' },
            ].map((k) => (
              <div key={k.label} className="bg-[#0f1626] border border-slate-800 rounded-lg p-3.5">
                <div className="text-[11px] text-slate-400">{k.label}</div>
                <div className={`font-mono text-base font-semibold mt-1 tabular-nums ${k.cls}`}>{k.val}</div>
              </div>
            ))}
          </div>

          {/* Secondary Metrics */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 bg-[#0f1626] border border-slate-800 rounded-lg p-4 text-xs font-mono">
            <div>
              <div className="text-slate-400 font-sans">Total Trades</div>
              <div className="text-slate-100 mt-0.5">{m.total_trades}</div>
            </div>
            <div>
              <div className="text-slate-400 font-sans">Avg Win</div>
              <div className="text-emerald-400 mt-0.5">{formatINR(m.avg_winning_trade_inr)}</div>
            </div>
            <div>
              <div className="text-slate-400 font-sans">Avg Loss</div>
              <div className="text-rose-400 mt-0.5">{formatINR(m.avg_losing_trade_inr)}</div>
            </div>
            <div>
              <div className="text-slate-400 font-sans">Expectancy / Trade</div>
              <div className="text-slate-100 mt-0.5">{formatINR(m.expectancy_inr)}</div>
            </div>
            <div>
              <div className="text-slate-400 font-sans">Max Consec. Losses</div>
              <div className="text-amber-300 mt-0.5">{m.max_consecutive_losses}</div>
            </div>
          </div>

          {/* Charts: Equity Curve + 10,000 Monte Carlo Distribution */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="bg-[#0f1626] border border-slate-800 rounded-lg p-4">
              <div className="font-display text-sm font-semibold text-slate-100 mb-3">Historical Equity Curve (INR)</div>
              <div className="h-[240px]">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={data.equity_curve || []}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 10 }} minTickGap={24} />
                    <YAxis tick={{ fill: '#64748b', fontSize: 10 }} width={64} domain={['auto', 'auto']} />
                    <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', fontSize: '12px' }} />
                    <Area type="monotone" dataKey="equity" stroke="#10b981" fill="rgba(16,185,129,0.18)" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="bg-[#0f1626] border border-slate-800 rounded-lg p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="font-display text-sm font-semibold text-slate-100">
                  10,000-Run Monte Carlo Terminal Equity
                </div>
                <span className="text-xs font-mono text-sky-300">
                  Prob. Profit: {mc.probability_of_profit_pct ?? 0}%
                </span>
              </div>
              <div className="h-[190px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={mc.distribution_histogram || []}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="range_label" tick={{ fill: '#64748b', fontSize: 10 }} />
                    <YAxis tick={{ fill: '#64748b', fontSize: 10 }} width={40} />
                    <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', fontSize: '12px' }} />
                    <Bar dataKey="runs" fill="#38bdf8" name="Simulated Runs" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="text-[11px] text-amber-200/90 bg-[#0a0f1c] border border-slate-800 rounded p-2.5">
                {mc.disclaimer}
              </div>
            </div>
          </div>

          {/* Walk-forward Trade Log */}
          <div className="bg-[#0f1626] border border-slate-800 rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between text-xs">
              <span className="font-display font-semibold text-sm text-slate-100">Historical Backtest Trade Log</span>
              <span className="text-slate-400">{data.bias_controls?.survivorship_bias_notice}</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 font-sans">
                    <th className="text-left px-4 py-2">Entry Date</th>
                    <th className="text-left px-4 py-2">Exit Date</th>
                    <th className="text-right px-4 py-2">Qty</th>
                    <th className="text-right px-4 py-2">Entry ₹</th>
                    <th className="text-right px-4 py-2">Exit ₹</th>
                    <th className="text-right px-4 py-2">Charges ₹</th>
                    <th className="text-right px-4 py-2">Net P&L ₹</th>
                    <th className="text-left px-4 py-2">Exit Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.trades || []).map((t: any, idx: number) => (
                    <tr key={idx} className="border-b border-slate-800/60">
                      <td className="px-4 py-2 text-slate-300">{t.entry_date}</td>
                      <td className="px-4 py-2 text-slate-300">{t.exit_date}</td>
                      <td className="px-4 py-2 text-right">{t.quantity}</td>
                      <td className="px-4 py-2 text-right">{formatINR(t.entry_price)}</td>
                      <td className="px-4 py-2 text-right">{formatINR(t.exit_price)}</td>
                      <td className="px-4 py-2 text-right text-amber-300">{formatINR(t.charges_inr)}</td>
                      <td className={`px-4 py-2 text-right ${t.net_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {formatINR(t.net_pnl)}
                      </td>
                      <td className="px-4 py-2 text-slate-400 font-sans">{t.exit_reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
