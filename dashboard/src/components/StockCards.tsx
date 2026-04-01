// components/StockCards.tsx
'use client';
import { StockEntry } from '@/lib/types';
import { fmtPct, fmtCLP, fmtNum } from '@/lib/data';

export default function StockCards({ top5 }: { top5: StockEntry[] }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 16 }}>
      {top5.map((s, i) => (
        <StockCard key={s.ticker} stock={s} rank={i + 1} />
      ))}
    </div>
  );
}

function StockCard({ stock: s, rank }: { stock: StockEntry; rank: number }) {
  const signalStyle = parseBadge(s.signal);
  const spreadPct = s.spread != null ? s.spread * 100 : null;

  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 12,
      padding: 20,
      display: 'flex',
      flexDirection: 'column',
      gap: 14,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{
          width: 30, height: 30, borderRadius: '50%',
          background: 'var(--border)', color: 'var(--cyan)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontWeight: 700, fontSize: '0.85rem', flexShrink: 0,
        }}>
          {rank}
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={{ fontWeight: 700, fontSize: '1rem' }}>{s.ticker}</span>
            <span style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>{s.name}</span>
          </div>
          <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--cyan)', marginTop: 2 }}>
            {fmtCLP(s.current_price)}
          </div>
        </div>
        <span style={{
          ...signalStyle, padding: '4px 10px', borderRadius: 10,
          fontSize: '0.75rem', fontWeight: 600, border: '1px solid', whiteSpace: 'nowrap',
        }}>
          {s.signal}
        </span>
      </div>

      {/* Score bar */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--muted)', marginBottom: 4 }}>
          <span>Score Unificado</span>
          <span style={{ color: 'var(--cyan)', fontWeight: 700 }}>{s.score.toFixed(4)}</span>
        </div>
        <div style={{ height: 6, background: 'var(--surface2)', borderRadius: 3 }}>
          <div style={{
            height: '100%', borderRadius: 3,
            width: `${Math.min(s.score * 100, 100)}%`,
            background: 'linear-gradient(90deg, var(--cyan), var(--purple))',
          }} />
        </div>
      </div>

      {/* Factor breakdown */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
        {[
          { label: '📈 Dividendos', value: s.factor_dividend, weight: '40%' },
          { label: '🏆 Calidad',    value: s.factor_quality,  weight: '25%' },
          { label: '⚡ Momentum',   value: s.factor_momentum, weight: '20%' },
          { label: '🛡️ Riesgo',    value: s.factor_risk,     weight: '15%' },
        ].map(({ label, value, weight }) => (
          <div key={label} style={{ background: 'var(--surface2)', borderRadius: 6, padding: '8px 10px' }}>
            <div style={{ fontSize: '0.7rem', color: 'var(--muted)', marginBottom: 2 }}>
              {label} <span style={{ opacity: 0.6 }}>({weight})</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ flex: 1, height: 4, background: 'var(--border)', borderRadius: 2 }}>
                <div style={{
                  height: '100%', borderRadius: 2,
                  width: `${Math.min((value ?? 0) * 100, 100)}%`,
                  background: scoreColor(value),
                }} />
              </div>
              <span style={{ fontSize: '0.78rem', fontWeight: 600, color: scoreColor(value) }}>
                {(value ?? 0).toFixed(2)}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Métricas clave */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
        <Metric label="DY" value={fmtPct(s.dividend_yield)} />
        <Metric label="Spread" value={spreadPct != null ? `${spreadPct >= 0 ? '+' : ''}${spreadPct.toFixed(1)}%` : 'N/D'} color={spreadPct != null && spreadPct >= 0 ? 'var(--green)' : 'var(--red)'} />
        <Metric label="ROE" value={fmtPct(s.roe)} />
        <Metric label="D/E" value={fmtNum(s.debt_to_equity)} />
        <Metric label="RSI" value={fmtNum(s.rsi, 0)} color={rsiColor(s.rsi)} />
        <Metric label="Sharpe" value={fmtNum(s.sharpe_ratio)} />
      </div>

      {/* Momentum bars */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <MomBar label="Momentum 3M" value={s.momentum_3m} />
        <MomBar label="Momentum 6M" value={s.momentum_6m} />
      </div>

      {/* Thesis */}
      <div style={{
        background: 'var(--surface2)', borderRadius: 6, padding: '10px 12px',
        borderLeft: '3px solid var(--border)', fontSize: '0.78rem',
        color: 'var(--muted)', lineHeight: 1.6,
      }}>
        {s.thesis}
      </div>

      {/* ML prediction */}
      {s.predicted_return_21d != null && (
        <div style={{
          background: 'rgba(168,85,247,0.08)', border: '1px solid rgba(168,85,247,0.2)',
          borderRadius: 6, padding: '8px 12px', fontSize: '0.8rem',
        }}>
          <span style={{ color: 'var(--muted)' }}>🤖 ML (21d): </span>
          <span style={{ fontWeight: 700, color: s.predicted_return_21d > 0 ? 'var(--green)' : 'var(--red)' }}>
            {s.predicted_return_21d > 0 ? '+' : ''}{s.predicted_return_21d.toFixed(1)}%
          </span>
          <span style={{ color: 'var(--muted)', marginLeft: 6 }}>
            ({s.confidence}) — {s.signal_ml}
          </span>
        </div>
      )}

      {/* Entry zone */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)',
        gap: 8, background: 'var(--surface2)', borderRadius: 8, padding: 12,
        fontSize: '0.78rem',
      }}>
        <div>
          <div style={{ color: 'var(--muted)', marginBottom: 2 }}>🎯 Entrada</div>
          <div style={{ fontWeight: 600, fontSize: '0.82rem' }}>
            {fmtCLP(s.entry_low)}<br />
            <span style={{ color: 'var(--muted)' }}>–</span> {fmtCLP(s.entry_high)}
          </div>
        </div>
        <div>
          <div style={{ color: 'var(--muted)', marginBottom: 2 }}>🛑 Stop Loss</div>
          <div style={{ fontWeight: 600, color: 'var(--red)', fontSize: '0.82rem' }}>
            {fmtCLP(s.stop_loss)}
          </div>
        </div>
        <div>
          <div style={{ color: 'var(--muted)', marginBottom: 2 }}>⏱ Horizonte</div>
          <div style={{ fontWeight: 600, fontSize: '0.78rem' }}>{s.horizon ?? 'N/D'}</div>
        </div>
      </div>

      {/* Weight */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.82rem' }}>
        <span style={{ color: 'var(--muted)' }}>Peso en portafolio</span>
        <span style={{ fontWeight: 700, color: 'var(--cyan)' }}>{s.weight_pct?.toFixed(1)}%</span>
      </div>
    </div>
  );
}

