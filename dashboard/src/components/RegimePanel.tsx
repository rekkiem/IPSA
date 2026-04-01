// components/RegimePanel.tsx
'use client';
import { RegimeData } from '@/lib/types';
import { regimeBg } from '@/lib/data';

export function RegimePanel({ regime }: { regime: RegimeData }) {
  const emoji = { BULL: '🐂', BEAR: '🐻', NEUTRAL: '⚖️' }[regime.regime] ?? '⚖️';
  const badgeCls = regimeBg(regime.regime);
  const mlBadge = regime.regime_ml
    ? { BULL: '🐂', BEAR: '🐻', NEUTRAL: '⚖️' }[regime.regime_ml] ?? ''
    : '';

  return (
    <div className="metric-card">
      <p style={{ fontSize: '0.72rem', color: 'var(--muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
        Régimen IPSA
      </p>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontSize: '1.1rem', fontWeight: 700, padding: '4px 14px', borderRadius: 20, border: '1px solid', ...parseBadgeCls(badgeCls) }}>
          {emoji} {regime.regime}
        </span>
        {regime.regime_ml && (
          <span style={{ fontSize: '0.78rem', color: 'var(--muted)', background: 'var(--surface)', padding: '3px 8px', borderRadius: 10 }}>
            🤖 {mlBadge} {regime.regime_ml}
            {regime.regime_prob_bull != null && ` (${(regime.regime_prob_bull * 100).toFixed(0)}%)`}
          </span>
        )}
      </div>
      {regime.ipsa_momentum_3m != null && (
        <p style={{ marginTop: 8, fontSize: '0.82rem', color: regime.ipsa_momentum_3m > 0 ? 'var(--green)' : 'var(--red)' }}>
          Momentum 3M: {regime.ipsa_momentum_3m > 0 ? '+' : ''}{regime.ipsa_momentum_3m.toFixed(1)}%
        </p>
      )}
    </div>
  );
}

function parseBadgeCls(cls: string): React.CSSProperties {
  if (cls.includes('green')) return { borderColor: 'rgba(0,255,136,0.3)', color: '#00ff88', background: 'rgba(0,255,136,0.1)' };
  if (cls.includes('red'))   return { borderColor: 'rgba(255,77,109,0.3)', color: '#ff4d6d', background: 'rgba(255,77,109,0.1)' };
  return { borderColor: 'rgba(255,209,102,0.3)', color: '#ffd166', background: 'rgba(255,209,102,0.1)' };
}

export default RegimePanel;
