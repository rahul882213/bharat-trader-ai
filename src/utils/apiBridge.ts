/**
 * Configurable Client API Bridge for Bharat Trader AI.
 * - Uses VITE_API_BASE_URL (HTTPS backend URL e.g. Render) when configured, or runtime
 *   saved URL (?api=https://... / localStorage), or same-origin when hosted full-stack.
 * - On static hosts (e.g. GitHub Pages) when no live backend is connected, serves real
 *   static NSE/BSE symbol directory search from stocks-master.json and returns clear
 *   503 JSON diagnostics for live-data endpoints (zero fake market data or status).
 */

const STORAGE_KEY = 'bharat_trader_api_url';
const STATIC_EVENT = 'bharat-trader-static-mode';

let cachedMaster: any[] | null = null;
let isStaticMode = false;

export interface BackendHealthStatus {
  checked: boolean;
  connected: boolean;
  backendUrl: string;
  apiVersion?: string;
  tradingMode?: string;
  database?: {
    connected: boolean;
    dialect?: string;
    stock_master_count?: number;
    last_data_update?: string | null;
    error?: string | null;
  };
  dataProviders?: Record<string, { available?: boolean; configured?: boolean; symbols_count?: number; type?: string }>;
  lastUpdated?: string | null;
  error?: string | null;
}

export function getConfiguredEnvApiUrl(): string {
  const envUrl = (import.meta as any).env?.VITE_API_BASE_URL || '';
  return String(envUrl).trim().replace(/\/+$/, '');
}

export function getBackendBaseUrl(): string {
  if (typeof window === 'undefined') return getConfiguredEnvApiUrl();
  try {
    const params = new URLSearchParams(window.location.search);
    const fromQuery = params.get('api');
    if (fromQuery !== null) {
      const cleaned = fromQuery.trim().replace(/\/+$/, '');
      if (cleaned) localStorage.setItem(STORAGE_KEY, cleaned);
      else localStorage.removeItem(STORAGE_KEY);
    }
    const stored = localStorage.getItem(STORAGE_KEY) || '';
    if (stored) return stored.replace(/\/+$/, '');
  } catch {
    // Ignore storage errors
  }
  return getConfiguredEnvApiUrl();
}

export function getDisplayBackendUrl(): string {
  const configured = getBackendBaseUrl();
  if (configured) return configured;
  if (typeof window !== 'undefined' && !window.location.hostname.endsWith('github.io')) {
    return window.location.origin;
  }
  return '';
}

export function setBackendBaseUrl(url: string) {
  if (typeof window === 'undefined') return;
  const cleaned = url.trim().replace(/\/+$/, '');
  if (cleaned) localStorage.setItem(STORAGE_KEY, cleaned);
  else localStorage.removeItem(STORAGE_KEY);
  isStaticMode = false;
  window.dispatchEvent(new CustomEvent(STATIC_EVENT, { detail: false }));
}

export function getIsStaticMode(): boolean {
  return isStaticMode;
}

function markStaticMode() {
  if (!isStaticMode && typeof window !== 'undefined') {
    isStaticMode = true;
    window.dispatchEvent(new CustomEvent(STATIC_EVENT, { detail: true }));
  }
}

