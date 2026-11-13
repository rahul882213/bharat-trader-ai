import React, { useEffect, useState } from 'react';
import {
  Activity,
  BarChart3,
  Bell,
  Briefcase,
  CandlestickChart,
  FileSpreadsheet,
  Newspaper,
  Radar,
  Search,
  Workflow,
  X,
} from 'lucide-react';
import type { NavSection, SearchSymbolResult } from './types/trading';
import { OverviewSection } from './components/OverviewSection';
import { ScannerSection } from './components/ScannerSection';
import { TechnicalSection } from './components/TechnicalSection';
import { FundamentalSection } from './components/FundamentalSection';
import { NewsSection } from './components/NewsSection';
import { BacktestSection } from './components/BacktestSection';
import { PortfolioRiskSection } from './components/PortfolioRiskSection';
import { AlertsSettingsSection } from './components/AlertsSettingsSection';
import { formatINR } from './utils/formatters';

const NAV_ITEMS: { id: NavSection; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: 'overview', label: 'Market Overview', icon: Activity },
  { id: 'scanner', label: 'AI Stock Scanner', icon: Radar },
  { id: 'technical', label: 'Technicals & Entry/Exit', icon: CandlestickChart },
  { id: 'fundamental', label: 'Fundamental Analyst', icon: FileSpreadsheet },
  { id: 'news', label: 'News & Filings', icon: Newspaper },
  { id: 'backtest', label: 'Backtesting Engine', icon: BarChart3 },
  { id: 'portfolio', label: 'Portfolio & Risk', icon: Briefcase },
  { id: 'alerts', label: 'Alerts & Settings', icon: Bell },
];

const QUICK_WATCHLIST = ['RELIANCE', 'TCS', 'HDFCBANK', 'HAL', 'TATAMOTORS', 'INFY', 'SBIN', 'ORIANA'];

