// components/Top5Table.tsx
'use client';
import { StockEntry } from '@/lib/types';
import { fmtPct, fmtCLP, fmtNum, fmtPctDirect, signalBg } from '@/lib/data';

export default function Top5Table({ top5 }: { top5: StockEntry[] }) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table>
        <thead>
          <tr>
            {['#','Acción','Score','DY%','Spread','RSI','DD 6M','Vol Anual','ML 21d','Peso %','Señal'].map(h => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {top5.map((s, i) => {
            const spreadPct = s.spread != null ? s.spread * 100 : null;
            const ml = s.predicted_return_21d;
            const badgeStyle = parseBadge(s.signal);
            return (
              <tr key={s.ticker}>
                <td style={{ color: 'var(--muted)', fontWeight: 700 }}>{i + 1}</td>
                <td>
                  <div style={{ fontWeight: 700 }}>{s.ticker}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>{s.name}</div>
                </td>
                <td style={{ fontWeight: 700, color: 'var(--cyan)', fontFamily: 'monospace' }}>{s.score.toFixed(4)}</td>
                <td>{fmtPct(s.dividend_yield)}</td>
                <td style={{ color: spreadPct != null && spreadPct >= 0 ? 'var(--green)' : 'var(--red)' }}>
                  {spreadPct != null ? `${spreadPct >= 0 ? '+' : ''}${spreadPct.toFixed(1)}%` : 'N/D'}
                </td>
                <td style={{ color: rsiColor(s.rsi) }}>{fmtNum(s.rsi, 0)}</td>
                <td style={{ color: 'var(--red)' }}>{s.max_drawdown != null ? `${s.max_drawdown.toFixed(1)}%` : 'N/D'}</td>
                <td>{s.volatility_annual != null ? `${s.volatility_annual.toFixed(1)}%` : 'N/D'}</td>
                <td style={{ color: ml != null && ml > 0 ? 'var(--green)' : 'var(--red)' }}>
                  {ml != null ? `${ml > 0 ? '+' : ''}${ml.toFixed(1)}%` : '—'}
                  {s.confidence && <span style={{ fontSize: '0.7rem', color: 'var(--muted)', marginLeft: 4 }}>({s.confidence})</span>}
                </td>
                <td style={{ fontWeight: 700 }}>{s.weight_pct?.toFixed(1)}%</td>
                <td>
                  <span style={{ ...badgeStyle, padding: '3px 10px', borderRadius: 10, fontSize: '0.78rem', fontWeight: 600, border: '1px solid' }}>
                    {s.signal}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function rsiColor(rsi: number | null) {
  if (!rsi) return 'var(--text)';
  if (rsi > 70) return 'var(--red)';
  if (rsi < 35) return 'var(--yellow)';
  return 'var(--green)';
}

function parseBadge(signal: string): React.CSSProperties {
  if (signal.includes('COMPRAR')) return { color: '#00ff88', borderColor: 'rgba(0,255,136,0.3)', background: 'rgba(0,255,136,0.1)' };
  if (signal.includes('ESPERAR')) return { color: '#ffd166', borderColor: 'rgba(255,209,102,0.3)', background: 'rgba(255,209,102,0.1)' };
  return { color: '#ff4d6d', borderColor: 'rgba(255,77,109,0.3)', background: 'rgba(255,77,109,0.1)' };
}