function Metric({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ background: 'var(--surface2)', borderRadius: 6, padding: '6px 8px' }}>
      <div style={{ fontSize: '0.68rem', color: 'var(--muted)', marginBottom: 1 }}>{label}</div>
      <div style={{ fontWeight: 600, fontSize: '0.85rem', color: color ?? 'var(--text)' }}>{value}</div>
    </div>
  );
}

function MomBar({ label, value }: { label: string; value: number | null }) {
  const v = value ?? 0;
  const color = v >= 0 ? 'var(--green)' : 'var(--red)';
  const pct = Math.min(Math.abs(v) / 30 * 50, 50); // max 30% → 50% bar

  return (
    <div style={{ background: 'var(--surface2)', borderRadius: 6, padding: '6px 8px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.68rem', color: 'var(--muted)', marginBottom: 4 }}>
        <span>{label}</span>
        <span style={{ color, fontWeight: 600 }}>{v >= 0 ? '+' : ''}{v.toFixed(1)}%</span>
      </div>
      <div style={{ height: 4, background: 'var(--border)', borderRadius: 2, position: 'relative' }}>
        <div style={{
          position: 'absolute', height: '100%', borderRadius: 2,
          background: color,
          left: v >= 0 ? '50%' : `${50 - pct}%`,
          width: `${pct}%`,
        }} />
        <div style={{
          position: 'absolute', left: '50%', top: -1,
          width: 2, height: 6, background: 'var(--muted)', transform: 'translateX(-50%)',
        }} />
      </div>
    </div>
  );
}

function scoreColor(v: number | null) {
  const n = v ?? 0;
  if (n >= 0.65) return 'var(--green)';
  if (n >= 0.45) return 'var(--cyan)';
  if (n >= 0.30) return 'var(--yellow)';
  return 'var(--red)';
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
