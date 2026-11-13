import React, { useEffect, useState } from 'react';
import { BellRing, Trash2 } from 'lucide-react';
import { formatINR, formatISTTime } from '../utils/formatters';
import { apiFetch } from '../utils/apiBridge';

interface Props {
  symbol: string;
}

export const AlertsSettingsSection: React.FC<Props> = ({ symbol }) => {
  const [alerts, setAlerts] = useState<any[]>([]);
  const [brokers, setBrokers] = useState<any>(null);
  const [checkSummary, setCheckSummary] = useState<string | null>(null);
  const [form, setForm] = useState({
    symbol,
    condition: 'price_above',
    threshold: '',
    telegram_notify: false,
    message: '',
  });

  useEffect(() => {
    setForm((prev) => ({ ...prev, symbol }));
  }, [symbol]);

  const loadData = async () => {
    const [aRes, bRes] = await Promise.all([apiFetch('/api/alerts'), apiFetch('/api/brokers/status')]);
    const [aJson, bJson] = await Promise.all([aRes.json(), bRes.json()]);
    setAlerts(aJson.alerts || []);
    setBrokers(bJson);
  };

  useEffect(() => {
    loadData();
  }, []);

  const addAlert = async (e: React.FormEvent) => {
    e.preventDefault();
    await apiFetch('/api/alerts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    });
    setForm((prev) => ({ ...prev, threshold: '', message: '' }));
    await loadData();
  };

  const runCheck = async () => {
    const res = await apiFetch('/api/alerts/check', { method: 'POST' });
    const json = await res.json();
    setAlerts(json.all_alerts || []);
    setCheckSummary(
      `Checked ${json.checked_count} active alerts · ${json.triggered_count} triggered at ${formatISTTime(
        json.checked_at_ist
      )}.`
    );
  };

  const removeAlert = async (id: string) => {
    await apiFetch(`/api/alerts/${encodeURIComponent(id)}`, { method: 'DELETE' });
    await loadData();
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-xl font-bold text-slate-100">Price Alerts, Broker Adapters & Settings</h1>
        <p className="text-xs text-slate-400 mt-1">
          Configure entry/SL/target/technical alerts and inspect environment-credentialed Indian broker adapters.
        </p>
      </div>

      {/* Price Alert Builder + Active Rules */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <form onSubmit={addAlert} className="bg-[#0f1626] border border-slate-800 rounded-lg p-5 space-y-3 text-xs">
          <h2 className="font-display text-sm font-semibold text-slate-100">Create Alert Rule</h2>
          <div>
            <label className="block text-slate-400 mb-1">NSE / BSE Symbol</label>
            <input
              type="text"
              required
              placeholder="Enter NSE/BSE symbol (e.g. ORIANA)"
              value={form.symbol}
              onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })}
              className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-2 font-mono text-slate-100"
            />
          </div>
          <div>
            <label className="block text-slate-400 mb-1">Condition</label>
            <select
              value={form.condition}
              onChange={(e) => setForm({ ...form, condition: e.target.value })}
              className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-2 text-slate-100"
            >
              <option value="price_above">Price Reaches Entry / Above (₹)</option>
              <option value="price_below">Price Reaches Stop-Loss / Below (₹)</option>
              <option value="target_hit">Target Hit (₹)</option>
              <option value="vwap_crossover">VWAP Bullish Crossover</option>
              <option value="volume_spike">Volume Spike (e.g. 2.0x)</option>
              <option value="breakout">20-Bar Breakout Confirmation</option>
              <option value="breakdown">20-Bar Breakdown Confirmation</option>
              <option value="unusual_volatility">Unusual ATR Volatility</option>
            </select>
          </div>
          <div>
            <label className="block text-slate-400 mb-1">Threshold (Price ₹ or Multiplier)</label>
            <input
              type="number"
              step="any"
              placeholder="e.g. 1350 or 2.0"
              value={form.threshold}
              onChange={(e) => setForm({ ...form, threshold: e.target.value })}
              className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-2 font-mono text-slate-100"
            />
          </div>
          <label className="flex items-center gap-2 text-slate-300 cursor-pointer pt-1">
            <input
              type="checkbox"
              checked={form.telegram_notify}
              onChange={(e) => setForm({ ...form, telegram_notify: e.target.checked })}
            />
            Send Telegram Notification (requires TELEGRAM_BOT_TOKEN)
          </label>
          <button
            type="submit"
            className="w-full py-2 font-semibold bg-amber-400 text-slate-950 rounded hover:bg-amber-300"
          >
            Add Alert
          </button>
        </form>

        <div className="lg:col-span-2 bg-[#0f1626] border border-slate-800 rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
            <h2 className="font-display text-sm font-semibold text-slate-100">Configured Alerts ({alerts.length})</h2>
            <button
              type="button"
              onClick={runCheck}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-100 rounded"
            >
              <BellRing className="w-3.5 h-3.5" />
              Check Alerts Now
            </button>
          </div>
          {checkSummary && (
            <div className="px-4 py-2 bg-[#0a0f1c] border-b border-slate-800 text-xs font-mono text-sky-300">
              {checkSummary}
            </div>
          )}
          {alerts.length === 0 ? (
            <div className="p-8 text-center text-xs text-slate-400">No active alerts configured yet.</div>
          ) : (
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400 font-sans">
                  <th className="text-left px-4 py-2.5">Symbol</th>
                  <th className="text-left px-4 py-2.5">Condition</th>
                  <th className="text-right px-4 py-2.5">Threshold</th>
                  <th className="text-left px-4 py-2.5">Status / Message</th>
                  <th className="text-right px-4 py-2.5">Remove</th>
                </tr>
              </thead>
              <tbody>
                {alerts.map((al) => (
                  <tr key={al.alert_id} className="border-b border-slate-800/60">
                    <td className="px-4 py-2.5 font-semibold text-slate-100">{al.symbol}</td>
                    <td className="px-4 py-2.5 text-slate-300 font-sans">{al.condition}</td>
                    <td className="px-4 py-2.5 text-right">
                      {al.threshold !== null && al.threshold !== undefined ? formatINR(al.threshold) : 'Auto'}
                    </td>
                    <td className="px-4 py-2.5 font-sans">
                      <span className={al.status === 'TRIGGERED' ? 'text-amber-300 font-semibold' : 'text-emerald-400'}>
                        {al.status}
                      </span>
                      {al.message ? <span className="text-slate-400 ml-2">{al.message}</span> : null}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <button
                        type="button"
                        onClick={() => removeAlert(al.alert_id)}
                        className="p-1 text-slate-400 hover:text-rose-400"
                        aria-label="Delete alert"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Indian Broker Integration Status & Market Settings */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-[#0f1626] border border-slate-800 rounded-lg p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-sm font-semibold text-slate-100">Indian Broker Adapter Architecture</h2>
            <span className="text-xs font-mono text-emerald-400">Paper Trading Default: ON</span>
          </div>
          <p className="text-xs text-slate-400 leading-relaxed">
            Credentials are read strictly from server environment variables (never hardcoded or stored in source code).
            Live orders require the 7-point pre-execution approval gate.
          </p>
          <div className="space-y-2 pt-1">
            {(brokers?.brokers || []).map((b: any) => (
              <div
                key={b.id}
                className="flex items-center justify-between p-3 bg-[#0a0f1c] border border-slate-800 rounded text-xs"
              >
                <div>
                  <div className="font-semibold text-slate-100">{b.name}</div>
                  <div className="text-slate-500 font-mono text-[11px]">Adapter: {b.id}</div>
                </div>
                <span className={`font-mono ${b.configured ? 'text-emerald-400' : 'text-slate-400'}`}>
                  {b.configured ? 'CREDENTIALS DETECTED' : 'ENV NOT SET (PAPER SAFE)'}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-[#0f1626] border border-slate-800 rounded-lg p-5 space-y-3 text-xs">
          <h2 className="font-display text-sm font-semibold text-slate-100">Indian Market Timings & Calendar (IST)</h2>
          <div className="space-y-2 font-mono">
            <div className="flex justify-between border-b border-slate-800 pb-1.5">
              <span className="text-slate-400 font-sans">Pre-Open Order Collection</span>
              <span className="text-slate-100">09:00 – 09:15 IST</span>
            </div>
            <div className="flex justify-between border-b border-slate-800 pb-1.5">
              <span className="text-slate-400 font-sans">Regular NSE / BSE Session</span>
              <span className="text-slate-100">09:15 – 15:30 IST</span>
            </div>
            <div className="flex justify-between border-b border-slate-800 pb-1.5">
              <span className="text-slate-400 font-sans">Intraday MIS Auto Square-Off</span>
              <span className="text-amber-300">15:15 IST</span>
            </div>
            <div className="flex justify-between border-b border-slate-800 pb-1.5">
              <span className="text-slate-400 font-sans">Trading Days</span>
              <span className="text-slate-100">Mon – Fri (Excl. NSE/BSE Holidays)</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400 font-sans">Special Sessions Supported</span>
              <span className="text-slate-100">Diwali Muhurat · Union Budget</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
