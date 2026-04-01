// lib/data.ts
// SOLO formatters y utilidades puras — sin imports de Node.js
// Seguro para incluir en cualquier componente (cliente o servidor)

export { getMockReport } from './mock-data';
export type { DailyReport } from './types';

// ── Formatters ──────────────────────────────────────────────────

export function fmtPct(v: number | null | undefined, d = 1): string {
  if (v == null || (typeof v === 'number' && isNaN(v))) return 'N/D';
  return `${(v * 100).toFixed(d)}%`;
}

export function fmtCLP(v: number | null | undefined): string {
  if (v == null || (typeof v === 'number' && isNaN(v))) return 'N/D';
  return `$${v.toLocaleString('es-CL', { maximumFractionDigits: 0 })}`;
}

export function fmtNum(v: number | null | undefined, d = 2): string {
  if (v == null || (typeof v === 'number' && isNaN(v))) return 'N/D';
  return v.toFixed(d);
}

export function fmtPctDirect(v: number | null | undefined, d = 1): string {
  if (v == null || (typeof v === 'number' && isNaN(v))) return 'N/D';
  return `${v.toFixed(d)}%`;
}

export function signalBg(signal: string): string {
  if (signal.includes('COMPRAR')) return 'bg-green/10 border-green/30 text-green';
  if (signal.includes('ESPERAR')) return 'bg-yellow/10 border-yellow/30 text-yellow';
  return 'bg-red/10 border-red/30 text-red';
}

export function regimeBg(regime: string): string {
  if (regime === 'BULL') return 'bg-green/10 border-green/30 text-green';
  if (regime === 'BEAR') return 'bg-red/10 border-red/30 text-red';
  return 'bg-yellow/10 border-yellow/30 text-yellow';
}
