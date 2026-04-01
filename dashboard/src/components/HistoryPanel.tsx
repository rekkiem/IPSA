// components/HistoryPanel.tsx
'use client';
import { useEffect, useState } from 'react';

interface HistoryEntry {
  date:     string;
  tickers:  string[];
  regime:   { regime: string };
  macro:    { risk_free_rate: number; usdclp: number | null };
}

export default function HistoryPanel() {
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/history')
      .then(r => r.json())
      .then(data => { setHistory(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div style={{ color: 'var(--muted)', fontSize: '0.85rem', padding: '20px 0', textAlign: 'center' }}>
        Cargando historial...
      </div>
    );
  }

  if (history.length === 0) {
    return (
      <div style={{ color: 'var(--muted)', fontSize: '0.85rem', padding: '20px 0', textAlign: 'center' }}>
        📭 Sin historial aún. Ejecuta el agente al menos una vez.
      </div>
    );
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <table>
        <thead>
          <tr>
            {['Fecha', 'Régimen', 'TPM', 'USD/CLP', 'Top 5 Seleccionado'].map(h => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {history.map((entry, i) => {
            const regime = entry.regime?.regime ?? 'N/D';
            const regColor = regime === 'BULL' ? 'var(--green)' : regime === 'BEAR' ? 'var(--red)' : 'var(--yellow)';
            const emoji = { BULL: '🐂', BEAR: '🐻', NEUTRAL: '⚖️' }[regime] ?? '';
            return (
              <tr key={i}>
                <td style={{ fontFamily: 'monospace', fontSize: '0.82rem', color: 'var(--muted)' }}>
                  {entry.date}
                </td>
                <td>
                  <span style={{ color: regColor, fontWeight: 600 }}>
                    {emoji} {regime}
                  </span>
                </td>
                <td style={{ fontSize: '0.82rem' }}>
                  {entry.macro?.risk_free_rate ? `${(entry.macro.risk_free_rate * 100).toFixed(2)}%` : 'N/D'}
                </td>
                <td style={{ fontSize: '0.82rem' }}>
                  {entry.macro?.usdclp ? `$${entry.macro.usdclp.toLocaleString('es-CL', { maximumFractionDigits: 0 })}` : 'N/D'}
                </td>
                <td>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {(entry.tickers ?? []).map(t => (
                      <span key={t} style={{
                        background: 'var(--surface2)',
                        border: '1px solid var(--border)',
                        borderRadius: 6,
                        padding: '2px 8px',
                        fontSize: '0.75rem',
                        fontFamily: 'monospace',
                        color: 'var(--cyan)',
                      }}>
                        {t.replace('.SN', '')}
                      </span>
                    ))}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