export default function App() {
  const [activeNav, setActiveNav] = useState<NavSection>('overview');
  const [selectedSymbol, setSelectedSymbol] = useState<string>('RELIANCE');
  const [exchange, setExchange] = useState<'NSE' | 'BSE'>('NSE');

  // Symbol Search
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchSymbolResult[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);

  // 12-Step Automated Workflow Modal
  const [workflowOpen, setWorkflowOpen] = useState(false);
  const [workflowLoading, setWorkflowLoading] = useState(false);
  const [workflowData, setWorkflowData] = useState<any>(null);
  const [workflowError, setWorkflowError] = useState<string | null>(null);

  useEffect(() => {
    const q = searchQuery.trim();
    if (!q) {
      setSearchResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/symbols/search?q=${encodeURIComponent(q)}`);
        const json = await res.json();
        setSearchResults(json.results || []);
        setSearchOpen(true);
      } catch {
        setSearchResults([]);
      }
    }, 220);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const handleSelectSymbol = (sym: string, targetTab: NavSection = 'technical') => {
    setSelectedSymbol(sym.toUpperCase());
    setActiveNav(targetTab);
    setSearchOpen(false);
    setSearchQuery('');
  };

  const runFullWorkflow = async () => {
    setWorkflowOpen(true);
    setWorkflowLoading(true);
    setWorkflowError(null);
    try {
      const res = await fetch(`/api/workflow/${encodeURIComponent(selectedSymbol)}?exchange=${exchange}`);
      const json = await res.json();
      if (!json.available) throw new Error(json.error || 'Workflow execution failed');
      setWorkflowData(json);
    } catch (e: any) {
      setWorkflowError(e.message || 'Workflow execution failed');
    } finally {
      setWorkflowLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#090d16] text-slate-200 flex flex-col">
      {/* Top Bar Contract: Brand Wordmark — Symbol Search — Primary CTA */}
      <header className="sticky top-0 z-30 h-14 px-5 border-b border-slate-800 bg-[#0b101b]/95 backdrop-blur flex items-center justify-between gap-6">
        <button
          type="button"
          onClick={() => setActiveNav('overview')}
          className="font-display text-base font-bold tracking-tight text-slate-100 whitespace-nowrap shrink-0"
        >
          Bharat Trader AI
        </button>

        <div className="relative flex-1 max-w-md">
          <div className="flex items-center bg-[#0f1626] border border-slate-700/80 rounded px-3 py-1.5">
            <Search className="w-3.5 h-3.5 text-slate-400 mr-2 shrink-0" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onFocus={() => searchResults.length && setSearchOpen(true)}
              placeholder={`Search NSE/BSE stock (Active: ${selectedSymbol})...`}
              className="w-full bg-transparent text-xs text-slate-100 placeholder:text-slate-500 focus:outline-none"
            />
          </div>
          {searchOpen && searchResults.length > 0 && (
            <div className="absolute left-0 right-0 mt-1 bg-[#0f1626] border border-slate-700 rounded-md shadow-2xl max-h-72 overflow-y-auto z-50">
              {searchResults.map((item) => (
                <button
                  key={item.symbol}
                  type="button"
                  onClick={() => handleSelectSymbol(item.symbol)}
                  className="w-full px-3 py-2 text-left hover:bg-slate-800 flex items-center justify-between text-xs border-b border-slate-800/50"
                >
                  <div>
                    <span className="font-mono font-semibold text-slate-100">{item.symbol}</span>
                    <span className="text-slate-400 ml-2 truncate">{item.name}</span>
                  </div>
                  <span className="text-[11px] text-slate-500">{item.sector}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <button
          type="button"
          onClick={runFullWorkflow}
          className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold bg-amber-400 text-slate-950 rounded hover:bg-amber-300 whitespace-nowrap shrink-0"
        >
          <Workflow className="w-3.5 h-3.5" />
          Run 12-Step Workflow ({selectedSymbol})
        </button>
      </header>

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
                    onClick={() => setActiveNav(item.id)}
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
              <div className="px-3 text-[11px] font-medium text-slate-500 mb-2">Quick NSE Watchlist</div>
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
          {activeNav === 'scanner' && <ScannerSection onSelectSymbol={(s) => handleSelectSymbol(s, 'technical')} />}
          {activeNav === 'technical' && (
            <TechnicalSection symbol={selectedSymbol} exchange={exchange} onChangeExchange={setExchange} />
          )}
          {activeNav === 'fundamental' && <FundamentalSection symbol={selectedSymbol} exchange={exchange} />}
          {activeNav === 'news' && <NewsSection symbol={selectedSymbol} />}
          {activeNav === 'backtest' && <BacktestSection symbol={selectedSymbol} />}
          {activeNav === 'portfolio' && <PortfolioRiskSection />}
          {activeNav === 'alerts' && <AlertsSettingsSection symbol={selectedSymbol} />}
        </main>
      </div>

      {/* 12-Step Automated Workflow Result Modal */}
      {workflowOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
          <div className="w-full max-w-3xl max-h-[85vh] bg-[#0f1626] border border-slate-700 rounded-lg flex flex-col overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-800">
              <div className="font-display font-semibold text-sm text-slate-100">
                12-Step Connected AI Workflow — {selectedSymbol} ({exchange})
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
                  Executing Scanner → News → Technicals → Entry → Exit → Backtest → Sizing → Risk Gate...
                </div>
              ) : workflowError ? (
                <div className="p-4 bg-rose-950/40 border border-rose-800 rounded text-rose-200">{workflowError}</div>
              ) : workflowData ? (
                <>
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

                  <div className="p-4 bg-[#0a0f1c] border border-slate-800 rounded space-y-2">
                    <div className="font-semibold text-slate-200">Pipeline Summary</div>
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

                  <div className="text-[11px] text-slate-400">
                    Structured JSON outputs saved to trader/analysis.json and trader/trade_plan.json.
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