async function loadStaticMaster(origFetch: typeof fetch): Promise<any[]> {
  if (cachedMaster) return cachedMaster;
  const base = ((import.meta as any).env?.BASE_URL || '/').replace(/\/?$/, '/');
  const res = await origFetch(`${base}stocks-master.json`);
  if (!res.ok) return [];
  const data = await res.json();
  cachedMaster = Array.isArray(data) ? data : [];
  return cachedMaster;
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

export async function checkBackendHealth(): Promise<BackendHealthStatus> {
  const baseUrl = getBackendBaseUrl();
  const displayUrl = getDisplayBackendUrl();
  const isGitHubPages = typeof window !== 'undefined' && window.location.hostname.endsWith('github.io');

  if (!baseUrl && isGitHubPages) {
    markStaticMode();
    return {
      checked: true,
      connected: false,
      backendUrl: '',
      database: { connected: false },
      dataProviders: {},
      lastUpdated: null,
      error:
        'Backend API URL is not configured. Deploy the FastAPI backend on Render, set VITE_API_BASE_URL, or connect your deployed HTTPS backend URL.',
    };
  }

  const target = baseUrl ? `${baseUrl}/health` : '/health';
  try {
    const res = await window.fetch(target, { cache: 'no-store' });
    const ct = res.headers.get('content-type') || '';
    if (!ct.includes('application/json')) {
      markStaticMode();
      return {
        checked: true,
        connected: false,
        backendUrl: displayUrl,
        database: { connected: false },
        dataProviders: {},
        lastUpdated: null,
        error: `Backend at ${displayUrl || 'origin'} returned non-JSON HTTP ${res.status}.`,
      };
    }
    const json = await res.json();
    if (!res.ok || (json.status !== 'ok' && json.status !== 'degraded')) {
      return {
        checked: true,
        connected: false,
        backendUrl: displayUrl,
        database: json.database || { connected: false },
        dataProviders: json.data_providers || {},
        lastUpdated: json.last_updated || null,
        error: json.error || `Backend responded with HTTP ${res.status}`,
      };
    }
    isStaticMode = false;
    window.dispatchEvent(new CustomEvent(STATIC_EVENT, { detail: false }));
    return {
      checked: true,
      connected: true,
      backendUrl: displayUrl,
      apiVersion: json.api_version,
      tradingMode: json.trading_mode,
      database: json.database || { connected: true },
      dataProviders: json.data_providers || {},
      lastUpdated: json.last_updated || json.database?.last_data_update || json.server_time_ist || null,
      error: null,
    };
  } catch (err: any) {
    markStaticMode();
    return {
      checked: true,
      connected: false,
      backendUrl: displayUrl,
      database: { connected: false },
      dataProviders: {},
      lastUpdated: null,
      error: err?.message || 'Unable to reach Bharat Trader AI backend over HTTPS.',
    };
  }
}

async function handleStaticFallback(urlPath: string, origFetch: typeof fetch): Promise<Response> {
  markStaticMode();
  const parsed = new URL(urlPath, window.location.origin);
  const path = parsed.pathname;

  if (path === '/api/symbols/search') {
    const master = await loadStaticMaster(origFetch);
    const q = (parsed.searchParams.get('q') || '').trim().toUpperCase();
    const limit = Math.min(Number(parsed.searchParams.get('limit') || 25), 100);
    if (!q) return jsonResponse({ results: master.slice(0, limit) });

    const scored: { score: number; row: any }[] = [];
    for (const row of master) {
      const sym = String(row.symbol || '').toUpperCase();
      const bse = String(row.bse_code || '').toUpperCase();
      const isin = String(row.isin || '').toUpperCase();
      const name = String(row.company_name || row.name || '').toUpperCase();
      const sector = String(row.sector || '').toUpperCase();
      const industry = String(row.industry || '').toUpperCase();
      const aliases: string[] = Array.isArray(row.aliases)
        ? row.aliases.map((a: string) => String(a).toUpperCase())
        : [];

      let score = 0;
      if (sym === q || bse === q || isin === q || aliases.includes(q)) score = 100;
      else if (sym.startsWith(q) || aliases.some((a) => a.startsWith(q))) score = 85;
      else if (name.startsWith(q)) score = 75;
      else if (sym.includes(q) || name.includes(q) || aliases.some((a) => a.includes(q))) score = 60;
      else if (sector.includes(q) || industry.includes(q) || bse.includes(q) || isin.includes(q)) score = 40;

      if (score > 0) scored.push({ score, row });
    }
    scored.sort((a, b) => b.score - a.score);
    return jsonResponse({ results: scored.slice(0, limit).map((s) => s.row), static_mode: true });
  }

  if (path.startsWith('/api/stocks/resolve/')) {
    const master = await loadStaticMaster(origFetch);
    const raw = decodeURIComponent(path.replace('/api/stocks/resolve/', '')).trim().toUpperCase();
    const hit =
      master.find(
        (r) =>
          String(r.symbol || '').toUpperCase() === raw ||
          String(r.nse_symbol || '').toUpperCase() === raw ||
          String(r.bse_code || '').toUpperCase() === raw ||
          String(r.isin || '').toUpperCase() === raw ||
          (Array.isArray(r.aliases) && r.aliases.some((a: string) => String(a).toUpperCase() === raw))
      ) ||
      master.find((r) => String(r.company_name || '').toUpperCase().includes(raw));
    if (hit) return jsonResponse({ ...hit, static_mode: true });
    return jsonResponse({
      stock_id: raw,
      nse_symbol: raw,
      symbol: raw,
      company_name: raw,
      exchange: parsed.searchParams.get('exchange') || 'NSE',
      sector: 'Indian Equities',
      industry: 'Indian Listed Equity',
      static_mode: true,
    });
  }

  if (path === '/api/stocks/master/stats') {
    const master = await loadStaticMaster(origFetch);
    const capTiers: Record<string, number> = {};
    const sectors = new Set<string>();
    for (const r of master) {
      if (r.cap_tier) capTiers[r.cap_tier] = (capTiers[r.cap_tier] || 0) + 1;
      if (r.sector) sectors.add(r.sector);
    }
    return jsonResponse({
      total_stocks: master.length,
      cap_tiers: capTiers,
      sectors_count: sectors.size,
      static_mode: true,
    });
  }

  if (path === '/api/screener/template-csv') {
    return jsonResponse({
      csv:
        'Name,NSE Code,BSE Code,Current Price,Market Capitalization,Stock P/E,ROE %,ROCE %,Debt to Equity,Sales growth 3Years,Profit growth 3Years,OPM %,Promoter holding %,Pledged percentage\n' +
        'Reliance Industries Ltd,RELIANCE,500325,1349.4,1826000,25.4,9.8,11.2,0.42,8.5,7.2,15.8,50.1,0.0\n',
      static_mode: true,
    });
  }

  if (path === '/api/screener/companies') {
    return jsonResponse({ count: 0, companies: [], static_mode: true });
  }

  if (path === '/api/screener/screens') {
    return jsonResponse({ screens: [], static_mode: true });
  }

  if (path.startsWith('/api/screener/company/')) {
    return jsonResponse({ found: false, company: null, static_mode: true });
  }

  if (path === '/api/alerts') {
    return jsonResponse({ alerts: [], static_mode: true });
  }

  if (path === '/api/brokers/status') {
    return jsonResponse({ active_mode: 'paper', brokers: [], static_mode: true });
  }

  return jsonResponse(
    {
      error:
        'Backend API Disconnected: Deploy the FastAPI backend on Render (with Supabase PostgreSQL) and connect via VITE_API_BASE_URL or the HTTPS backend connector bar.',
      static_mode: true,
      available: false,
    },
    503
  );
}

export function installApiBridge() {
  if (typeof window === 'undefined' || (window as any).__bharatApiBridgeInstalled) return;
  (window as any).__bharatApiBridgeInstalled = true;

  const origFetch = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const rawUrl =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.toString()
          : input.url;

    if (!rawUrl.startsWith('/api/')) {
      return origFetch(input, init);
    }

    const baseUrl = getBackendBaseUrl();
    const isGitHubPages = window.location.hostname.endsWith('github.io');

    // On GitHub Pages with no backend URL configured, avoid firing doomed 404 calls
    if (!baseUrl && isGitHubPages) {
      return handleStaticFallback(rawUrl, origFetch);
    }

    const targetUrl = baseUrl ? `${baseUrl}${rawUrl}` : rawUrl;

    try {
      const res = await origFetch(targetUrl, init);
      const ct = res.headers.get('content-type') || '';
      if (res.status === 404 || (!ct.includes('application/json') && !res.ok)) {
        return handleStaticFallback(rawUrl, origFetch);
      }
      return res;
    } catch {
      return handleStaticFallback(rawUrl, origFetch);
    }
  };
}
