import React, { useEffect, useRef, useState } from 'react';
import {
  ArrowLeft,
  BarChart3,
  BookmarkPlus,
  CandlestickChart,
  Check,
  FileSpreadsheet,
  Loader2,
  Search,
  Sparkles,
  Workflow,
  X,
} from 'lucide-react';
import type { NavSection, SearchSymbolResult, SelectedStock } from '../types/trading';
import { apiFetch } from '../utils/apiBridge';

function toSelectedStock(item: SearchSymbolResult, overrideExchange?: 'NSE' | 'BSE'): SelectedStock {
  const rawEx = String(item.exchange || 'NSE').toUpperCase();
  const normalizedEx: 'NSE' | 'BSE' = overrideExchange || (rawEx.startsWith('BSE') ? 'BSE' : 'NSE');
  const displaySym =
    normalizedEx === 'BSE' && !item.nse_symbol
      ? item.bse_code || item.symbol
      : item.nse_symbol || item.symbol || item.bse_code || '';
  return {
    stock_id: item.stock_id,
    symbol: displaySym.toUpperCase(),
    companyName: item.company_name || item.name || displaySym,
    exchange: normalizedEx,
    nseSymbol: item.nse_symbol || undefined,
    bseCode: item.bse_code || undefined,
    isin: item.isin || undefined,
    sector: item.sector || undefined,
    industry: item.industry || undefined,
    capTier: item.cap_tier ?? null,
  };
}

async function queryStocksApi(query: string, exchangeFilter: 'ALL' | 'NSE' | 'BSE'): Promise<SearchSymbolResult[]> {
  const q = query.trim();
  if (!q) return [];
  const res = await apiFetch(
    `/api/symbols/search?q=${encodeURIComponent(q)}&exchange=${encodeURIComponent(exchangeFilter)}&limit=30`
  );
  if (!res.ok) {
    throw new Error(`Stock search failed (HTTP ${res.status})`);
  }
  const json = await res.json();
  if (json.error && !Array.isArray(json.results)) {
    throw new Error(json.error);
  }
  const list: SearchSymbolResult[] = Array.isArray(json.results) ? json.results : [];
  if (list.length > 0) return list;

  // Fallback direct resolution for exact BSE code, alias, or symbol
  const resResolve = await apiFetch(
    `/api/stocks/resolve/${encodeURIComponent(q)}?exchange=${exchangeFilter === 'BSE' ? 'BSE' : 'NSE'}`
  );
  if (!resResolve.ok) return [];
  const rec = await resResolve.json();
  if (rec && rec.trading_status && rec.trading_status !== 'UNVERIFIED') {
    return [
      {
        stock_id: rec.stock_id,
        symbol: rec.nse_symbol || rec.bse_code || rec.symbol || q.toUpperCase(),
        nse_symbol: rec.nse_symbol,
        bse_code: rec.bse_code,
        name: rec.company_name || rec.symbol || q.toUpperCase(),
        company_name: rec.company_name,
        series: rec.series || 'EQ',
        isin: rec.isin || '',
        exchange: rec.exchange || (exchangeFilter === 'BSE' ? 'BSE' : 'NSE'),
        sector: rec.sector || 'Indian Equities',
        industry: rec.industry || 'Indian Listed Equity',
        market_cap_cr: rec.market_cap_cr,
        cap_tier: rec.cap_tier,
        screener_url: rec.screener_url,
      },
    ];
  }
  return [];
}

interface AnalysisSelectorModalProps {
  isOpen: boolean;
  onClose: () => void;
  onStartAnalysis: (stock: SelectedStock) => void;
}

