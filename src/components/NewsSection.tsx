import React, { useEffect, useState } from 'react';
import { ExternalLink, RefreshCw } from 'lucide-react';
import { formatISTTime } from '../utils/formatters';
import { apiFetch } from '../utils/apiBridge';

interface Props {
  symbol: string;
}

export const NewsSection: React.FC<Props> = ({ symbol }) => {
  const [scope, setScope] = useState<'symbol' | 'market'>('market');
  const [sentimentFilter, setSentimentFilter] = useState<'ALL' | 'BULLISH' | 'BEARISH' | 'NEUTRAL'>('ALL');
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const loadNews = async (refresh = false) => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({ limit: '35' });
      if (scope === 'symbol' && symbol) qs.set('symbol', symbol);
      if (refresh) qs.set('refresh', '1');
      const res = await apiFetch(`/api/news?${qs.toString()}`);
      setData(await res.json());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!symbol && scope === 'symbol') setScope('market');
    loadNews(false);
  }, [scope, symbol]);

  const articles: any[] = (data?.articles || []).filter(
    (a: any) => sentimentFilter === 'ALL' || a.sentiment === sentimentFilter
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-xl font-bold text-slate-100">Indian Market News & Regulatory Announcements</h1>
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400 mt-1">
            <span>Sources: RBI · SEBI · Economic Times · Moneycontrol · Business Standard · CNBC-TV18</span>
            {data?.generated_at_ist && (
              <>
                <span aria-hidden="true">·</span>
                <span className="font-mono">Updated {formatISTTime(data.generated_at_ist)}</span>
              </>
            )}
          </div>
        </div>

        <button
          type="button"
          onClick={() => loadNews(true)}
          className="inline-flex items-center gap-2 px-4 py-2 text-xs font-medium bg-[#131b2e] border border-slate-700 text-slate-200 rounded hover:bg-slate-800"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh Feeds
        </button>
      </div>

      {/* Scope & Sentiment Filter */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-[#0f1626] border border-slate-800 rounded-lg p-3">
        <div className="flex items-center gap-1 p-0.5 bg-[#0a0f1c] border border-slate-700 rounded">
          <button
            type="button"
            onClick={() => setScope('market')}
            className={`px-3 py-1.5 text-xs font-medium rounded ${
              scope === 'market' ? 'bg-slate-700 text-slate-100' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            All India Markets & RBI/SEBI
          </button>
          <button
            type="button"
            disabled={!symbol}
            onClick={() => setScope('symbol')}
            className={`px-3 py-1.5 text-xs font-medium rounded disabled:opacity-40 ${
              scope === 'symbol' ? 'bg-slate-700 text-slate-100' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {symbol ? `${symbol} Specific Filings & News` : 'Select a Stock for Company News'}
          </button>
        </div>

        <div className="flex items-center gap-1 p-0.5 bg-[#0a0f1c] border border-slate-700 rounded">
          {(['ALL', 'BULLISH', 'BEARISH', 'NEUTRAL'] as const).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setSentimentFilter(s)}
              className={`px-3 py-1.5 text-xs font-mono rounded ${
                sentimentFilter === s ? 'bg-slate-700 text-slate-100 font-semibold' : 'text-slate-400'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {loading && !articles.length ? (
        <div className="p-8 text-center text-xs text-slate-400">Fetching live Indian financial & regulatory feeds...</div>
      ) : articles.length === 0 ? (
        <div className="p-8 bg-[#0f1626] border border-slate-800 rounded-lg text-center text-xs text-slate-400">
          No recent news matched the selected filter.
        </div>
      ) : (
        <div className="space-y-3">
          {articles.map((art, i) => {
            const sentColor =
              art.sentiment === 'BULLISH'
                ? 'text-emerald-400'
                : art.sentiment === 'BEARISH'
                ? 'text-rose-400'
                : 'text-slate-400';
            return (
              <div key={i} className="bg-[#0f1626] border border-slate-800 rounded-lg p-4 space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                  <div className="flex flex-wrap items-center gap-2 text-slate-400">
                    <span className="text-amber-300 font-medium">{art.event_category}</span>
                    <span aria-hidden="true">·</span>
                    <span>{art.source}</span>
                    <span aria-hidden="true">·</span>
                    <span className="font-mono">{art.published_at}</span>
                  </div>
                  <span className={`font-mono font-semibold ${sentColor}`}>{art.sentiment}</span>
                </div>

                <div className="flex items-start justify-between gap-4">
                  <h3 className="font-display text-sm font-semibold text-slate-100 leading-snug">{art.title}</h3>
                  {art.url && (
                    <a
                      href={art.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-sky-400 hover:text-sky-300 shrink-0 whitespace-nowrap"
                    >
                      Source <ExternalLink className="w-3 h-3" />
                    </a>
                  )}
                </div>

                {art.summary && <p className="text-xs text-slate-400 leading-relaxed">{art.summary}</p>}
                <div className="text-xs text-slate-300 pt-1 border-t border-slate-800/70">
                  Impact: {art.impact_explanation}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
