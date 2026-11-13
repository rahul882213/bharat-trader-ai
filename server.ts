import express from 'express';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import fs from 'node:fs/promises';
import path from 'node:path';
import dotenv from 'dotenv';
import { GoogleGenAI, Type } from '@google/genai';

dotenv.config();

const execFileAsync = promisify(execFile);
const ROOT_DIR = process.cwd();

const app = express();
app.use(express.json({ limit: '2mb' }));

// Simple in-memory TTL cache to respect external rate limits on heavy universe calls
const apiCache = new Map<string, { ts: number; data: unknown }>();
function getCached<T>(key: string, ttlMs: number): T | null {
  const hit = apiCache.get(key);
  if (hit && Date.now() - hit.ts < ttlMs) {
    return hit.data as T;
  }
  return null;
}
function setCached(key: string, data: unknown) {
  apiCache.set(key, { ts: Date.now(), data });
}

async function runPythonCli(args: string[], timeoutMs = 45000): Promise<any> {
  const { stdout, stderr } = await execFileAsync('python3', ['main.py', '--json', ...args], {
    cwd: ROOT_DIR,
    timeout: timeoutMs,
    maxBuffer: 1024 * 1024 * 10,
    env: { ...process.env, PYTHONPATH: ROOT_DIR },
  });
  if (!stdout && stderr) {
    throw new Error(stderr);
  }
  return JSON.parse(stdout);
}

async function runPythonSnippet(code: string, payload: unknown, timeoutMs = 30000): Promise<any> {
  const { stdout, stderr } = await execFileAsync(
    'python3',
    ['-c', code, JSON.stringify(payload)],
    {
      cwd: ROOT_DIR,
      timeout: timeoutMs,
      maxBuffer: 1024 * 1024 * 10,
      env: { ...process.env, PYTHONPATH: ROOT_DIR },
    }
  );
  if (!stdout && stderr) {
    throw new Error(stderr);
  }
  return JSON.parse(stdout);
}

function getGeminiClient(): GoogleGenAI | null {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey || apiKey === 'MY_GEMINI_API_KEY') return null;
  return new GoogleGenAI({
    apiKey,
    httpOptions: {
      headers: {
        'User-Agent': 'aistudio-build',
      },
    },
  });
}

// --- HEALTH ---
app.get('/api/health', (_req, res) => {
  res.json({ status: 'ok', service: 'Bharat Trader AI', trading_mode: 'paper' });
});

// --- MARKET OVERVIEW & INTELLIGENCE ---
app.get('/api/market/overview', async (req, res) => {
  try {
    const force = req.query.refresh === '1';
    if (!force) {
      const cached = getCached('market_overview', 45_000);
      if (cached) return res.json(cached);
    }
    const data = await runPythonCli(['market', 'overview']);
    setCached('market_overview', data);
    res.json(data);
  } catch (err: any) {
    res.status(500).json({ error: err.message || 'Failed to load market overview' });
  }
});

app.get('/api/report/daily', async (_req, res) => {
  try {
    const cached = getCached('daily_report', 60_000);
    if (cached) return res.json(cached);
    const data = await runPythonCli(['report', 'daily']);
    setCached('daily_report', data);
    res.json(data);
  } catch (err: any) {
    res.status(500).json({ error: err.message || 'Failed to generate daily report' });
  }
});