export const AnalysisStockSelectorModal: React.FC<AnalysisSelectorModalProps> = ({
  isOpen,
  onClose,
  onStartAnalysis,
}) => {
  const [query, setQuery] = useState('');
  const [exchangeFilter, setExchangeFilter] = useState<'ALL' | 'NSE' | 'BSE'>('ALL');
  const [results, setResults] = useState<SearchSymbolResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [pickedStock, setPickedStock] = useState<SelectedStock | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Reset completely on open so NO stock is ever pre-selected
  useEffect(() => {
    if (!isOpen) return;
    setQuery('');
    setExchangeFilter('ALL');
    setResults([]);
    setLoading(false);
    setError(null);
    setHasSearched(false);
    setActiveIndex(-1);
    setPickedStock(null);
    const t = setTimeout(() => inputRef.current?.focus(), 40);
    return () => clearTimeout(t);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const trimmed = query.trim();
    if (!trimmed) {
      setResults([]);
      setLoading(false);
      setError(null);
      setHasSearched(false);
      setActiveIndex(-1);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    const timer = setTimeout(async () => {
      try {
        const list = await queryStocksApi(trimmed, exchangeFilter);
        if (cancelled) return;
        setResults(list);
        setHasSearched(true);
        setActiveIndex(list.length > 0 ? 0 : -1);
      } catch (err: any) {
        if (cancelled) return;
        setResults([]);
        setHasSearched(true);
        setError(err?.message || 'Failed to search stocks');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 180);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query, exchangeFilter, isOpen]);

  const handleSelectRow = (row: SearchSymbolResult) => {
    const forcedEx: 'NSE' | 'BSE' | undefined =
      exchangeFilter === 'BSE'
        ? 'BSE'
        : exchangeFilter === 'NSE'
          ? 'NSE'
          : undefined;
    setPickedStock(toSelectedStock(row, forcedEx));
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((prev) => (results.length === 0 ? -1 : (prev + 1) % results.length));
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((prev) => (results.length === 0 ? -1 : prev <= 0 ? results.length - 1 : prev - 1));
      return;
    }
    if (e.key === 'Enter' && results.length > 0) {
      e.preventDefault();
      const target = results[activeIndex >= 0 ? activeIndex : 0];
      if (target) handleSelectRow(target);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/80 backdrop-blur-xs flex items-start justify-center pt-3 sm:pt-12 px-3 pb-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="analysis-selector-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-2xl max-h-[88dvh] bg-[#0f1626] border border-slate-700 rounded-lg shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 sm:px-5 py-3.5 border-b border-slate-800 shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <Workflow className="w-4 h-4 text-amber-400 shrink-0" />
            <h2 id="analysis-selector-title" className="font-display font-semibold text-sm sm:text-base text-slate-100 truncate">
              Select Stock for AI Analysis
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cancel selection"
            className="min-w-[40px] min-h-[40px] flex items-center justify-center rounded text-slate-400 hover:text-slate-100 hover:bg-slate-800"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Search Input & Exchange Filter */}
        <div className="p-4 border-b border-slate-800 space-y-2.5 shrink-0">
          <div className="flex items-center gap-2 bg-[#090d16] border border-slate-700 focus-within:border-amber-400 rounded-md px-3 min-h-[44px]">
            <Search className="w-4 h-4 text-slate-400 shrink-0" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Search Company name, NSE symbol, or BSE code..."
              aria-label="Search stock for AI analysis"
              className="w-full bg-transparent text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none py-2"
            />
            {loading && <Loader2 className="w-4 h-4 text-amber-400 animate-spin shrink-0" />}
            {query && (
              <button
                type="button"
                onClick={() => {
                  setQuery('');
                  setResults([]);
                  setHasSearched(false);
                  inputRef.current?.focus();
                }}
                aria-label="Clear search"
                className="p-1.5 text-slate-400 hover:text-slate-100 rounded hover:bg-slate-800"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          <div className="flex items-center justify-between gap-2 text-xs">
            <span className="text-slate-400">Matches NSE, BSE & SME equity universe</span>
            <div className="inline-flex bg-[#090d16] border border-slate-800 rounded p-0.5 shrink-0">
              {(['ALL', 'NSE', 'BSE'] as const).map((ex) => (
                <button
                  key={ex}
                  type="button"
                  onClick={() => setExchangeFilter(ex)}
                  className={`px-2.5 py-1 rounded font-mono text-[11px] ${
                    exchangeFilter === ex ? 'bg-slate-700 text-amber-300 font-semibold' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Scrollable Results List */}
        <div className="flex-1 min-h-[160px] overflow-y-auto overscroll-contain divide-y divide-slate-800/60">
          {error && (
            <div className="m-4 p-3 bg-rose-950/40 border border-rose-800 rounded text-xs text-rose-200">
              {error}
            </div>
          )}

          {!query.trim() ? (
            <div className="px-5 py-8 text-center text-xs text-slate-400 space-y-1">
              <div className="text-slate-300 font-medium">Search any listed Indian company to begin</div>
              <div>Type company name, NSE symbol, or 6-digit BSE code above.</div>
            </div>
          ) : loading && results.length === 0 ? (
            <div className="px-5 py-8 text-center text-xs text-slate-400 flex items-center justify-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin text-amber-400" />
              Searching NSE/BSE Stock Master...
            </div>
          ) : hasSearched && results.length === 0 && !error ? (
            <div className="px-5 py-8 text-center text-xs text-slate-400">
              No matching NSE/BSE company found for "{query.trim()}".
            </div>
          ) : (
            results.map((item, idx) => {
              const isSelected =
                pickedStock &&
                ((pickedStock.stock_id && item.stock_id && pickedStock.stock_id === item.stock_id) ||
                  pickedStock.symbol === (item.nse_symbol || item.bse_code || item.symbol));
              const isHighlighted = idx === activeIndex;
              return (
                <button
                  key={`${item.stock_id || item.symbol}-${idx}`}
                  type="button"
                  onClick={() => handleSelectRow(item)}
                  className={`w-full min-h-[52px] px-4 py-2.5 text-left flex items-center justify-between gap-3 transition-colors ${
                    isSelected
                      ? 'bg-amber-400/15 border-l-2 border-amber-400'
                      : isHighlighted
                        ? 'bg-slate-800/80'
                        : 'hover:bg-slate-800/50'
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="text-xs sm:text-sm font-medium text-slate-100 truncate">
                      {item.company_name || item.name}
                    </div>
                    <div className="flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-[11px] font-mono text-slate-400 mt-0.5">
                      {item.nse_symbol && <span className="text-amber-300 font-semibold">NSE: {item.nse_symbol}</span>}
                      {item.bse_code && <span className="text-sky-300">BSE: {item.bse_code}</span>}
                      {!item.nse_symbol && !item.bse_code && <span className="text-amber-300">{item.symbol}</span>}
                      {item.sector && <span className="font-sans text-slate-500">· {item.sector}</span>}
                    </div>
                  </div>
                  <div className="shrink-0 flex items-center gap-2">
                    <span className="px-2 py-0.5 text-[11px] font-mono rounded bg-[#090d16] border border-slate-700 text-slate-200">
                      {item.exchange || 'NSE'}
                    </span>
                    {isSelected && <Check className="w-4 h-4 text-amber-400" />}
                  </div>
                </button>
              );
            })
          )}
        </div>

        {/* Selected Company Confirmation Box & Footer Actions */}
        <div className="p-4 border-t border-slate-800 bg-[#0b101b] space-y-3 shrink-0">
          {pickedStock ? (
            <div className="p-3 rounded-md bg-[#090d16] border border-amber-400/40 text-xs space-y-1">
              <div className="text-slate-200">
                <span className="text-slate-400">Selected Company: </span>
                <span className="font-semibold text-slate-100">{pickedStock.companyName}</span>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2 font-mono">
                <div>
                  <span className="text-slate-400 font-sans">Symbol: </span>
                  <span className="text-amber-300 font-semibold">{pickedStock.symbol}</span>
                  {pickedStock.bseCode && (
                    <span className="text-slate-400 ml-2">(BSE: {pickedStock.bseCode})</span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <div>
                    <span className="text-slate-400 font-sans">Exchange: </span>
                    <span className="text-slate-100 font-semibold">{pickedStock.exchange}</span>
                  </div>
                  {pickedStock.nseSymbol && pickedStock.bseCode && (
                    <button
                      type="button"
                      onClick={() =>
                        setPickedStock((prev) =>
                          prev ? { ...prev, exchange: prev.exchange === 'NSE' ? 'BSE' : 'NSE' } : prev
                        )
                      }
                      className="px-2 py-0.5 text-[10px] rounded bg-slate-800 text-sky-300 hover:bg-slate-700"
                    >
                      Switch to {pickedStock.exchange === 'NSE' ? 'BSE' : 'NSE'}
                    </button>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="text-xs text-slate-400 text-center py-1">
              No company selected yet. Search and tap a company above before starting analysis.
            </div>
          )}

          <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="min-h-[44px] px-4 py-2 text-xs font-medium bg-slate-800 border border-slate-700 text-slate-200 rounded hover:bg-slate-700"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={!pickedStock}
              onClick={() => {
                if (!pickedStock) return;
                onStartAnalysis(pickedStock);
              }}
              className="min-h-[44px] inline-flex items-center justify-center gap-2 px-5 py-2 text-xs font-semibold bg-amber-400 text-slate-950 rounded hover:bg-amber-300 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Sparkles className="w-3.5 h-3.5" />
              Start AI Analysis
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

interface GlobalStockSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCompleteAiAnalysis: (stock: SelectedStock) => void;
  onSelectTabAction: (stock: SelectedStock, tab: NavSection) => void;
  onAddToWatchlist: (stock: SelectedStock) => Promise<void>;
}

export const GlobalStockSearchModal: React.FC<GlobalStockSearchModalProps> = ({
  isOpen,
  onClose,
  onCompleteAiAnalysis,
  onSelectTabAction,
  onAddToWatchlist,
}) => {
  const [query, setQuery] = useState('');
  const [exchangeFilter, setExchangeFilter] = useState<'ALL' | 'NSE' | 'BSE'>('ALL');
  const [results, setResults] = useState<SearchSymbolResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [profileStock, setProfileStock] = useState<SelectedStock | null>(null);
  const [watchlistAdded, setWatchlistAdded] = useState(false);
  const [watchlistBusy, setWatchlistBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    setQuery('');
    setExchangeFilter('ALL');
    setResults([]);
    setLoading(false);
    setError(null);
    setHasSearched(false);
    setActiveIndex(-1);
    setProfileStock(null);
    setWatchlistAdded(false);
    const t = setTimeout(() => inputRef.current?.focus(), 40);
    return () => clearTimeout(t);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const trimmed = query.trim();
    if (!trimmed) {
      setResults([]);
      setLoading(false);
      setError(null);
      setHasSearched(false);
      setActiveIndex(-1);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    const timer = setTimeout(async () => {
      try {
        const list = await queryStocksApi(trimmed, exchangeFilter);
        if (cancelled) return;
        setResults(list);
        setHasSearched(true);
        setActiveIndex(list.length > 0 ? 0 : -1);
      } catch (err: any) {
        if (cancelled) return;
        setResults([]);
        setHasSearched(true);
        setError(err?.message || 'Unable to search Stock Master');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 180);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query, exchangeFilter, isOpen]);

  const openProfile = (row: SearchSymbolResult) => {
    const forcedEx: 'NSE' | 'BSE' | undefined =
      exchangeFilter === 'BSE'
        ? 'BSE'
        : exchangeFilter === 'NSE'
          ? 'NSE'
          : undefined;
    setProfileStock(toSelectedStock(row, forcedEx));
    setWatchlistAdded(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      if (profileStock) {
        setProfileStock(null);
      } else {
        onClose();
      }
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((prev) => (results.length === 0 ? -1 : (prev + 1) % results.length));
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((prev) => (results.length === 0 ? -1 : prev <= 0 ? results.length - 1 : prev - 1));
      return;
    }
    if (e.key === 'Enter' && results.length > 0) {
      e.preventDefault();
      const target = results[activeIndex >= 0 ? activeIndex : 0];
      if (target) openProfile(target);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/80 backdrop-blur-xs flex items-start justify-center pt-3 sm:pt-12 px-3 pb-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="global-search-modal-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-2xl max-h-[88dvh] bg-[#0f1626] border border-slate-700 rounded-lg shadow-2xl flex flex-col overflow-hidden">
        {/* Modal Header */}
        <div className="flex items-center justify-between px-4 sm:px-5 py-3.5 border-b border-slate-800 shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <Search className="w-4 h-4 text-amber-400 shrink-0" />
            <h2 id="global-search-modal-title" className="font-display font-semibold text-sm sm:text-base text-slate-100 truncate">
              {profileStock ? 'Company Profile & Actions' : 'Global NSE / BSE Stock Search'}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close global stock search"
            className="min-w-[40px] min-h-[40px] flex items-center justify-center rounded text-slate-400 hover:text-slate-100 hover:bg-slate-800"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Either Company Profile Actions View OR Search & Autocomplete List */}
        {profileStock ? (
          <div className="flex-1 overflow-y-auto overscroll-contain p-4 sm:p-5 space-y-4">
            <button
              type="button"
              onClick={() => setProfileStock(null)}
              className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-100 min-h-[36px]"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              Back to Search Results
            </button>

            <div className="p-4 rounded-lg bg-[#090d16] border border-slate-800 space-y-2.5">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h3 className="font-display text-base font-bold text-slate-100">{profileStock.companyName}</h3>
                  <div className="flex flex-wrap items-center gap-2 text-xs font-mono mt-1">
                    <span className="text-amber-300 font-semibold">Symbol: {profileStock.symbol}</span>
                    {profileStock.bseCode && (
                      <>
                        <span className="text-slate-600">·</span>
                        <span className="text-sky-300">BSE: {profileStock.bseCode}</span>
                      </>
                    )}
                    <span className="text-slate-600">·</span>
                    <span className="text-slate-200">Exchange: {profileStock.exchange}</span>
                  </div>
                </div>
                {profileStock.nseSymbol && profileStock.bseCode && (
                  <button
                    type="button"
                    onClick={() =>
                      setProfileStock((prev) =>
                        prev ? { ...prev, exchange: prev.exchange === 'NSE' ? 'BSE' : 'NSE' } : prev
                      )
                    }
                    className="min-h-[36px] px-3 py-1 text-xs font-mono rounded bg-slate-800 border border-slate-700 text-sky-300 hover:bg-slate-700"
                  >
                    Switch Exchange ({profileStock.exchange})
                  </button>
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 pt-2 border-t border-slate-800 text-xs">
                <div>
                  <div className="text-slate-500">ISIN</div>
                  <div className="font-mono text-slate-200">{profileStock.isin || '—'}</div>
                </div>
                <div>
                  <div className="text-slate-500">Sector</div>
                  <div className="text-slate-200">{profileStock.sector || 'Indian Equities'}</div>
                </div>
                <div>
                  <div className="text-slate-500">Industry / Cap</div>
                  <div className="text-slate-200 truncate">
                    {profileStock.industry || 'Indian Listed Equity'}
                    {profileStock.capTier ? ` · ${profileStock.capTier}` : ''}
                  </div>
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <div className="text-xs font-medium text-slate-400">Select Action</div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                <button
                  type="button"
                  onClick={() => {
                    onClose();
                    onCompleteAiAnalysis(profileStock);
                  }}
                  className="sm:col-span-2 min-h-[48px] px-4 py-2.5 rounded-md bg-amber-400 text-slate-950 font-semibold text-xs sm:text-sm hover:bg-amber-300 flex items-center justify-center gap-2"
                >
                  <Workflow className="w-4 h-4" />
                  Complete AI Analysis
                </button>

                <button
                  type="button"
                  onClick={() => {
                    onSelectTabAction(profileStock, 'technical');
                    onClose();
                  }}
                  className="min-h-[46px] px-4 py-2.5 rounded-md bg-[#131b2e] border border-slate-700 text-slate-100 text-xs font-medium hover:bg-slate-800 flex items-center justify-center gap-2"
                >
                  <CandlestickChart className="w-4 h-4 text-sky-400" />
                  Technical Analysis
                </button>

                <button
                  type="button"
                  onClick={() => {
                    onSelectTabAction(profileStock, 'fundamental');
                    onClose();
                  }}
                  className="min-h-[46px] px-4 py-2.5 rounded-md bg-[#131b2e] border border-slate-700 text-slate-100 text-xs font-medium hover:bg-slate-800 flex items-center justify-center gap-2"
                >
                  <FileSpreadsheet className="w-4 h-4 text-emerald-400" />
                  Fundamental Analysis
                </button>

                <button
                  type="button"
                  onClick={() => {
                    onSelectTabAction(profileStock, 'screener');
                    onClose();
                  }}
                  className="min-h-[46px] px-4 py-2.5 rounded-md bg-[#131b2e] border border-slate-700 text-slate-100 text-xs font-medium hover:bg-slate-800 flex items-center justify-center gap-2"
                >
                  <BarChart3 className="w-4 h-4 text-amber-300" />
                  View Financial Results
                </button>

                <button
                  type="button"
                  disabled={watchlistBusy}
                  onClick={async () => {
                    setWatchlistBusy(true);
                    try {
                      await onAddToWatchlist(profileStock);
                      setWatchlistAdded(true);
                    } finally {
                      setWatchlistBusy(false);
                    }
                  }}
                  className={`min-h-[46px] px-4 py-2.5 rounded-md border text-xs font-medium flex items-center justify-center gap-2 ${
                    watchlistAdded
                      ? 'bg-emerald-950/50 border-emerald-700 text-emerald-300'
                      : 'bg-[#131b2e] border-slate-700 text-slate-100 hover:bg-slate-800'
                  }`}
                >
                  {watchlistAdded ? <Check className="w-4 h-4" /> : <BookmarkPlus className="w-4 h-4 text-amber-300" />}
                  {watchlistBusy ? 'Adding...' : watchlistAdded ? 'Added to Watchlist' : 'Add to Watchlist'}
                </button>
              </div>
            </div>
          </div>
        ) : (
          <>
            <div className="p-4 border-b border-slate-800 space-y-2.5 shrink-0">
              <div className="flex items-center gap-2 bg-[#090d16] border border-slate-700 focus-within:border-amber-400 rounded-md px-3 min-h-[44px]">
                <Search className="w-4 h-4 text-slate-400 shrink-0" />
                <input
                  ref={inputRef}
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Search by Company name, NSE symbol, or BSE code..."
                  aria-label="Global stock search input"
                  className="w-full bg-transparent text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none py-2"
                />
                {loading && <Loader2 className="w-4 h-4 text-amber-400 animate-spin shrink-0" />}
                {query && (
                  <button
                    type="button"
                    onClick={() => {
                      setQuery('');
                      setResults([]);
                      setHasSearched(false);
                      inputRef.current?.focus();
                    }}
                    aria-label="Clear search query"
                    className="p-1.5 text-slate-400 hover:text-slate-100 rounded hover:bg-slate-800"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>

              <div className="flex items-center justify-between gap-2 text-xs">
                <span className="text-slate-400">Use ↑↓ arrows + Enter or tap any stock</span>
                <div className="inline-flex bg-[#090d16] border border-slate-800 rounded p-0.5 shrink-0">
                  {(['ALL', 'NSE', 'BSE'] as const).map((ex) => (
                    <button
                      key={ex}
                      type="button"
                      onClick={() => setExchangeFilter(ex)}
                      className={`px-2.5 py-1 rounded font-mono text-[11px] ${
                        exchangeFilter === ex
                          ? 'bg-slate-700 text-amber-300 font-semibold'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {ex}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="flex-1 min-h-[200px] overflow-y-auto overscroll-contain divide-y divide-slate-800/60">
              {error && (
                <div className="m-4 p-3 bg-rose-950/40 border border-rose-800 rounded text-xs text-rose-200">
                  {error}
                </div>
              )}

              {!query.trim() ? (
                <div className="px-5 py-10 text-center text-xs text-slate-400 space-y-1">
                  <div className="text-slate-200 font-medium">Search All NSE & BSE Equities</div>
                  <div>Enter company name, NSE symbol, BSE scrip code, ISIN, or sector.</div>
                </div>
              ) : loading && results.length === 0 ? (
                <div className="px-5 py-10 text-center text-xs text-slate-400 flex items-center justify-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin text-amber-400" />
                  Searching Stock Master Database...
                </div>
              ) : hasSearched && results.length === 0 && !error ? (
                <div className="px-5 py-10 text-center text-xs text-slate-400">
                  No stocks found matching "{query.trim()}". Try NSE symbol, full company name, or 6-digit BSE code.
                </div>
              ) : (
                results.map((item, idx) => {
                  const isHighlighted = idx === activeIndex;
                  return (
                    <button
                      key={`${item.stock_id || item.symbol}-${idx}`}
                      type="button"
                      onClick={() => openProfile(item)}
                      className={`w-full min-h-[54px] px-4 py-2.5 text-left flex items-center justify-between gap-3 transition-colors ${
                        isHighlighted ? 'bg-slate-800/80' : 'hover:bg-slate-800/50'
                      }`}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="text-xs sm:text-sm font-medium text-slate-100 truncate">
                          {item.company_name || item.name}
                        </div>
                        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-[11px] font-mono text-slate-400 mt-0.5">
                          {item.nse_symbol && <span className="text-amber-300 font-semibold">NSE: {item.nse_symbol}</span>}
                          {item.bse_code && <span className="text-sky-300">BSE: {item.bse_code}</span>}
                          {!item.nse_symbol && !item.bse_code && <span className="text-amber-300">{item.symbol}</span>}
                          {item.isin && <span className="text-slate-500">· {item.isin}</span>}
                          {item.sector && <span className="font-sans text-slate-500">· {item.sector}</span>}
                        </div>
                      </div>
                      <div className="shrink-0 text-right">
                        <span className="px-2 py-0.5 text-[11px] font-mono rounded bg-[#090d16] border border-slate-700 text-slate-200">
                          {item.exchange || 'NSE'}
                        </span>
                        {item.cap_tier && <div className="text-[10px] text-slate-500 mt-0.5">{item.cap_tier}</div>}
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};
