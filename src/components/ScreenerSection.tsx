import React, { useEffect, useState } from 'react';
import { Download, ExternalLink, FileSpreadsheet, Globe, Link2, Save, Upload } from 'lucide-react';
import { formatCrores, formatINR, formatISTTime } from '../utils/formatters';

interface Props {
  symbol: string;
  onSelectSymbol: (sym: string, tab?: 'technical' | 'fundamental' | 'screener') => void;
}

type ScreenerSubTab =
  | 'company'
  | 'quarters'
  | 'annual'
  | 'balance'
  | 'cashflow'
  | 'shareholding'
  | 'ratios'
  | 'peers'
  | 'screens';

export const ScreenerSection: React.FC<Props> = ({ symbol, onSelectSymbol }) => {
  const [subTab, setSubTab] = useState<ScreenerSubTab>('company');
  const [companyData, setCompanyData] = useState<any>(null);
  const [importedCompanies, setImportedCompanies] = useState<any[]>([]);
  const [screens, setScreens] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusMsg, setStatusMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  // Import Controls
  const [statementScope, setStatementScope] = useState<'Consolidated' | 'Standalone'>('Consolidated');
  const [updateExisting, setUpdateExisting] = useState(true);
  const [screenName, setScreenName] = useState('');
  const [screenerUrlInput, setScreenerUrlInput] = useState('');
  const [uploading, setUploading] = useState(false);

  // Business & Order Book Notes Form
  const [notesForm, setNotesForm] = useState({
    order_book_cr: '',
    order_inflow_cr: '',
    order_execution_timeline: '',
    customer_concentration: '',
    industry_outlook: '',
    competitive_position: '',
    management_notes: '',
  });
  const [savingNotes, setSavingNotes] = useState(false);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [cRes, listRes, scrRes] = await Promise.all([
        fetch(`/api/screener/company/${encodeURIComponent(symbol)}`),
        fetch('/api/screener/companies'),
        fetch('/api/screener/screens'),
      ]);
      const [cJson, listJson, scrJson] = await Promise.all([cRes.json(), listRes.json(), scrRes.json()]);
      setCompanyData(cJson);
      setImportedCompanies(listJson.companies || []);
      setScreens(scrJson.screens || []);
      setScreenerUrlInput(cJson?.screener_url || cJson?.stock_meta?.screener_url || '');
      const bn = cJson?.business_notes || {};
      setNotesForm({
        order_book_cr: bn.order_book_cr !== undefined ? String(bn.order_book_cr) : '',
        order_inflow_cr: bn.order_inflow_cr !== undefined ? String(bn.order_inflow_cr) : '',
        order_execution_timeline: bn.order_execution_timeline || '',
        customer_concentration: bn.customer_concentration || '',
        industry_outlook: bn.industry_outlook || '',
        competitive_position: bn.competitive_position || '',
        management_notes: bn.management_notes || '',
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, [symbol]);

  const handleCsvUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setStatusMsg(null);
    try {
      const text = await file.text();
      const res = await fetch('/api/screener/import-csv', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          csv_text: text,
          filename: file.name,
          screen_name: screenName || file.name.replace(/\.csv$/i, ''),
          screener_url: screenerUrlInput || undefined,
          statement_scope: statementScope,
          update_existing: updateExisting,
        }),
      });
      const json = await res.json();
      if (!json.success) throw new Error(json.error || 'CSV import failed');
      setStatusMsg({
        type: 'ok',
        text: `Imported ${json.processed_companies} companies from ${file.name} (${json.inserted_new} new, ${json.updated_existing} updated, ${json.duplicates_in_file} file duplicates handled).`,
      });
      await loadAll();
    } catch (err: any) {
      setStatusMsg({ type: 'err', text: err.message });
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const handleXlsxUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setStatusMsg(null);
    try {
      const b64: string = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ''));
        reader.onerror = () => reject(new Error('Failed to read Excel file'));
        reader.readAsDataURL(file);
      });
      const res = await fetch('/api/screener/import-xlsx', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content_base64: b64,
          filename: file.name,
          symbol_hint: symbol,
          screener_url: screenerUrlInput || undefined,
          statement_scope: statementScope,
          update_existing: updateExisting,
        }),
      });
      const json = await res.json();
      if (!json.success) throw new Error(json.error || 'Excel import failed');
      setStatusMsg({
        type: 'ok',
        text: `Imported ${json.company?.company_name || json.company?.symbol} (.xlsx): ${json.pnl_periods} annual P&L periods, ${json.quarterly_periods} quarters, ${json.balance_sheet_periods} balance sheets.`,
      });
      if (json.company?.symbol) onSelectSymbol(json.company.symbol, 'screener');
      await loadAll();
    } catch (err: any) {
      setStatusMsg({ type: 'err', text: err.message });
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const downloadCsvTemplate = async () => {
    const res = await fetch('/api/screener/template-csv');
    const json = await res.json();
    const blob = new Blob([json.csv || ''], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'screener_import_template.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  const saveUrlAssociation = async () => {
    if (!screenerUrlInput.trim()) return;
    setStatusMsg(null);
    const res = await fetch('/api/screener/associate-url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, screener_url: screenerUrlInput.trim(), statement_scope: statementScope }),
    });
    const json = await res.json();
    if (json.updated) {
      setStatusMsg({ type: 'ok', text: `Associated Screener.in URL with ${json.symbol}.` });
      await loadAll();
    }
  };

  const runOptionalPublicFetch = async () => {
    setUploading(true);
    setStatusMsg(null);
    try {
      const res = await fetch('/api/screener/optional-public-fetch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, statement_scope: statementScope }),
      });
      const json = await res.json();
      if (!json.available) throw new Error(json.error || 'Public page fetch unavailable');
      setStatusMsg({
        type: 'ok',
        text: `Fetched public ratios from ${json.source} for ${json.company_name}. Import Excel export for full multi-year statements.`,
      });
    } catch (err: any) {
      setStatusMsg({ type: 'err', text: err.message });
    } finally {
      setUploading(false);
    }
  };

  const saveBusinessNotes = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingNotes(true);
    setStatusMsg(null);
    try {
      const payload: Record<string, any> = { ...notesForm };
      if (notesForm.order_book_cr) payload.order_book_cr = Number(notesForm.order_book_cr);
      if (notesForm.order_inflow_cr) payload.order_inflow_cr = Number(notesForm.order_inflow_cr);
      const res = await fetch('/api/screener/business-notes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, notes: payload }),
      });
      const json = await res.json();
      if (json.updated) {
        setStatusMsg({ type: 'ok', text: `Saved order book & business notes for ${symbol}.` });
        await loadAll();
      }
    } finally {
      setSavingNotes(false);
    }
  };

  const meta = companyData?.stock_meta || {};
  const ratios = companyData?.ratios || {};
  const pnl: any[] = companyData?.pnl_annual || [];
  const quarters: any[] = companyData?.quarters || [];
  const bs: any[] = companyData?.balance_sheet || [];
  const cf: any[] = companyData?.cash_flow || [];
  const sh: any[] = companyData?.shareholding || [];
  const peers: any[] = companyData?.peers || [];
  const missing: string[] = companyData?.missing_fields || [];

  const renderDynamicStatementTable = (rows: any[], emptyMsg: string) => {
    if (!rows.length) {
      return (
        <div className="p-6 text-center text-xs text-slate-400">
          {emptyMsg} Export the company workbook (.xlsx) from Screener.in and upload it above to inspect multi-year rows.
        </div>
      );
    }
    const keys = Array.from(new Set(rows.flatMap((r) => Object.keys(r)))).filter((k) => k !== 'period');
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="border-b border-slate-800 text-slate-400 font-sans">
              <th className="text-left px-4 py-2.5 font-medium sticky left-0 bg-[#0f1626]">Metric (₹ Cr)</th>
              {rows.map((r, i) => (
                <th key={i} className="text-right px-4 py-2.5 font-medium whitespace-nowrap">
                  {r.period}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => (
              <tr key={k} className="border-b border-slate-800/60 hover:bg-slate-800/30">
                <td className="px-4 py-2 font-sans text-slate-200 capitalize sticky left-0 bg-[#0f1626]">
                  {k.replace(/_/g, ' ')}
                </td>
                {rows.map((r, i) => (
                  <td key={i} className="px-4 py-2 text-right tabular-nums text-slate-100">
                    {r[k] !== undefined && r[k] !== null ? Number(r[k]).toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '—'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* Header & Provenance */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-xl font-bold text-slate-100">
            Screener.in Data Center — {meta.company_name || symbol} ({meta.nse_symbol || symbol})
          </h1>
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400 mt-1">
            <span>Source: {companyData?.source || 'No Screener Export Imported Yet'}</span>
            <span aria-hidden="true">·</span>
            <span>Scope: {companyData?.statement_scope || statementScope}</span>
            <span aria-hidden="true">·</span>
            <span>Period: {companyData?.reporting_period || 'Unavailable'}</span>
            <span aria-hidden="true">·</span>
            <span>{companyData?.is_estimated ? 'Estimated' : 'Actual Export Data'}</span>
            {companyData?.imported_at && (
              <>
                <span aria-hidden="true">·</span>
                <span className="font-mono">Last Data Update: {formatISTTime(companyData.imported_at)}</span>
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={downloadCsvTemplate}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium bg-[#131b2e] border border-slate-700 text-slate-200 rounded hover:bg-slate-800"
          >
            <Download className="w-3.5 h-3.5" />
            CSV Header Template
          </button>
          {(companyData?.screener_url || meta.screener_url) && (
            <a
              href={companyData?.screener_url || meta.screener_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium bg-[#131b2e] border border-slate-700 text-amber-300 rounded hover:bg-slate-800"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              Open on Screener.in
            </a>
          )}
        </div>
      </div>

      {/* Upload / Import Controls (CSV + Excel .xlsx + URL Association) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-[#0f1626] border border-slate-800 rounded-lg p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-display text-sm font-semibold text-slate-100">
              Import Screener.in Exported Files (CSV & Excel .xlsx)
            </h2>
            <span className="text-[11px] text-slate-400">
              Auto-maps NSE/BSE/ISIN · Updates existing records · Detects duplicates
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div>
              <label className="block text-slate-400 mb-1">Statement Scope</label>
              <select
                value={statementScope}
                onChange={(e) => setStatementScope(e.target.value as any)}
                className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-1.5 text-slate-100"
              >
                <option value="Consolidated">Consolidated</option>
                <option value="Standalone">Standalone</option>
              </select>
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Stock Screen Name (CSV)</label>
              <input
                type="text"
                value={screenName}
                onChange={(e) => setScreenName(e.target.value)}
                placeholder="e.g. High ROCE Cap Goods"
                className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-2.5 py-1.5 text-slate-100"
              />
            </div>
            <div className="flex items-end pb-1.5">
              <label className="flex items-center gap-2 text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={updateExisting}
                  onChange={(e) => setUpdateExisting(e.target.checked)}
                />
                Update previously imported duplicates
              </label>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="flex items-center justify-center gap-2 p-4 border border-dashed border-slate-700 rounded-lg bg-[#0a0f1c] hover:border-amber-400/60 cursor-pointer text-xs">
              <Upload className="w-4 h-4 text-amber-300" />
              <div>
                <div className="font-semibold text-slate-100">Import Screener CSV</div>
                <div className="text-slate-400">Multi-company stock screens or company CSV</div>
              </div>
              <input type="file" accept=".csv,text/csv" onChange={handleCsvUpload} disabled={uploading} className="hidden" />
            </label>

            <label className="flex items-center justify-center gap-2 p-4 border border-dashed border-slate-700 rounded-lg bg-[#0a0f1c] hover:border-emerald-400/60 cursor-pointer text-xs">
              <FileSpreadsheet className="w-4 h-4 text-emerald-400" />
              <div>
                <div className="font-semibold text-slate-100">Import Screener Excel (.xlsx)</div>
                <div className="text-slate-400">Company export (P&L, Quarters, BS, Cash Flow)</div>
              </div>
              <input
                type="file"
                accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                onChange={handleXlsxUpload}
                disabled={uploading}
                className="hidden"
              />
            </label>
          </div>

          <div className="flex flex-wrap gap-2 items-center pt-1">
            <input
              type="url"
              value={screenerUrlInput}
              onChange={(e) => setScreenerUrlInput(e.target.value)}
              placeholder="https://www.screener.in/company/SYMBOL/consolidated/"
              className="flex-1 min-w-[240px] bg-[#0a0f1c] border border-slate-700 rounded px-3 py-1.5 text-xs text-slate-100 font-mono"
            />
            <button
              type="button"
              onClick={saveUrlAssociation}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-100 rounded"
            >
              <Link2 className="w-3.5 h-3.5" />
              Associate URL
            </button>
            <button
              type="button"
              onClick={runOptionalPublicFetch}
              disabled={uploading}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-sky-300 rounded"
              title="Optional rate-limited public page check (Unofficial)"
            >
              <Globe className="w-3.5 h-3.5" />
              Optional Public Check
            </button>
          </div>

          {statusMsg && (
            <div
              className={`p-3 rounded border text-xs ${
                statusMsg.type === 'ok'
                  ? 'bg-emerald-950/40 border-emerald-800 text-emerald-200'
                  : 'bg-rose-950/40 border-rose-800 text-rose-200'
              }`}
            >
              {statusMsg.text}
            </div>
          )}
        </div>

        {/* Last Data Update & Missing Data Audit */}
        <div className="bg-[#0f1626] border border-slate-800 rounded-lg p-5 space-y-3 text-xs">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-sm font-semibold text-slate-100">Data Completeness & Audit</h2>
            <span className="font-mono text-slate-400">{importedCompanies.length} imported</span>
          </div>
          <div className="space-y-1.5 font-mono text-[11px]">
            <div className="flex justify-between">
              <span className="text-slate-400 font-sans">ISIN / BSE Code</span>
              <span className="text-slate-200">
                {meta.isin || '—'} · {meta.bse_code || '—'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400 font-sans">Last Data Update</span>
              <span className="text-slate-200">
                {companyData?.imported_at ? formatISTTime(companyData.imported_at) : 'Not Imported'}
              </span>
            </div>
          </div>

          <div className="pt-2 border-t border-slate-800">
            <div className="text-slate-300 font-semibold mb-1.5">Missing Financial Fields ({missing.length})</div>
            {missing.length === 0 ? (
              <div className="text-emerald-400">All core Screener statements & ratios present.</div>
            ) : (
              <ul className="space-y-1 text-amber-300/90 list-disc list-inside">
                {missing.slice(0, 6).map((m) => (
                  <li key={m}>{m}</li>
                ))}
              </ul>
            )}
          </div>

          {importedCompanies.length > 0 && (
            <div className="pt-2 border-t border-slate-800">
              <div className="text-slate-400 mb-1.5">Recently Imported Companies</div>
              <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto">
                {importedCompanies.slice(0, 12).map((c) => (
                  <button
                    key={c.stock_id}
                    type="button"
                    onClick={() => onSelectSymbol(c.symbol, 'screener')}
                    className={`px-2 py-1 rounded font-mono text-[11px] border ${
                      c.symbol === symbol
                        ? 'bg-amber-400/15 border-amber-400/50 text-amber-300'
                        : 'bg-[#0a0f1c] border-slate-800 text-slate-300 hover:border-slate-600'
                    }`}
                  >
                    {c.symbol}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 9 Screener Data Center Views Navigation */}
      <div className="flex flex-wrap gap-1 p-1 bg-[#0f1626] border border-slate-800 rounded-lg">
        {(
          [
            ['company', 'Company Data & Order Book'],
            ['ratios', 'Financial Ratios'],
            ['quarters', `Quarterly Results (${quarters.length})`],
            ['annual', `Annual Financials (${pnl.length})`],
            ['balance', `Balance Sheet (${bs.length})`],
            ['cashflow', `Cash Flow (${cf.length})`],
            ['shareholding', `Shareholding (${sh.length})`],
            ['peers', `Peer Comparison (${peers.length})`],
            ['screens', `Imported Stock Screens (${screens.length})`],
          ] as [ScreenerSubTab, string][]
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setSubTab(id)}
            className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
              subTab === id ? 'bg-slate-800 text-slate-100' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Active Data View */}
      {loading && !companyData ? (
        <div className="h-48 bg-[#0f1626] border border-slate-800 rounded-lg animate-pulse" />
      ) : subTab === 'company' ? (
        <form onSubmit={saveBusinessNotes} className="bg-[#0f1626] border border-slate-800 rounded-lg p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-sm font-semibold text-slate-100">
              Company Qualitative & Order Book Intelligence ({symbol})
            </h2>
            <button
              type="button"
              onClick={() => onSelectSymbol(symbol, 'fundamental')}
              className="px-3 py-1.5 text-xs font-semibold bg-amber-400 text-slate-950 rounded hover:bg-amber-300"
            >
              Run Fundamental AI Evaluation →
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
            <div>
              <label className="block text-slate-400 mb-1">Order Book Size (₹ Crores)</label>
              <input
                type="number"
                step="any"
                value={notesForm.order_book_cr}
                onChange={(e) => setNotesForm({ ...notesForm, order_book_cr: e.target.value })}
                placeholder="e.g. 2400"
                className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-3 py-1.5 font-mono text-slate-100"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Recent Order Inflow (₹ Crores)</label>
              <input
                type="number"
                step="any"
                value={notesForm.order_inflow_cr}
                onChange={(e) => setNotesForm({ ...notesForm, order_inflow_cr: e.target.value })}
                placeholder="e.g. 650"
                className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-3 py-1.5 font-mono text-slate-100"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Execution Timeline</label>
              <input
                type="text"
                value={notesForm.order_execution_timeline}
                onChange={(e) => setNotesForm({ ...notesForm, order_execution_timeline: e.target.value })}
                placeholder="e.g. 18-24 months"
                className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-3 py-1.5 text-slate-100"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Customer Concentration Risk</label>
              <input
                type="text"
                value={notesForm.customer_concentration}
                onChange={(e) => setNotesForm({ ...notesForm, customer_concentration: e.target.value })}
                placeholder="e.g. Top 5 clients = 48% of revenue"
                className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-3 py-1.5 text-slate-100"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Industry Outlook</label>
              <input
                type="text"
                value={notesForm.industry_outlook}
                onChange={(e) => setNotesForm({ ...notesForm, industry_outlook: e.target.value })}
                placeholder="e.g. Grid capex & solar EPC tailwind"
                className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-3 py-1.5 text-slate-100"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Competitive Position / Moat</label>
              <input
                type="text"
                value={notesForm.competitive_position}
                onChange={(e) => setNotesForm({ ...notesForm, competitive_position: e.target.value })}
                placeholder="e.g. Approved PGCIL / Defence vendor"
                className="w-full bg-[#0a0f1c] border border-slate-700 rounded px-3 py-1.5 text-slate-100"
              />
            </div>
          </div>
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={savingNotes}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-100 rounded"
            >
              <Save className="w-3.5 h-3.5" />
              {savingNotes ? 'Saving...' : 'Save Order Book & Business Notes'}
            </button>
          </div>
        </form>
      ) : subTab === 'ratios' ? (
        <div className="bg-[#0f1626] border border-slate-800 rounded-lg p-5">
          <h2 className="font-display text-sm font-semibold text-slate-100 mb-4">Imported Screener Financial Ratios</h2>
          {Object.keys(ratios).length === 0 ? (
            <div className="text-xs text-slate-400">No ratios imported yet for {symbol}.</div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 text-xs font-mono">
              {Object.entries(ratios).map(([k, v]) => (
                <div key={k} className="bg-[#0a0f1c] border border-slate-800 rounded p-3">
                  <div className="font-sans text-slate-400 capitalize">{k.replace(/_/g, ' ')}</div>
                  <div className="text-sm font-semibold text-slate-100 mt-1 tabular-nums">
                    {typeof v === 'number'
                      ? k.includes('cr')
                        ? formatCrores(v)
                        : k.includes('inr')
                        ? formatINR(v)
                        : k.includes('pct')
                        ? `${v.toFixed(2)}%`
                        : v.toFixed(2)
                      : String(v)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : subTab === 'quarters' ? (
        <div className="bg-[#0f1626] border border-slate-800 rounded-lg overflow-hidden">
          {renderDynamicStatementTable(quarters, 'No Quarterly Results imported yet.')}
        </div>
      ) : subTab === 'annual' ? (
        <div className="bg-[#0f1626] border border-slate-800 rounded-lg overflow-hidden">
          {renderDynamicStatementTable(pnl, 'No Annual Profit & Loss statement imported yet.')}
        </div>
      ) : subTab === 'balance' ? (
        <div className="bg-[#0f1626] border border-slate-800 rounded-lg overflow-hidden">
          {renderDynamicStatementTable(bs, 'No Balance Sheet imported yet.')}
        </div>
      ) : subTab === 'cashflow' ? (
        <div className="bg-[#0f1626] border border-slate-800 rounded-lg overflow-hidden">
          {renderDynamicStatementTable(cf, 'No Cash Flow statement imported yet.')}
        </div>
      ) : subTab === 'shareholding' ? (
        <div className="bg-[#0f1626] border border-slate-800 rounded-lg overflow-hidden">
          {renderDynamicStatementTable(sh, 'No Shareholding Pattern table imported yet.')}
        </div>
      ) : subTab === 'peers' ? (
        <div className="bg-[#0f1626] border border-slate-800 rounded-lg overflow-hidden">
          {peers.length === 0 ? (
            <div className="p-6 text-center text-xs text-slate-400">
              Import additional companies or a multi-company CSV stock screen in this sector ({meta.sector}) to view Screener peers.
            </div>
          ) : (
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400 font-sans">
                  <th className="text-left px-4 py-2.5">Symbol</th>
                  <th className="text-left px-4 py-2.5">Company</th>
                  <th className="text-right px-4 py-2.5">Mkt Cap</th>
                  <th className="text-right px-4 py-2.5">P/E</th>
                  <th className="text-right px-4 py-2.5">ROCE %</th>
                  <th className="text-right px-4 py-2.5">ROE %</th>
                  <th className="text-right px-4 py-2.5">OPM %</th>
                </tr>
              </thead>
              <tbody>
                {peers.map((p) => (
                  <tr
                    key={p.symbol}
                    onClick={() => onSelectSymbol(p.symbol, 'screener')}
                    className="border-b border-slate-800/60 hover:bg-slate-800/40 cursor-pointer"
                  >
                    <td className="px-4 py-2.5 font-semibold text-amber-300">{p.symbol}</td>
                    <td className="px-4 py-2.5 font-sans text-slate-200">{p.company_name}</td>
                    <td className="px-4 py-2.5 text-right">{formatCrores(p.market_cap_cr)}</td>
                    <td className="px-4 py-2.5 text-right">{p.pe ?? '—'}</td>
                    <td className="px-4 py-2.5 text-right">{p.roce_pct ? `${p.roce_pct}%` : '—'}</td>
                    <td className="px-4 py-2.5 text-right">{p.roe_pct ? `${p.roe_pct}%` : '—'}</td>
                    <td className="px-4 py-2.5 text-right">{p.opm_pct ? `${p.opm_pct}%` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          {screens.length === 0 ? (
            <div className="bg-[#0f1626] border border-slate-800 rounded-lg p-6 text-center text-xs text-slate-400">
              No Screener.in stock screens imported yet. Upload any exported Screener CSV file above.
            </div>
          ) : (
            screens.map((scr) => (
              <div key={scr.screen_id} className="bg-[#0f1626] border border-slate-800 rounded-lg overflow-hidden">
                <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between text-xs">
                  <span className="font-display font-semibold text-sm text-slate-100">
                    {scr.screen_name} ({scr.row_count} companies)
                  </span>
                  <span className="text-slate-400 font-mono">Imported {formatISTTime(scr.imported_at)}</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs font-mono">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400 font-sans">
                        <th className="text-left px-4 py-2">Symbol</th>
                        <th className="text-left px-4 py-2">Company</th>
                        <th className="text-right px-4 py-2">CMP</th>
                        <th className="text-right px-4 py-2">Mkt Cap</th>
                        <th className="text-right px-4 py-2">P/E</th>
                        <th className="text-right px-4 py-2">ROCE %</th>
                        <th className="text-right px-4 py-2">ROE %</th>
                        <th className="text-right px-4 py-2">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(scr.rows || []).map((r: any, idx: number) => (
                        <tr key={idx} className="border-b border-slate-800/60 hover:bg-slate-800/40">
                          <td className="px-4 py-2 font-semibold text-amber-300">{r.symbol}</td>
                          <td className="px-4 py-2 font-sans text-slate-200">{r.company_name}</td>
                          <td className="px-4 py-2 text-right">{formatINR(r.cmp_inr)}</td>
                          <td className="px-4 py-2 text-right">{formatCrores(r.market_cap_cr)}</td>
                          <td className="px-4 py-2 text-right">{r.pe ?? '—'}</td>
                          <td className="px-4 py-2 text-right">{r.roce_pct ? `${r.roce_pct}%` : '—'}</td>
                          <td className="px-4 py-2 text-right">{r.roe_pct ? `${r.roe_pct}%` : '—'}</td>
                          <td className="px-4 py-2 text-right">
                            <button
                              type="button"
                              onClick={() => onSelectSymbol(r.symbol, 'fundamental')}
                              className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-100 rounded font-sans"
                            >
                              Analyse
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};
