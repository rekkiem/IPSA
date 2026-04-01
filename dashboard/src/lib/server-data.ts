// lib/server-data.ts
// Marcado 'use server' → Next.js NUNCA lo bundlea para el cliente
// Solo se ejecuta en Node.js (API routes, Server Components, page.tsx async)
'use server';

import fs   from 'fs';
import path from 'path';
import type { DailyReport } from './types';
import { getMockReport } from './mock-data';

/** Sanitiza NaN/Infinity residuales de Python antes de JSON.parse */
function sanitize(raw: string): string {
  return raw
    .replace(/:\s*NaN/g,       ': null')
    .replace(/:\s*Infinity/g,  ': null')
    .replace(/:\s*-Infinity/g, ': null');
}

function safeJsonParse(raw: string): any {
  try {
    return JSON.parse(sanitize(raw));
  } catch {
    return null;
  }
}

function getReportsDir(): string {
  return (
    process.env.REPORTS_DIR ??
    path.join(process.cwd(), '..', 'ipsa_agent', 'reports')
  );
}

function getDataDir(): string {
  return (
    process.env.DATA_DIR ??
    path.join(process.cwd(), '..', 'ipsa_agent', 'data')
  );
}

/** Lee el reporte JSON más reciente del agente Python */
export async function fetchLatestReport(): Promise<DailyReport> {
  try {
    const dir = getReportsDir();
    if (!fs.existsSync(dir)) return getMockReport();

    const files = fs
      .readdirSync(dir)
      .filter(f => f.startsWith('ipsa_data_') && f.endsWith('.json'))
      .sort()
      .reverse();

    if (!files.length) return getMockReport();

    const raw  = fs.readFileSync(path.join(dir, files[0]), 'utf-8');
    const data = safeJsonParse(raw);
    return data ?? getMockReport();
  } catch (e) {
    console.warn('[server-data] fetchLatestReport error:', e);
    return getMockReport();
  }
}

/** Lee el historial de decisiones del agente Python */
export async function fetchHistory(): Promise<any[]> {
  try {
    const file = path.join(getDataDir(), 'decisions_history.json');
    if (!fs.existsSync(file)) return [];
    const raw  = fs.readFileSync(file, 'utf-8');
    const data = safeJsonParse(raw);
    return Array.isArray(data) ? data.slice(-30).reverse() : [];
  } catch {
    return [];
  }
}
