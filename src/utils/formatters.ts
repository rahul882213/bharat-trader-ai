export function formatINR(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const sign = value < 0 ? '-' : '';
  const abs = Math.abs(value);
  return `${sign}₹${abs.toLocaleString('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`;
}

export function formatCrores(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `₹${value.toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} Cr`;
}

export function formatPct(value: number | null | undefined, showPlus = true): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const prefix = showPlus && value > 0 ? '+' : '';
  return `${prefix}${value.toFixed(2)}%`;
}

export function formatVolume(vol: number | null | undefined): string {
  if (vol === null || vol === undefined || Number.isNaN(vol)) return '—';
  if (vol >= 1e7) return `${(vol / 1e7).toFixed(2)} Cr`;
  if (vol >= 1e5) return `${(vol / 1e5).toFixed(2)} L`;
  if (vol >= 1e3) return `${(vol / 1e3).toFixed(1)} K`;
  return String(vol);
}

export function formatISTTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString('en-IN', {
      timeZone: 'Asia/Kolkata',
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }) + ' IST';
  } catch {
    return iso;
  }
}
