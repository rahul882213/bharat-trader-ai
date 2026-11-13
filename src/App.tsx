import React, { useEffect, useState } from 'react';
import {
  Activity,
  BarChart3,
  Bell,
  Briefcase,
  CandlestickChart,
  Database,
  FileSpreadsheet,
  Globe,
  Newspaper,
  Radar,
  Search,
  Trash2,
  Workflow,
  X,
} from 'lucide-react';
import type { NavSection, SelectedStock, WatchlistItem } from './types/trading';
import { OverviewSection } from './components/OverviewSection';
import { ScannerSection } from './components/ScannerSection';
import { ScreenerSection } from './components/ScreenerSection';
import { TechnicalSection } from './components/TechnicalSection';
import { FundamentalSection } from './components/FundamentalSection';
import { NewsSection } from './components/NewsSection';
import { BacktestSection } from './components/BacktestSection';
import { PortfolioRiskSection } from './components/PortfolioRiskSection';
import { AlertsSettingsSection } from './components/AlertsSettingsSection';
import { AnalysisStockSelectorModal, GlobalStockSearchModal } from './components/StockModals';
import { formatINR, formatISTTime } from './utils/formatters';
import {
  apiFetch,
  BackendHealthStatus,
  checkBackendHealth,
  getBackendBaseUrl,
  setBackendBaseUrl,
} from './utils/apiBridge';

const NAV_ITEMS: { id: NavSection; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: 'overview', label: 'Market Overview', icon: Activity },
  { id: 'scanner', label: 'Scanner & AI Rankings', icon: Radar },
  { id: 'screener', label: 'Screener.in Data Center', icon: Database },
  { id: 'technical', label: 'Analyse Any Stock (Tech)', icon: CandlestickChart },
  { id: 'fundamental', label: 'Fundamental Analysis', icon: FileSpreadsheet },
  { id: 'news', label: 'News & Filings', icon: Newspaper },
  { id: 'backtest', label: 'Backtesting Engine', icon: BarChart3 },
  { id: 'portfolio', label: 'Portfolio Analysis & Risk', icon: Briefcase },
  { id: 'alerts', label: 'Alerts & Settings', icon: Bell },
];

