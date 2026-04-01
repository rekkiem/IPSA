// components/RankedAllTable.tsx
'use client';
import { useState } from 'react';
import { StockEntry } from '@/lib/types';
import { fmtPct, fmtNum } from '@/lib/data';

export default function RankedAllTable({ ranked }: { ranked: StockEntry[] }) {
  const [showExcluded, setShowExcluded] = useState(false);
  const display = showExcluded ? ranked : ranked.filter(s => !s.is_excluded);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <button
          onClick={() => setShowExcluded(v => !v)}
          style={{
            background: showExcluded ? 'rgba(255,77,109,0.15)' : 'var(--surface2)',
            border: '1px solid var(--border)',
            color: showExcluded ? '#ff4d6d' : 'var(--muted)',
            borderRadius: 8,
            padding: '5px 12px',
            fontSize: '0.78rem',
            cursor: 'pointer',
          }}
        >
          {showExcluded ? '🙈 Ocultar excluidas' : '👁 Mostrar excluidas'}
        </button>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              {['Rank', 'Ticker', 'Nombre', 'Score', 'Señal', 'DY%', 'RSI',
                'Mom 3M', 'Drawdown', 'Sharpe', 'Estado'].map(h => (
                <th key={h}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {display.map((s) => {
              const isExcl = s.is_excluded;
              const dy = s.dividend_yield != null ? s.dividend_yield * 100 : null;
              const mom3 = s.momentum_3m;
              const badge = parseBadge(s.signal);

              return (
                <tr key={s.ticker} style={{ opacity: isExcl ? 0.45 : 1 }}>
                  <td style={{ color: 'var(--muted)', fontWeight: 700 }}>{s.rank}</td>
                  <td style={{ fontWeight: 700, fontFamily: 'monospace', color: 'var(--cyan)' }}>{s.ticker}</td>
                  <td style={{ fontSize: '0.82rem', color: 'var(--muted)' }}>{s.name}</td>
                  <td style={{ fontFamily: 'monospace', fontWeight: 600 }}>{s.score.toFixed(4)}</td>
                  <td>
                    <span style={{
                      ...badge, padding: '2px 8px',
                      borderRadius: 8, fontSize: '0.72rem',
                      fontWeight: 600, border: '1px solid',
                    }}>
                      {s.signal}
                    </span>
                  </td>
                  <td>{dy != null ? `${dy.toFixed(1)}%` : 'N/D'}</td>
                  <td style={{ color: rsiColor(s.rsi) }}>{fmtNum(s.rsi, 0)}</td>
                  <td style={{ color: mom3 != null && mom3 >= 0 ? 'var(--green)' : 'var(--red)' }}>
                    {mom3 != null ? `${mom3 >= 0 ? '+' : ''}${mom3.toFixed(1)}%` : 'N/D'}
                  </td>
                  <td style={{ color: 'var(--red)' }}>
                    {s.max_drawdown != null ? `${s.max_drawdown.toFixed(1)}%` : 'N/D'}
                  </td>
                  <td>{fmtNum(s.sharpe_ratio)}</td>
                  <td>
                    {isExcl
                      ? <span style={{ color: '#ff4d6d', fontSize: '0.75rem' }}>
                          ⚠️ {s.kill_reasons?.[0]?.slice(0, 40) ?? 'Excluida'}
                        </span>
                      : <span style={{ color: 'var(--green)', fontSize: '0.78rem' }}>✓ Elegible</span>
                    }
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function parseBadge(signal: string): React.CSSProperties {
  if (signal.includes('COMPRAR')) return { color: '#00ff88', borderColor: 'rgba(0,255,136,0.3)', background: 'rgba(0,255,136,0.1)' };
  if (signal.includes('ESPERAR')) return { color: '#ffd166', borderColor: 'rgba(255,209,102,0.3)', background: 'rgba(255,209,102,0.1)' };
  return { color: '#ff4d6d', borderColor: 'rgba(255,77,109,0.3)', background: 'rgba(255,77,109,0.1)' };
}

function rsiColor(rsi: number | null) {
  if (!rsi) return 'var(--text)';
  if (rsi > 70) return 'var(--red)';
  if (rsi < 35) return 'var(--yellow)';
  return 'var(--green)';
}