// --- SYMBOL SEARCH & WATCHLIST ---
app.get('/api/symbols/search', async (req, res) => {
  try {
    const q = String(req.query.q || '').trim();
    if (!q) return res.json({ results: [] });
    const data = await runPythonCli(['search', q]);
    res.json(data);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

app.get('/api/watchlist', async (_req, res) => {
  try {
    const raw = await fs.readFile(path.join(ROOT_DIR, 'trader', 'watchlist.json'), 'utf-8');
    res.json(JSON.parse(raw));
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/watchlist', async (req, res) => {
  try {
    const { symbol, exchange = 'NSE', sector = 'Indian Equities' } = req.body || {};
    if (!symbol) return res.status(400).json({ error: 'Symbol is required' });
    const filePath = path.join(ROOT_DIR, 'trader', 'watchlist.json');
    const current = JSON.parse(await fs.readFile(filePath, 'utf-8'));
    const clean = String(symbol).trim().toUpperCase().replace(/\.(NS|BO)$/i, '');
    if (!current.watchlist.some((w: any) => w.symbol === clean)) {
      current.watchlist.unshift({ symbol: clean, exchange, sector });
    }
    current.updated_at = new Date().toISOString();
    await fs.writeFile(filePath, JSON.stringify(current, null, 2));
    res.json(current);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// --- SCANNER ---
app.get('/api/scanner', async (req, res) => {
  try {
    const strategy = String(req.query.strategy || 'daily');
    const timeframe = String(req.query.timeframe || '1d');
    const universe = String(req.query.universe || 'nifty50');
    const limit = String(req.query.limit || '25');
    const exchange = String(req.query.exchange || 'NSE');
    const cacheKey = `scan:${strategy}:${timeframe}:${universe}:${limit}:${exchange}`;
    if (req.query.refresh !== '1') {
      const cached = getCached(cacheKey, 45_000);
      if (cached) return res.json(cached);
    }
    const data = await runPythonCli([
      'scanner',
      strategy,
      '--timeframe',
      timeframe,
      '--universe',
      universe,
      '--limit',
      limit,
      '--exchange',
      exchange,
    ]);
    setCached(cacheKey, data);
    res.json(data);
  } catch (err: any) {
    res.status(500).json({ error: err.message || 'Scanner failed' });
  }
});

// --- CHART & TECHNICALS ---
app.get('/api/chart/:symbol', async (req, res) => {
  try {
    const symbol = String(req.params.symbol).toUpperCase();
    const timeframe = String(req.query.timeframe || '1d');
    const exchange = String(req.query.exchange || 'NSE');
    const range = req.query.range ? String(req.query.range) : null;
    const args = ['chart', symbol, '--timeframe', timeframe, '--exchange', exchange];
    if (range) args.push('--range', range);
    const data = await runPythonCli(args);
    res.json(data);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// --- ENTRY & EXIT ENGINES ---
app.get('/api/entry/:symbol', async (req, res) => {
  try {
    const symbol = String(req.params.symbol).toUpperCase();
    const timeframe = String(req.query.timeframe || '15m');
    const exchange = String(req.query.exchange || 'NSE');
    const data = await runPythonCli(['entry', symbol, '--timeframe', timeframe, '--exchange', exchange]);
    res.json(data);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

app.get('/api/exit/:symbol', async (req, res) => {
  try {
    const symbol = String(req.params.symbol).toUpperCase();
    const timeframe = String(req.query.timeframe || '1d');
    const product = String(req.query.product || 'MIS');
    const exchange = String(req.query.exchange || 'NSE');
    const args = ['exit', symbol, '--timeframe', timeframe, '--product', product, '--exchange', exchange];
    if (req.query.entry) args.push('--entry', String(req.query.entry));
    const data = await runPythonCli(args);
    res.json(data);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// --- FULL 12-STEP WORKFLOW ---
app.get('/api/workflow/:symbol', async (req, res) => {
  try {
    const symbol = String(req.params.symbol).toUpperCase();
    const timeframe = String(req.query.timeframe || '1d');
    const exchange = String(req.query.exchange || 'NSE');
    const data = await runPythonCli(['analyse', symbol, '--timeframe', timeframe, '--exchange', exchange], 60000);
    res.json(data);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// --- FUNDAMENTAL ANALYST ---
app.get('/api/fundamentals/:symbol', async (req, res) => {
  try {
    const symbol = String(req.params.symbol).toUpperCase();
    const exchange = String(req.query.exchange || 'NSE');
    const cacheKey = `fund:${symbol}:${exchange}`;
    if (req.query.refresh !== '1') {
      const cached = getCached(cacheKey, 120_000);
      if (cached) return res.json(cached);
    }
    const data = await runPythonCli(['fundamentals', symbol, '--exchange', exchange]);
    setCached(cacheKey, data);
    res.json(data);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// --- NEWS & FILINGS ---
app.get('/api/news', async (req, res) => {
  try {
    const symbol = req.query.symbol ? String(req.query.symbol).toUpperCase() : null;
    const limit = String(req.query.limit || '30');
    const cacheKey = `news:${symbol || 'ALL'}:${limit}`;
    if (req.query.refresh !== '1') {
      const cached = getCached(cacheKey, 60_000);
      if (cached) return res.json(cached);
    }
    const args = ['news', '--limit', limit];
    if (symbol) args.push('--symbol', symbol);
    const data = await runPythonCli(args);
    setCached(cacheKey, data);
    res.json(data);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// --- BACKTESTER + 10,000 MONTE CARLO ---
app.post('/api/backtest', async (req, res) => {
  try {
    const {
      symbol = 'RELIANCE',
      strategy = 'ema_crossover',
      timeframe = '1d',
      capital = 1000000,
      trade_type = 'equity_intraday',
      runs = 10000,
    } = req.body || {};
    const data = await runPythonCli([
      'backtest',
      '--symbol',
      String(symbol).toUpperCase(),
      '--strategy',
      String(strategy),
      '--timeframe',
      String(timeframe),
      '--capital',
      String(capital),
      '--trade-type',
      String(trade_type),
      '--runs',
      String(runs),
    ]);
    res.json(data);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// --- RISK MANAGEMENT & POSITION SIZING ---
app.get('/api/risk', async (_req, res) => {
  try {
    const data = await runPythonCli(['risk', 'check']);
    res.json(data);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/risk/config', async (req, res) => {
  try {
    const data = await runPythonSnippet(
      `
import json, sys
from backend.services.workflow import load_module_fn
mod = load_module_fn("trader-risk", "risk_engine.py")
payload = json.loads(sys.argv[1])
print(json.dumps(mod.update_risk_config(payload)))
      `,
      req.body || {}
    );
    res.json(data);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/risk/evaluate', async (req, res) => {
  try {
    const data = await runPythonSnippet(
      `
import json, sys
from backend.services.workflow import load_module_fn
mod = load_module_fn("trader-risk", "risk_engine.py")
p = json.loads(sys.argv[1])
res = mod.evaluate_trade_risk(
  symbol=p["symbol"],
  entry_price=float(p["entry_price"]),
  stop_loss=float(p["stop_loss"]),
  target_price=float(p["target_price"]),
  quantity=int(p["quantity"]),
  charges_inr=float(p.get("charges_inr", 0.0)),
)
print(json.dumps(res))
      `,
      req.body || {}
    );
    res.json(data);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/budget/calculate', async (req, res) => {
  try {
    const data = await runPythonSnippet(
      `
import json, sys
from backend.services.workflow import load_module_fn
mod = load_module_fn("trader-budget", "position_sizer.py")
p = json.loads(sys.argv[1])
res = mod.calculate_position_size(
  capital_inr=float(p.get("capital_inr", 1000000)),
  risk_pct=float(p.get("risk_pct", 1.0)),
  entry_price=float(p["entry_price"]),
  stop_loss=float(p["stop_loss"]),
  segment=p.get("segment", "cash_equity"),
  trade_type=p.get("trade_type", "equity_intraday"),
  broker=p.get("broker", "zerodha"),
  lot_size=int(p.get("lot_size", 1)),
  fno_enabled=bool(p.get("fno_enabled", False)),
)
print(json.dumps(res))
      `,
      req.body || {}
    );
    res.json(data);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// --- PORTFOLIO, PAPER TRADING & BROKER ADAPTERS ---
app.get('/api/portfolio', async (req, res) => {
  try {
    const liveLtp = req.query.live === '1';
    const args = ['portfolio'];
    if (liveLtp) args.push('--live-ltp');
    const data = await runPythonCli(args);
    res.json(data);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

app.get('/api/brokers/status', async (_req, res) => {
  try {
    const data = await runPythonSnippet(
      `
import json
from backend.services.workflow import load_module_fn
mod = load_module_fn("trader-broker", "broker_executor.py")
print(json.dumps(mod.get_broker_status()))
      `,
      {}
    );
    res.json(data);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/orders/preview', async (req, res) => {
  try {
    const data = await runPythonSnippet(
      `
import json, sys
from backend.services.workflow import load_module_fn
mod = load_module_fn("trader-broker", "broker_executor.py")
p = json.loads(sys.argv[1])
print(json.dumps(mod.preview_live_order(p)))
      `,
      req.body || {}
    );
    res.json(data);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/orders/execute', async (req, res) => {
  try {
    const data = await runPythonSnippet(
      `
import json, sys
from backend.services.workflow import load_module_fn
broker_mod = load_module_fn("trader-broker", "broker_executor.py")
risk_mod = load_module_fn("trader-risk", "risk_engine.py")
p = json.loads(sys.argv[1])
order = p["order"]
mode = p.get("mode", "paper")
broker = p.get("broker", "paper")
approved = bool(p.get("explicit_user_approval", False))

# Always enforce Risk Gate before opening new BUY/SELL position
if not p.get("skip_risk_check", False) and order.get("stop_loss") and order.get("target"):
    rc = risk_mod.evaluate_trade_risk(
        symbol=order["symbol"],
        entry_price=float(order["price"]),
        stop_loss=float(order["stop_loss"]),
        target_price=float(order["target"]),
        quantity=int(order["quantity"]),
    )
    if rc["verdict"] == "BLOCK":
        print(json.dumps({"executed": False, "blocked_by_risk": True, "risk_check": rc}))
        sys.exit(0)

res = broker_mod.execute_order(order, mode=mode, broker=broker, explicit_user_approval=approved)
print(json.dumps(res))
      `,
      req.body || {}
    );
    res.json(data);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/positions/close', async (req, res) => {
  try {
    const data = await runPythonSnippet(
      `
import json, sys
from backend.broker_adapters.paper_adapter import PaperBrokerAdapter
p = json.loads(sys.argv[1])
res = PaperBrokerAdapter().close_position(
  symbol=p["symbol"],
  exchange=p.get("exchange", "NSE"),
  product=p.get("product", "MIS"),
  exit_price=float(p["exit_price"]) if p.get("exit_price") else None,
)
print(json.dumps(res))
      `,
      req.body || {}
    );
    res.json(data);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// --- ALERTS ---
app.get('/api/alerts', async (_req, res) => {
  try {
    const data = await runPythonCli(['alerts', 'list']);
    res.json(data);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/alerts', async (req, res) => {
  try {
    const data = await runPythonSnippet(
      `
import json, sys
from backend.services.workflow import load_module_fn
mod = load_module_fn("trader-alerts", "alert_engine.py")
p = json.loads(sys.argv[1])
res = mod.create_alert(
  symbol=p["symbol"],
  condition=p["condition"],
  threshold=float(p["threshold"]) if p.get("threshold") not in (None, "") else None,
  exchange=p.get("exchange", "NSE"),
  telegram_notify=bool(p.get("telegram_notify", False)),
  message=p.get("message", ""),
)
print(json.dumps(res))
      `,
      req.body || {}
    );
    res.json(data);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/alerts/check', async (_req, res) => {
  try {
    const data = await runPythonCli(['alerts', 'check']);
    res.json(data);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

app.delete('/api/alerts/:id', async (req, res) => {
  try {
    const data = await runPythonSnippet(
      `
import json, sys
from backend.services.workflow import load_module_fn
mod = load_module_fn("trader-alerts", "alert_engine.py")
p = json.loads(sys.argv[1])
print(json.dumps(mod.delete_alert(p["id"])))
      `,
      { id: req.params.id }
    );
    res.json(data);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// --- SERVER-SIDE GEMINI AI RESEARCH SYNTHESIS ---
app.post('/api/ai/research', async (req, res) => {
  const ai = getGeminiClient();
  if (!ai) {
    return res.status(503).json({
      error: 'GEMINI_API_KEY is not configured in environment secrets. Quantitative metrics remain fully operational.',
    });
  }
  try {
    const { symbol, context } = req.body || {};
    if (!symbol) return res.status(400).json({ error: 'Symbol is required' });

    const response = await ai.models.generateContent({
      model: 'gemini-4-hydrogen',
      contents:
        `Analyze the Indian equity ${symbol} strictly based on the verified quantitative, fundamental, and news context provided below. ` +
        `Never invent prices, revenue figures, or guaranteed return predictions. Clearly distinguish reported facts from analytical interpretation.\n\n` +
        `CONTEXT JSON:\n${JSON.stringify(context).slice(0, 14000)}`,
      config: {
        systemInstruction:
          'You are a senior Indian equity research analyst and algorithmic risk officer at an institutional NSE/BSE desk. ' +
          'Output strictly structured JSON in INR (₹). Focus on price structure, fundamental quality, governance, catalysts, and downside risk.',
        responseMimeType: 'application/json',
        responseSchema: {
          type: Type.OBJECT,
          properties: {
            thesis_headline: { type: Type.STRING },
            technical_stance: { type: Type.STRING },
            fundamental_assessment: { type: Type.STRING },
            key_catalysts: { type: Type.ARRAY, items: { type: Type.STRING } },
            key_risks: { type: Type.ARRAY, items: { type: Type.STRING } },
            actionable_desk_note: { type: Type.STRING },
          },
          required: [
            'thesis_headline',
            'technical_stance',
            'fundamental_assessment',
            'key_catalysts',
            'key_risks',
            'actionable_desk_note',
          ],
        },
      },
    });

    const parsed = JSON.parse((response.text ?? '{}').trim());
    res.json({ available: true, symbol, model: 'gemini-4-hydrogen', synthesis: parsed });
  } catch (err: any) {
    res.status(500).json({ error: err.message || 'Gemini AI synthesis failed' });
  }
});

// --- VITE DEV / STATIC PRODUCTION SERVING ---
const PORT = 3000;

async function startServer() {
  if (process.env.NODE_ENV !== 'production') {
    const { createServer: createViteServer } = await import('vite');
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distDir = path.join(ROOT_DIR, 'dist');
    app.use(express.static(distDir));
    app.get('*', (_req, res) => {
      res.sendFile(path.join(distDir, 'index.html'));
    });
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Bharat Trader AI server running on http://0.0.0.0:${PORT}`);
  });
}

startServer();