export default function App() {
  const [activeNav, setActiveNav] = useState<NavSection>('overview');
  const [scannerInitialMode, setScannerInitialMode] = useState<'technical' | 'market_wide'>('technical');

  // Dynamic Selected Stock State (ZERO hardcoded HAL / RELIANCE / TCS defaults)
  const [selectedStock, setSelectedStock] = useState<SelectedStock | null>(null);

  // Modals: Global Stock Search & Pre-Analysis Stock Selector
  const [globalSearchOpen, setGlobalSearchOpen] = useState(false);
  const [analysisSelectorOpen, setAnalysisSelectorOpen] = useState(false);

  // Dynamic Watchlist loaded from backend /api/watchlist
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [watchlistLoading, setWatchlistLoading] = useState(true);

  // Dynamic 12-Step Workflow Modal
  const [workflowOpen, setWorkflowOpen] = useState(false);
  const [workflowLoading, setWorkflowLoading] = useState(false);
  const [workflowData, setWorkflowData] = useState<any>(null);
  const [workflowError, setWorkflowError] = useState<string | null>(null);
  const [analysisTargetStock, setAnalysisTargetStock] = useState<SelectedStock | null>(null);

  // Backend Connectivity & Cloud Health State
  const [health, setHealth] = useState<BackendHealthStatus>({
    checked: false,
    connected: false,
    backendUrl: getBackendBaseUrl(),
  });
  const [backendUrlInput, setBackendUrlInput] = useState<string>(() => getBackendBaseUrl());
  const [showUrlEditor, setShowUrlEditor] = useState(false);

  const refreshHealth = async () => {
    const status = await checkBackendHealth();
    setHealth(status);
  };

  const loadWatchlist = async () => {
    setWatchlistLoading(true);
    try {
      const res = await apiFetch('/api/watchlist');
      const json = await res.json();
      setWatchlist(Array.isArray(json.watchlist) ? json.watchlist : []);
    } catch {
      setWatchlist([]);
    } finally {
      setWatchlistLoading(false);
    }
  };

  useEffect(() => {
    refreshHealth();
    loadWatchlist();
  }, []);

  // Lock background page scroll while any modal is open (critical for mobile browsers)
  useEffect(() => {
    const anyModalOpen = globalSearchOpen || analysisSelectorOpen || workflowOpen;
    document.body.style.overflow = anyModalOpen ? 'hidden' : '';
    return () => {
      document.body.style.overflow = '';
    };
  }, [globalSearchOpen, analysisSelectorOpen, workflowOpen]);

  const handleSelectStockObject = (stock: SelectedStock, targetTab: NavSection = 'technical') => {
    setSelectedStock(stock);
    setActiveNav(targetTab);
  };

  const handleSelectSymbol = async (
    sym: string,
    targetTab: NavSection = 'technical',
    companyName?: string,
    explicitExchange: 'NSE' | 'BSE' = 'NSE'
  ) => {
    const clean = sym.trim().toUpperCase();
    setSelectedStock({
      symbol: clean,
      companyName: companyName || clean,
      exchange: explicitExchange,
    });
    setActiveNav(targetTab);
    try {
      const res = await apiFetch(`/api/stocks/resolve/${encodeURIComponent(clean)}?exchange=${explicitExchange}`);
      const rec = await res.json();
      if (rec) {
        const resolvedSym = (rec.nse_symbol || rec.bse_code || clean).toUpperCase();
        const resolvedEx: 'NSE' | 'BSE' =
          explicitExchange === 'BSE' || String(rec.exchange || '').toUpperCase().startsWith('BSE') ? 'BSE' : 'NSE';
        setSelectedStock({
          stock_id: rec.stock_id,
          symbol: resolvedSym,
          companyName: rec.company_name || companyName || resolvedSym,
          exchange: resolvedEx,
          nseSymbol: rec.nse_symbol,
          bseCode: rec.bse_code,
          isin: rec.isin,
          sector: rec.sector,
          industry: rec.industry,
          capTier: rec.cap_tier ?? null,
        });
      }
    } catch {
      // Retain optimistic object if resolution fails
    }
  };

  const handleAddToWatchlist = async (stock: SelectedStock) => {
    const res = await apiFetch('/api/watchlist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        symbol: stock.symbol,
        exchange: stock.exchange,
        sector: stock.sector || 'Indian Equities',
        company_name: stock.companyName,
      }),
    });
    const json = await res.json();
    if (Array.isArray(json.watchlist)) {
      setWatchlist(json.watchlist);
    } else {
      await loadWatchlist();
    }
  };

  const handleRemoveFromWatchlist = async (sym: string, exch: 'NSE' | 'BSE') => {
    try {
      const res = await apiFetch(`/api/watchlist/${encodeURIComponent(sym)}?exchange=${exch}`, {
        method: 'DELETE',
      });
      const json = await res.json();
      if (Array.isArray(json.watchlist)) {
        setWatchlist(json.watchlist);
      } else {
        await loadWatchlist();
      }
    } catch {
      // Ignore error
    }
  };

  // Reusable dynamic 12-Step AI Analysis runner accepting { symbol, exchange, companyName }
  const runAnalysis = async (target: SelectedStock) => {
    setAnalysisSelectorOpen(false);
    setSelectedStock(target);
    setAnalysisTargetStock(target);
    setWorkflowData(null);
    setWorkflowError(null);
    setWorkflowOpen(true);
    setWorkflowLoading(true);
    try {
      const res = await apiFetch('/api/workflow/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: target.symbol,
          exchange: target.exchange,
          company_name: target.companyName,
          analysis_type: 'full',
          timeframe: '1d',
        }),
      });
      const json = await res.json();
      if (!json.available) {
        throw new Error(json.error || `Workflow execution failed for ${target.symbol}`);
      }
      setWorkflowData(json);
    } catch (e: any) {
      setWorkflowError(e.message || `AI Analysis failed for ${target.symbol}`);
    } finally {
      setWorkflowLoading(false);
    }
  };

  const openMarketWideScan = () => {
    setScannerInitialMode('market_wide');
    setActiveNav('scanner');
  };

  const renderEmptyStockPrompt = (featureName: string) => (
    <div className="bg-[#0f1626] border border-slate-800 rounded-lg p-6 sm:p-8 text-center space-y-4 max-w-xl mx-auto mt-6">
      <div className="w-10 h-10 rounded-full bg-amber-400/10 border border-amber-400/30 text-amber-300 flex items-center justify-center mx-auto">
        <Search className="w-5 h-5" />
      </div>
      <div className="space-y-1">
        <h2 className="font-display text-base font-bold text-slate-100">No Stock Selected for {featureName}</h2>
        <p className="text-xs text-slate-400">
          Search and select any NSE or BSE listed company by company name, NSE symbol, or BSE code.
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-2.5">
        <button
          type="button"
          onClick={() => setGlobalSearchOpen(true)}
          className="min-h-[44px] inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold bg-amber-400 text-slate-950 rounded hover:bg-amber-300"
        >
          <Search className="w-3.5 h-3.5" />
          Search & Select Stock
        </button>
        <button
          type="button"
          onClick={() => setAnalysisSelectorOpen(true)}
          className="min-h-[44px] inline-flex items-center gap-2 px-4 py-2 text-xs font-medium bg-[#131b2e] border border-slate-700 text-slate-200 rounded hover:bg-slate-800"
        >
          <Workflow className="w-3.5 h-3.5 text-amber-400" />
          Run AI Analysis
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-[#090d16] text-slate-200 flex flex-col">
      {/* Top Bar: Brand + Clickable Search Button — Search Trigger Bar — Selected Stock + Run AI Analysis */}
      <header className="sticky top-0 z-30 h-14 px-3 sm:px-4 md:px-5 border-b border-slate-800 bg-[#0b101b]/95 backdrop-blur flex items-center justify-between gap-2 sm:gap-4">
        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={() => setActiveNav('overview')}
            className="font-display text-sm sm:text-base font-bold tracking-tight text-slate-100 whitespace-nowrap"
          >
            Bharat Trader AI
          </button>
          <button
            type="button"
            onClick={() => setGlobalSearchOpen(true)}
            aria-label="Search NSE/BSE stocks"
            data-testid="header-search-button"
            className="min-w-[40px] min-h-[40px] flex items-center justify-center rounded-md bg-[#0f1626] border border-slate-700/80 text-slate-300 hover:text-amber-300 hover:border-amber-400/60 transition-colors shrink-0"
          >
            <Search className="w-4 h-4" />
          </button>
        </div>

        <button
          type="button"
          onClick={() => setGlobalSearchOpen(true)}
          className="hidden sm:flex flex-1 max-w-lg items-center gap-2 bg-[#0f1626] border border-slate-700/80 hover:border-slate-500 rounded px-3 min-h-[38px] text-left transition-colors"
        >
          <Search className="w-3.5 h-3.5 text-slate-400 shrink-0" />
          <span className="text-xs text-slate-400 truncate">
            Search any Indian company by name, NSE symbol, or BSE code...
          </span>
        </button>

        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={() => setGlobalSearchOpen(true)}
            className="hidden lg:flex flex-col text-right pr-2.5 border-r border-slate-800 hover:opacity-85 transition-opacity"
          >
            <span className="text-[10px] text-slate-400 uppercase tracking-wider">Selected Stock</span>
            <span
              className="text-xs font-mono font-semibold text-slate-100 max-w-[190px] truncate"
              title={selectedStock ? `${selectedStock.symbol} · ${selectedStock.companyName}` : 'No Stock Selected'}
            >
              {selectedStock
                ? `${selectedStock.symbol} (${selectedStock.exchange}) · ${selectedStock.companyName}`
                : 'No Stock Selected'}
            </span>
          </button>

          <button
            type="button"
            onClick={openMarketWideScan}
            className="hidden sm:inline-flex items-center gap-1.5 px-3 min-h-[38px] text-xs font-medium bg-[#131b2e] border border-slate-700 text-slate-200 rounded hover:bg-slate-800 whitespace-nowrap"
          >
            <Globe className="w-3.5 h-3.5 text-sky-400" />
            Scan Entire Market
          </button>

          <button
            type="button"
            onClick={() => setAnalysisSelectorOpen(true)}
            data-testid="run-ai-analysis-button"
            className="inline-flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 min-h-[40px] text-xs font-semibold bg-amber-400 text-slate-950 rounded hover:bg-amber-300 whitespace-nowrap"
          >
            <Workflow className="w-3.5 h-3.5" />
            Run AI Analysis
          </button>
        </div>
      </header>

      {/* Automated Backend Connectivity, Database & Provider Status Bar */}
      <div
        className={`px-4 md:px-5 py-2 border-b text-[11px] flex flex-wrap items-center justify-between gap-3 ${
          !health.checked
            ? 'bg-[#0d1424] border-slate-800 text-slate-400'
            : health.connected
              ? 'bg-[#0b1523] border-slate-800/90 text-slate-300'
              : 'bg-[#1a1118] border-rose-500/40 text-rose-200'
        }`}
      >
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <div className="inline-flex items-center gap-1.5 font-semibold">
            <span
              className={`w-2 h-2 rounded-full ${
                !health.checked
                  ? 'bg-slate-500 animate-pulse'
                  : health.connected
                    ? 'bg-emerald-400'
                    : 'bg-rose-500'
              }`}
            />
            <span>
              Backend:{' '}
              {!health.checked ? 'Checking...' : health.connected ? 'Connected' : 'Disconnected'}
            </span>
          </div>

          <span className="font-mono text-slate-400">
            URL:{' '}
            <span className="text-slate-200">
              {health.backendUrl || 'Not configured (VITE_API_BASE_URL)'}
            </span>
          </span>

          <span className="text-slate-400">
            DB:{' '}
            <span className={health.database?.connected ? 'text-emerald-300' : 'text-rose-300'}>
              {health.database?.connected
                ? `Connected (${health.database.dialect || 'sql'})`
                : 'Disconnected'}
            </span>
          </span>

          {health.dataProviders && Object.keys(health.dataProviders).length > 0 && (
            <span className="text-slate-400">
              Providers:{' '}
              <span className="text-slate-200">
                {Object.entries(health.dataProviders)
                  .map(([k, v]) => `${k.replace('_', ' ')}: ${v.available ? 'OK' : 'Off'}`)
                  .join(' · ')}
              </span>
            </span>
          )}

          <span className="text-slate-400 font-mono">
            Last Update:{' '}
            <span className="text-slate-200">
              {health.lastUpdated ? formatISTTime(health.lastUpdated) : 'Unavailable'}
            </span>
          </span>
        </div>

        <div className="flex items-center gap-2">
          {!health.connected && health.checked && health.error && (
            <span className="text-rose-300 max-w-md truncate" title={health.error}>
              {health.error}
            </span>
          )}
          <button
            type="button"
            onClick={() => setShowUrlEditor((v) => !v)}
            className="px-2.5 py-1 bg-slate-800/80 border border-slate-700 rounded text-[11px] text-slate-200 hover:bg-slate-700"
          >
            {showUrlEditor ? 'Hide API Config' : 'Configure HTTPS API'}
          </button>
          <button
            type="button"
            onClick={refreshHealth}
            className="px-2.5 py-1 bg-slate-800/80 border border-slate-700 rounded text-[11px] text-slate-200 hover:bg-slate-700"
          >
            Recheck
          </button>
        </div>

        {showUrlEditor && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setBackendBaseUrl(backendUrlInput);
              window.location.reload();
            }}
            className="w-full pt-1.5 border-t border-slate-800/80 flex flex-wrap items-center gap-2"
          >
            <span className="text-slate-400">Deployed HTTPS Backend URL:</span>
            <input
              type="url"
              value={backendUrlInput}
              onChange={(e) => setBackendUrlInput(e.target.value)}
              placeholder="https://your-service.onrender.com"
              className="flex-1 min-w-[240px] max-w-md bg-[#090d16] border border-slate-700 rounded px-2.5 py-1 text-xs font-mono text-slate-100 focus:outline-none focus:border-amber-400"
            />
            <button
              type="submit"
              className="px-3 py-1 bg-amber-400 text-slate-950 font-semibold rounded hover:bg-amber-300"
            >
              Connect HTTPS Backend
            </button>
            {getBackendBaseUrl() && (
              <button
                type="button"
                onClick={() => {
                  setBackendUrlInput('');
                  setBackendBaseUrl('');
                  window.location.reload();
                }}
                className="px-2.5 py-1 bg-slate-800 text-slate-300 rounded hover:bg-slate-700"
              >
                Reset
              </button>
            )}
          </form>
        )}
      </div>

      <div className="flex flex-1 min-h-0">
        {/* Left Institutional Sidebar */}
        <aside className="hidden md:flex w-60 shrink-0 flex-col border-r border-slate-800 bg-[#0b101b] p-3 justify-between">
          <div className="space-y-6">
            <nav className="space-y-1">
              {NAV_ITEMS.map((item) => {
                const Icon = item.icon;
                const active = activeNav === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      if (item.id === 'scanner') setScannerInitialMode('technical');
                      setActiveNav(item.id);
                    }}
                    className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-md text-xs font-medium transition-colors whitespace-nowrap ${
                      active
                        ? 'bg-slate-800 text-slate-100'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/40'
                    }`}
                  >
                    <Icon className="w-4 h-4 shrink-0" />
                    <span className="truncate">{item.label}</span>
                  </button>
                );
              })}
            </nav>

            <div className="pt-4 border-t border-slate-800">
              <div className="px-3 flex items-center justify-between mb-2">
                <span className="text-[11px] font-medium text-slate-500">Watchlist</span>
                <button
                  type="button"
                  onClick={() => setGlobalSearchOpen(true)}
                  className="text-[11px] text-amber-300 hover:text-amber-200"
                >
                  + Add
                </button>
              </div>
              {watchlistLoading ? (
                <div className="px-3 py-2 text-[11px] text-slate-500">Loading watchlist...</div>
              ) : watchlist.length === 0 ? (
                <div className="px-3 py-2 text-[11px] text-slate-500">
                  No stocks in watchlist. Use Search to add any NSE/BSE stock.
                </div>
              ) : (
                <div className="space-y-0.5 max-h-60 overflow-y-auto">
                  {watchlist.map((w) => {
                    const ex = (w.exchange || 'NSE') as 'NSE' | 'BSE';
                    const isCurrent = selectedStock?.symbol === w.symbol && selectedStock?.exchange === ex;
                    return (
                      <div
                        key={`${w.symbol}-${ex}`}
                        className={`group flex items-center justify-between rounded px-2 py-1 text-xs font-mono transition-colors ${
                          isCurrent
                            ? 'bg-amber-400/10 text-amber-300 font-semibold'
                            : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/40'
                        }`}
                      >
                        <button
                          type="button"
                          onClick={() =>
                            handleSelectSymbol(
                              w.symbol,
                              activeNav === 'overview' ? 'technical' : activeNav,
                              w.company_name,
                              ex
                            )
                          }
                          className="flex-1 flex items-center justify-between text-left px-1 py-0.5 min-w-0"
                        >
                          <span className="truncate">{w.symbol}</span>
                          <span className="text-[10px] text-slate-500 ml-2">{ex}</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => handleRemoveFromWatchlist(w.symbol, ex)}
                          aria-label={`Remove ${w.symbol} from watchlist`}
                          className="p-1 text-slate-600 hover:text-rose-400 opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          <div className="p-3 bg-[#0f1626] border border-slate-800 rounded text-[11px] text-slate-400 space-y-1">
            <div className="text-slate-200 font-semibold">Decision-Support Desk</div>
            <div>Paper Trading Enabled · IST</div>
            <div>Analytical tool only, not investment advice.</div>
          </div>
        </aside>

        {/* Mobile Nav Bar */}
        <div className="md:hidden fixed bottom-0 left-0 right-0 z-30 bg-[#0b101b] border-t border-slate-800 flex overflow-x-auto px-2 py-1.5 gap-1">
          {NAV_ITEMS.map((item) => {
            const active = activeNav === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setActiveNav(item.id)}
                className={`px-3 py-1.5 rounded text-xs whitespace-nowrap shrink-0 ${
                  active ? 'bg-slate-800 text-slate-100 font-semibold' : 'text-slate-400'
                }`}
              >
                {item.label}
              </button>
            );
          })}
        </div>

        {/* Main Viewport */}
        <main className="flex-1 min-w-0 p-4 sm:p-5 md:p-7 pb-20 md:pb-8 overflow-y-auto">
          {activeNav === 'overview' && <OverviewSection onSelectSymbol={(s) => handleSelectSymbol(s, 'technical')} />}
          {activeNav === 'scanner' && (
            <ScannerSection
              initialMode={scannerInitialMode}
              onSelectSymbol={(s) => handleSelectSymbol(s, 'technical')}
            />
          )}
          {activeNav === 'screener' && (
            <ScreenerSection
              symbol={selectedStock?.symbol || ''}
              onSelectSymbol={(s, tab) => handleSelectSymbol(s, tab || 'screener')}
            />
          )}
          {activeNav === 'technical' &&
            (selectedStock ? (
              <TechnicalSection
                symbol={selectedStock.symbol}
                exchange={selectedStock.exchange}
                onChangeExchange={(ex) =>
                  setSelectedStock((prev) => (prev ? { ...prev, exchange: ex } : prev))
                }
              />
            ) : (
              renderEmptyStockPrompt('Technical Analysis')
            ))}
          {activeNav === 'fundamental' &&
            (selectedStock ? (
              <FundamentalSection
                symbol={selectedStock.symbol}
                exchange={selectedStock.exchange}
                onOpenScreener={() => setActiveNav('screener')}
              />
            ) : (
              renderEmptyStockPrompt('Fundamental Analysis')
            ))}
          {activeNav === 'news' && <NewsSection symbol={selectedStock?.symbol || ''} />}
          {activeNav === 'backtest' &&
            (selectedStock ? (
              <BacktestSection symbol={selectedStock.symbol} />
            ) : (
              renderEmptyStockPrompt('Historical Backtesting')
            ))}
          {activeNav === 'portfolio' && <PortfolioRiskSection />}
          {activeNav === 'alerts' && <AlertsSettingsSection symbol={selectedStock?.symbol || ''} />}
        </main>
      </div>

      {/* Modal 1: Select Stock for AI Analysis (Opens on "Run AI Analysis" click; NO stock pre-selected) */}
      <AnalysisStockSelectorModal
        isOpen={analysisSelectorOpen}
        onClose={() => setAnalysisSelectorOpen(false)}
        onStartAnalysis={runAnalysis}
      />

      {/* Modal 2: Global Stock Search Modal (Opens on Search icon button / Search bar click) */}
      <GlobalStockSearchModal
        isOpen={globalSearchOpen}
        onClose={() => setGlobalSearchOpen(false)}
        onCompleteAiAnalysis={runAnalysis}
        onSelectTabAction={handleSelectStockObject}
        onAddToWatchlist={handleAddToWatchlist}
      />

      {/* Modal 3: Dynamic 12-Step AI Analysis Result Modal */}
      {workflowOpen && analysisTargetStock && (
        <div
          className="fixed inset-0 z-50 flex items-start sm:items-center justify-center bg-black/80 backdrop-blur-xs pt-3 sm:pt-4 px-3 pb-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="workflow-result-title"
          onClick={(e) => {
            if (e.target === e.currentTarget) setWorkflowOpen(false);
          }}
        >
          <div className="w-full max-w-3xl max-h-[88dvh] bg-[#0f1626] border border-slate-700 rounded-lg flex flex-col overflow-hidden shadow-2xl">
            <div className="flex items-center justify-between px-4 sm:px-5 py-3.5 border-b border-slate-800 shrink-0">
              <div id="workflow-result-title" className="font-display font-semibold text-sm text-slate-100 truncate pr-2">
                12-Step AI Analysis — {analysisTargetStock.companyName} ({analysisTargetStock.symbol} · {analysisTargetStock.exchange})
              </div>
              <button
                type="button"
                onClick={() => setWorkflowOpen(false)}
                aria-label="Close AI analysis results"
                className="min-w-[40px] min-h-[40px] flex items-center justify-center rounded text-slate-400 hover:text-slate-100 hover:bg-slate-800 shrink-0"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-4 sm:p-5 overflow-y-auto overscroll-contain space-y-4 text-xs">
              {workflowLoading ? (
                <div className="py-12 text-center text-slate-400">
                  Executing Stock Resolution → Screener & Market Fundamentals → News → Technicals → Entry → Exit → Backtest → Risk Gate for{' '}
                  <span className="text-amber-300 font-mono font-semibold">{analysisTargetStock.symbol}</span>...
                </div>
              ) : workflowError ? (
                <div className="p-4 bg-rose-950/40 border border-rose-800 rounded text-rose-200">{workflowError}</div>
              ) : workflowData ? (
                <>
                  <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                    <span className="font-mono text-slate-200">{workflowData.stock_meta?.company_name}</span>
                    {workflowData.stock_meta?.isin && (
                      <>
                        <span>·</span>
                        <span className="font-mono">ISIN {workflowData.stock_meta.isin}</span>
                      </>
                    )}
                    {workflowData.stock_meta?.bse_code && (
                      <>
                        <span>·</span>
                        <span className="font-mono">BSE {workflowData.stock_meta.bse_code}</span>
                      </>
                    )}
                    <span>·</span>
                    <span>{workflowData.stock_meta?.sector}</span>
                    {workflowData.stock_meta?.cap_tier && (
                      <>
                        <span>·</span>
                        <span>{workflowData.stock_meta.cap_tier}</span>
                      </>
                    )}
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono">
                    <div className="p-3 bg-[#0a0f1c] border border-slate-800 rounded">
                      <div className="text-slate-400 font-sans">Entry Status</div>
                      <div className="text-amber-300 font-semibold mt-0.5">
                        {workflowData.trade_plan?.entry?.status}
                      </div>
                    </div>
                    <div className="p-3 bg-[#0a0f1c] border border-slate-800 rounded">
                      <div className="text-slate-400 font-sans">Entry / Stop-Loss</div>
                      <div className="text-slate-100 mt-0.5">
                        {formatINR(workflowData.trade_plan?.exit?.entry_price)} /{' '}
                        {formatINR(workflowData.trade_plan?.exit?.initial_stop_loss)}
                      </div>
                    </div>
                    <div className="p-3 bg-[#0a0f1c] border border-slate-800 rounded">
                      <div className="text-slate-400 font-sans">Position Size</div>
                      <div className="text-slate-100 mt-0.5">
                        {workflowData.trade_plan?.position_sizing?.quantity ?? 0} shares
                      </div>
                    </div>
                    <div className="p-3 bg-[#0a0f1c] border border-slate-800 rounded">
                      <div className="text-slate-400 font-sans">Risk Verdict</div>
                      <div
                        className={`font-semibold mt-0.5 ${
                          workflowData.trade_plan?.risk_check?.verdict === 'PASS'
                            ? 'text-emerald-400'
                            : 'text-rose-400'
                        }`}
                      >
                        {workflowData.trade_plan?.risk_check?.verdict}
                      </div>
                    </div>
                  </div>

                  {workflowData.analysis?.fundamental?.scores && (
                    <div className="p-4 bg-[#0a0f1c] border border-slate-800 rounded space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-slate-200">AI Fundamental Scores</span>
                        <span className="font-mono text-amber-300">
                          Composite {workflowData.analysis.fundamental.scores.composite_score}/100
                        </span>
                      </div>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 font-mono text-[11px]">
                        <div>Quality: {workflowData.analysis.fundamental.scores.business_quality?.score}/100</div>
                        <div>Strength: {workflowData.analysis.fundamental.scores.financial_strength?.score}/100</div>
                        <div>Growth: {workflowData.analysis.fundamental.scores.growth?.score}/100</div>
                        <div>Valuation: {workflowData.analysis.fundamental.scores.valuation?.score}/100</div>
                      </div>
                      <p className="text-slate-300 leading-relaxed">
                        {workflowData.analysis.fundamental.final_assessment}
                      </p>
                    </div>
                  )}

                  <div className="p-4 bg-[#0a0f1c] border border-slate-800 rounded space-y-2">
                    <div className="font-semibold text-slate-200">Technical & Trade Pipeline Summary</div>
                    <div className="text-slate-300">{workflowData.trade_plan?.entry?.summary}</div>
                    <div className="text-slate-400">
                      News Sentiment: {workflowData.analysis?.news?.overall_sentiment} (
                      {workflowData.analysis?.news?.counts?.total ?? 0} stories) · Backtest Win Rate:{' '}
                      {workflowData.trade_plan?.backtest_summary?.win_rate_pct ?? 0}% · Monte Carlo Profit Prob:{' '}
                      {workflowData.trade_plan?.backtest_summary?.monte_carlo_prob_profit_pct ?? 0}%
                    </div>
                    {workflowData.trade_plan?.risk_check?.violations?.length > 0 && (
                      <div className="text-rose-400">
                        Risk Violations: {workflowData.trade_plan.risk_check.violations.join(' ')}
                      </div>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-400">
                    <span>Persisted in central SQLite/PostgreSQL DB + trader/analysis.json & trader/trade_plan.json.</span>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setWorkflowOpen(false);
                          setActiveNav('fundamental');
                        }}
                        className="min-h-[38px] px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded"
                      >
                        Open Fundamental Report
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setWorkflowOpen(false);
                          setActiveNav('technical');
                        }}
                        className="min-h-[38px] px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded"
                      >
                        Open Chart & Order Ticket
                      </button>
                    </div>
                  </div>
                </>
              ) : null}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
