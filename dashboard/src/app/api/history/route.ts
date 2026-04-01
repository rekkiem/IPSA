// app/api/history/route.ts
import { NextResponse } from 'next/server';
import fs   from 'fs';
import path from 'path';

export async function GET() {
  try {
    const dir  = process.env.DATA_DIR ?? path.join(process.cwd(), '..', 'ipsa_agent', 'data');
    const file = path.join(dir, 'decisions_history.json');
    if (!fs.existsSync(file)) return NextResponse.json([]);
    const data = JSON.parse(fs.readFileSync(file, 'utf-8'));
    return NextResponse.json(Array.isArray(data) ? data.slice(-30).reverse() : []);
  } catch {
    return NextResponse.json([]);
  }
}
