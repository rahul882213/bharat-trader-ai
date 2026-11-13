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
  Workflow,
  X,
} from 'lucide-react';
import type { NavSection, SearchSymbolResult } from './types/trading';
import { OverviewSection } from './components/OverviewSection';
import { ScannerSection } from './components/ScannerSection';
import { ScreenerSection } from './components/ScreenerSection';
import { TechnicalSection } from './components/TechnicalSection';
import { FundamentalSection } from './components/FundamentalSection';
import { NewsSection } from './components/NewsSection';
import { BacktestSection } from './components/BacktestSection';
import { PortfolioRiskSection } from './components/PortfolioRiskSection';
import { AlertsSettingsSection } from './components/AlertsSettingsSection';
import { formatINR, formatISTTime } from './utils/formatters';
import {
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

const QUICK_WATCHLIST = ['HAL', 'MAZDOCK', 'ORIANA', 'HBLENGINE', 'TCS', 'HDFCBANK', 'RELIANCE', 'HINDCOPPER'];

export default function App() {
  const [activeNav, setActiveNav] = useState<NavSection>('overview');
  const [scannerInitialMode, setScannerInitialMode] = useState<'technical' | 'market_wide'>('technical');
  const [selectedSymbol, setSelectedSymbol] = useState<string>('HAL');
  const [selectedCompanyName, setSelectedCompanyName] = useState<string>('Hindustan Aeronautics Limited');
  const [exchange, setExchange] = useState<'NSE' | 'BSE'>('NSE');

  // Global Universal Stock Search
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchSymbolResult[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);

  // Dynamic 12-Step Workflow Modal
  const [workflowOpen, setWorkflowOpen] = useState(false);
  const [workflowLoading, setWorkflowLoading] = useState(false);
  const [workflowData, setWorkflowData] = useState<any>(null);
  const [workflowError, setWorkflowError] = useState<string | null>(null);

  // Backend Connectivity & Cloud Health State (Requirement #8)
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

  useEffect(() => {
    refreshHealth();
  }, []);

  // Sync canonical metadata whenever selectedSymbol changes
  useEffect(() => {
    let active = true;
    fetch(`/api/stocks/resolve/${encodeURIComponent(selectedSymbol)}?exchange=${exchange}`)
      .then((r) => r.json())
      .then((rec) => {
        if (!active || !rec) return;
        if (rec.company_name) setSelectedCompanyName(rec.company_name);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [selectedSymbol, exchange]);

  useEffect(() => {
    const q = searchQuery.trim();
    if (!q) {
      setSearchResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/symbols/search?q=${encodeURIComponent(q)}&limit=25`);
        const json = await res.json();
        setSearchResults(json.results || []);
        setSearchOpen(true);
      } catch {
        setSearchResults([]);
      }
    }, 200);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const handleSelectSymbol = (sym: string, targetTab: NavSection = 'technical', companyName?: string) => {
    setSelectedSymbol(sym.toUpperCase());
    if (companyName) setSelectedCompanyName(companyName);
    setActiveNav(targetTab);
    setSearchOpen(false);
    setSearchQuery('');
  };

  const handleSearchSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = searchQuery.trim();
    if (!q) return;
    if (searchResults.length > 0) {
      const top = searchResults[0];
      handleSelectSymbol(top.symbol, activeNav === 'overview' ? 'technical' : activeNav, top.name);
      return;
    }
    try {
      const res = await fetch(`/api/stocks/resolve/${encodeURIComponent(q)}`);
      const rec = await res.json();
      const sym = rec.nse_symbol || rec.bse_code || q.toUpperCase();
      handleSelectSymbol(sym, activeNav === 'overview' ? 'technical' : activeNav, rec.company_name);
    } catch {
      handleSelectSymbol(q.toUpperCase());
    }
  };

  const runAiAnalysis = async () => {
    setWorkflowOpen(true);
    setWorkflowLoading(true);
    setWorkflowError(null);
    try {
      const res = await fetch('/api/workflow/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: selectedSymbol, exchange, analysis_type: 'full', timeframe: '1d' }),
      });
      const json = await res.json();
      if (!json.available) throw new Error(json.error || `Workflow execution failed for ${selectedSymbol}`);
      setWorkflowData(json);
    } catch (e: any) {
      setWorkflowError(e.message || 'AI Analysis failed');
    } finally {
      setWorkflowLoading(false);
    }
  };

  const openMarketWideScan = () => {
    setScannerInitialMode('market_wide');
    setActiveNav('scanner');
  };

  return (
    <div className="min-h-screen bg-[#090d16] text-slate-200 flex flex-col">
      {/* Top Bar: Brand — Global Universal Stock Search — Selected Stock + Run AI Analysis & Market-Wide Scan */}
      <header className="sticky top-0 z-30 h-14 px-4 md:px-5 border-b border-slate-800 bg-[#0b101b]/95 backdrop-blur flex items-center justify-between gap-4">
        <button
          type="button"
          onClick={() => setActiveNav('overview')}
          className="font-display text-base font-bold tracking-tight text-slate-100 whitespace-nowrap shrink-0"
        >
          Bharat Trader AI
        </button>

        <form onSubmit={handleSearchSubmit} className="relative flex-1 max-w-lg">
          <div className="flex items-center bg-[#0f1626] border border-slate-700/80 rounded px-3 py-1.5">
            <Search className="w-3.5 h-3.5 text-slate-400 mr-2 shrink-0" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onFocus={() => searchResults.length && setSearchOpen(true)}
              placeholder="Search Company, NSE, BSE, ISIN, Sector, Industry (e.g. ORIANAPOWER, HBLENGINEERING, HAL)..."
              className="w-full bg-transparent text-xs text-slate-100 placeholder:text-slate-500 focus:outline-none"
            />
          </div>
          {searchOpen && searchResults.length > 0 && (
            <div className="absolute left-0 right-0 mt-1 bg-[#0f1626] border border-slate-700 rounded-md shadow-2xl max-h-80 overflow-y-auto z-50">
              {searchResults.map((item) => (
                <button
                  key={item.stock_id || item.symbol}
                  type="button"
                  onClick={() =>
                    handleSelectSymbol(
                      item.symbol,
                      activeNav === 'overview' ? 'technical' : activeNav,
                      item.company_name || item.name
                    )
                  }
                  className="w-full px-3 py-2 text-left hover:bg-slate-800 flex items-center justify-between gap-3 text-xs border-b border-slate-800/50"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-semibold text-amber-300">{item.symbol}</span>
                      {item.bse_code && <span className="font-mono text-[10px] text-slate-500">BSE:{item.bse_code}</span>}
                      <span className="text-slate-200 truncate">{item.company_name || item.name}</span>
                    </div>
                    <div className="text-[10px] text-slate-400 font-mono truncate">
                      {item.isin ? `ISIN ${item.isin} · ` : ''}
                      {item.industry || item.sector}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-[11px] text-slate-400">{item.sector}</div>
                    {item.cap_tier && <div className="text-[10px] text-slate-500">{item.cap_tier}</div>}
                  </div>
                </button>
              ))}
            </div>
          )}
        </form>

        <div className="flex items-center gap-2.5 shrink-0">
          <div className="hidden lg:flex flex-col text-right pr-2 border-r border-slate-800">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider">Selected Stock</span>
            <span className="text-xs font-mono font-semibold text-slate-100 max-w-[180px] truncate" title={selectedCompanyName}>
              {selectedSymbol} · {selectedCompanyName}
            </span>
          </div>

          <button
            type="button"
            onClick={openMarketWideScan}
            className="hidden sm:inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium bg-[#131b2e] border border-slate-700 text-slate-200 rounded hover:bg-slate-800 whitespace-nowrap"
          >
            <Globe className="w-3.5 h-3.5 text-sky-400" />
            Scan Entire Market
          </button>

          <button
            type="button"
            onClick={runAiAnalysis}
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold bg-amber-400 text-slate-950 rounded hover:bg-amber-300 whitespace-nowrap"
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
              <div className="px-3 text-[11px] font-medium text-slate-500 mb-2">Quick Stock Switcher</div>
              <div className="space-y-0.5">
                {QUICK_WATCHLIST.map((sym) => (
                  <button
                    key={sym}
                    type="button"
                    onClick={() => handleSelectSymbol(sym, activeNav === 'overview' ? 'technical' : activeNav)}
                    className={`w-full flex items-center justify-between px-3 py-1.5 rounded text-xs font-mono transition-colors ${
                      selectedSymbol === sym
                        ? 'bg-amber-400/10 text-amber-300 font-semibold'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/40'
                    }`}
                  >
                    <span>{sym}</span>
                    <span className="text-[10px] text-slate-500">NSE</span>
                  </button>
                ))}
              </div>
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
        <main className="flex-1 min-w-0 p-5 md:p-7 pb-20 md:pb-8 overflow-y-auto">
          {activeNav === 'overview' && <OverviewSection onSelectSymbol={(s) => handleSelectSymbol(s, 'technical')} />}
          {activeNav === 'scanner' && (
            <ScannerSection
              initialMode={scannerInitialMode}
              onSelectSymbol={(s) => handleSelectSymbol(s, 'technical')}
            />
          )}
          {activeNav === 'screener' && (
            <ScreenerSection
              symbol={selectedSymbol}
              onSelectSymbol={(s, tab) => handleSelectSymbol(s, tab || 'screener')}
            />
          )}
          {activeNav === 'technical' && (
            <TechnicalSection symbol={selectedSymbol} exchange={exchange} onChangeExchange={setExchange} />
          )}
          {activeNav === 'fundamental' && (
            <FundamentalSection
              symbol={selectedSymbol}
              exchange={exchange}
              onOpenScreener={() => setActiveNav('screener')}
            />
          )}
          {activeNav === 'news' && <NewsSection symbol={selectedSymbol} />}
          {activeNav === 'backtest' && <BacktestSection symbol={selectedSymbol} />}
          {activeNav === 'portfolio' && <PortfolioRiskSection />}
          {activeNav === 'alerts' && <AlertsSettingsSection symbol={selectedSymbol} />}
        </main>
      </div>

      {/* Dynamic 12-Step AI Analysis Result Modal */}
      {workflowOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
          <div className="w-full max-w-3xl max-h-[85vh] bg-[#0f1626] border border-slate-700 rounded-lg flex flex-col overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-800">
              <div className="font-display font-semibold text-sm text-slate-100">
                12-Step AI Analysis — {selectedCompanyName} ({selectedSymbol} · {exchange})
              </div>
              <button
                type="button"
                onClick={() => setWorkflowOpen(false)}
                className="p-1 text-slate-400 hover:text-slate-100"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5 overflow-y-auto space-y-4 text-xs">
              {workflowLoading ? (
                <div className="py-12 text-center text-slate-400">
                  Executing Stock Resolution → Screener & Market Fundamentals → News → Technicals → Entry → Exit → Backtest → Risk Gate for {selectedSymbol}...
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
                    <span>Persisted in central SQLite DB + trader/analysis.json & trader/trade_plan.json.</span>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setWorkflowOpen(false);
                          setActiveNav('fundamental');
                        }}
                        className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded"
                      >
                        Open Fundamental Report
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setWorkflowOpen(false);
                          setActiveNav('technical');
                        }}
                        className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded"
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
