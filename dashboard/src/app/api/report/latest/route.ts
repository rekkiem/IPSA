// app/api/report/latest/route.ts
// Sirve el JSON más reciente al cliente (HistoryPanel, refetch manual)
// Sanitiza NaN residuales de Python antes de enviar

import { NextResponse } from 'next/server';
import fs   from 'fs';
import path from 'path';

function sanitize(raw: string): string {
  return raw
    .replace(/:\s*NaN/g,       ': null')
    .replace(/:\s*Infinity/g,  ': null')
    .replace(/:\s*-Infinity/g, ': null');
}

export async function GET() {
  try {
    const dir =
      process.env.REPORTS_DIR ??
      path.join(process.cwd(), '..', 'ipsa_agent', 'reports');

    if (!fs.existsSync(dir)) {
      return NextResponse.json({ error: 'Reports dir not found' }, { status: 404 });
    }

    const files = fs
      .readdirSync(dir)
      .filter(f => f.startsWith('ipsa_data_') && f.endsWith('.json'))
      .sort()
      .reverse();

    if (!files.length) {
      return NextResponse.json({ error: 'No reports yet' }, { status: 404 });
    }

    const raw  = fs.readFileSync(path.join(dir, files[0]), 'utf-8');
    const data = JSON.parse(sanitize(raw));

    return NextResponse.json(data, {
      headers: { 'Cache-Control': 'public, s-maxage=300, stale-while-revalidate=600' },
    });
  } catch (e) {
    console.error('[API /report/latest]', e);
    return NextResponse.json({ error: 'Internal error' }, { status: 500 });
  }
}
