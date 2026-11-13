import React, { useEffect, useRef, useState } from 'react';
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  createChart,
  type Time,
} from 'lightweight-charts';
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  BarChart,
  Bar,
  Cell,
} from 'recharts';
import type { CandleBar } from '../types/trading';

interface Props {
  symbol: string;
  candles: CandleBar[];
  series?: {
    ema9?: (number | null)[];
    ema21?: (number | null)[];
    ema50?: (number | null)[];
    vwap?: (number | null)[];
    bb_upper?: (number | null)[];
    bb_lower?: (number | null)[];
    rsi14?: (number | null)[];
    macd?: (number | null)[];
    macd_signal?: (number | null)[];
    macd_hist?: (number | null)[];
  };
  supportResistance?: {
    supports?: number[];
    resistances?: number[];
  };
}

export const CandlestickTerminalChart: React.FC<Props> = ({
  symbol,
  candles,
  series,
  supportResistance,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [showEma, setShowEma] = useState(true);
  const [showVwap, setShowVwap] = useState(true);
  const [showBB, setShowBB] = useState(false);
  const [showSR, setShowSR] = useState(true);
  const [subPanel, setSubPanel] = useState<'rsi' | 'macd'>('rsi');

  useEffect(() => {
    const el = containerRef.current;
    if (!el || !candles.length) return;

    const chart = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: '#0c1220' },
        textColor: '#94a3b8',
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: 'rgba(30, 41, 59, 0.55)' },
        horzLines: { color: 'rgba(30, 41, 59, 0.55)' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#1e293b' },
      timeScale: { borderColor: '#1e293b', timeVisible: true, secondsVisible: false },
      width: el.clientWidth,
      height: 410,
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    });

    // Deduplicate/sort strictly ascending times for Lightweight Charts
    const seenTimes = new Set<string | number>();
    const normalized: { idx: number; time: Time; bar: CandleBar }[] = [];
    candles.forEach((c, idx) => {
      const t = (typeof c.time === 'number' ? c.time : String(c.time)) as Time;
      const key = String(t);
      if (!seenTimes.has(key)) {
        seenTimes.add(key);
        normalized.push({ idx, time: t, bar: c });
      }
    });

    candleSeries.setData(
      normalized.map((item) => ({
        time: item.time,
        open: item.bar.open,
        high: item.bar.high,
        low: item.bar.low,
        close: item.bar.close,
      }))
    );

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    });
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });
    volumeSeries.setData(
      normalized.map((item) => ({
        time: item.time,
        value: item.bar.volume,
        color:
          item.bar.close >= item.bar.open
            ? 'rgba(16, 185, 129, 0.32)'
            : 'rgba(239, 68, 68, 0.32)',
      }))
    );

    const addOverlayLine = (vals: (number | null)[] | undefined, color: string, lineWidth: 1 | 2 = 1) => {
      if (!vals) return;
      const pts = normalized
        .map((item) => {
          const v = vals[item.idx];
          return v !== null && v !== undefined ? { time: item.time, value: v } : null;
        })
        .filter((x): x is { time: Time; value: number } => x !== null);
      if (!pts.length) return;
      const ls = chart.addSeries(LineSeries, {
        color,
        lineWidth,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      ls.setData(pts);
    };

    if (showEma && series) {
      addOverlayLine(series.ema9, '#38bdf8', 1);
      addOverlayLine(series.ema21, '#f59e0b', 2);
      addOverlayLine(series.ema50, '#a855f7', 1);
    }
    if (showVwap && series) {
      addOverlayLine(series.vwap, '#eab308', 2);
    }
    if (showBB && series) {
      addOverlayLine(series.bb_upper, 'rgba(148, 163, 184, 0.55)', 1);
      addOverlayLine(series.bb_lower, 'rgba(148, 163, 184, 0.55)', 1);
    }

    if (showSR && supportResistance) {
      supportResistance.supports?.slice(0, 2).forEach((lvl, i) => {
        candleSeries.createPriceLine({
          price: lvl,
          color: '#10b981',
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `S${i + 1}`,
        });
      });
      supportResistance.resistances?.slice(0, 2).forEach((lvl, i) => {
        candleSeries.createPriceLine({
          price: lvl,
          color: '#ef4444',
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `R${i + 1}`,
        });
      });
    }

    chart.timeScale().fitContent();

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [candles, series, supportResistance, showEma, showVwap, showBB, showSR]);

  const oscData = candles.slice(-80).map((c, idx) => {
    const offset = Math.max(0, candles.length - 80) + idx;
    return {
      date: c.date.slice(5, 16),
      rsi: series?.rsi14?.[offset] ?? null,
      macd: series?.macd?.[offset] ?? null,
      signal: series?.macd_signal?.[offset] ?? null,
      hist: series?.macd_hist?.[offset] ?? null,
    };
  });

  return (
    <div className="bg-[#0c1220] border border-slate-800 rounded-lg overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 border-b border-slate-800 bg-[#0f1626]">
        <div className="flex items-center gap-3 text-xs text-slate-400">
          <span className="font-display font-semibold text-slate-100 text-sm">{symbol}</span>
          <span aria-hidden="true">·</span>
          <span>EMA 9 (Cyan) / 21 (Amber) / 50 (Violet)</span>
          <span aria-hidden="true">·</span>
          <span>VWAP (Gold)</span>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={() => setShowEma((v) => !v)}
            className={`px-2.5 py-1 text-xs rounded border transition-colors whitespace-nowrap shrink-0 ${
              showEma
                ? 'bg-slate-800 border-sky-500/60 text-sky-300'
                : 'border-slate-800 text-slate-400 hover:text-slate-200'
            }`}
          >
            EMA 9/21/50
          </button>
          <button
            type="button"
            onClick={() => setShowVwap((v) => !v)}
            className={`px-2.5 py-1 text-xs rounded border transition-colors whitespace-nowrap shrink-0 ${
              showVwap
                ? 'bg-slate-800 border-amber-500/60 text-amber-300'
                : 'border-slate-800 text-slate-400 hover:text-slate-200'
            }`}
          >
            VWAP
          </button>
          <button
            type="button"
            onClick={() => setShowBB((v) => !v)}
            className={`px-2.5 py-1 text-xs rounded border transition-colors whitespace-nowrap shrink-0 ${
              showBB
                ? 'bg-slate-800 border-slate-500 text-slate-100'
                : 'border-slate-800 text-slate-400 hover:text-slate-200'
            }`}
          >
            Bollinger
          </button>
          <button
            type="button"
            onClick={() => setShowSR((v) => !v)}
            className={`px-2.5 py-1 text-xs rounded border transition-colors whitespace-nowrap shrink-0 ${
              showSR
                ? 'bg-slate-800 border-emerald-500/60 text-emerald-300'
                : 'border-slate-800 text-slate-400 hover:text-slate-200'
            }`}
          >
            S/R Levels
          </button>
        </div>
      </div>

      <div ref={containerRef} className="w-full h-[410px]" />

      {/* Sub-chart Oscillator Panel: RSI(14) or MACD(12,26,9) */}
      <div className="border-t border-slate-800 px-4 py-3 bg-[#0a0f1c]">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1 p-0.5 bg-slate-900 border border-slate-800 rounded-md">
            <button
              type="button"
              onClick={() => setSubPanel('rsi')}
              className={`px-3 py-1 text-xs font-medium rounded transition-colors whitespace-nowrap ${
                subPanel === 'rsi' ? 'bg-slate-800 text-slate-100' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              RSI (14)
            </button>
            <button
              type="button"
              onClick={() => setSubPanel('macd')}
              className={`px-3 py-1 text-xs font-medium rounded transition-colors whitespace-nowrap ${
                subPanel === 'macd' ? 'bg-slate-800 text-slate-100' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              MACD (12, 26, 9)
            </button>
          </div>
          <span className="text-xs text-slate-500 font-mono">Last 80 bars</span>
        </div>

        <div className="h-[130px] w-full">
          {subPanel === 'rsi' ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={oscData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 10 }} minTickGap={24} />
                <YAxis domain={[0, 100]} tick={{ fill: '#64748b', fontSize: 10 }} width={32} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', fontSize: '12px' }}
                />
                <ReferenceLine y={70} stroke="#ef4444" strokeDasharray="3 3" />
                <ReferenceLine y={30} stroke="#10b981" strokeDasharray="3 3" />
                <Line type="monotone" dataKey="rsi" stroke="#38bdf8" dot={false} strokeWidth={1.75} name="RSI(14)" />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={oscData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 10 }} minTickGap={24} />
                <YAxis tick={{ fill: '#64748b', fontSize: 10 }} width={36} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', fontSize: '12px' }}
                />
                <ReferenceLine y={0} stroke="#475569" />
                <Bar dataKey="hist" name="Histogram">
                  {oscData.map((entry, idx) => (
                    <Cell key={idx} fill={(entry.hist ?? 0) >= 0 ? '#10b981' : '#ef4444'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
};
