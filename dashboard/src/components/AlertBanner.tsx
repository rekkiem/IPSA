// components/AlertBanner.tsx
'use client';
import { ChangesData } from '@/lib/types';

export default function AlertBanner({ changes }: { changes: ChangesData }) {
  if (!changes.changed) return null;
  return (
    <div style={{
      background: 'rgba(255,209,102,0.08)',
      border: '1px solid rgba(255,209,102,0.25)',
      borderRadius: 10,
      padding: '12px 18px',
      marginBottom: 20,
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      fontSize: '0.88rem',
      color: '#ffd166',
    }}>
      <span style={{ fontSize: '1.1rem' }}>🚨</span>
      <div>
        <strong>Cambio en Top 5</strong>
        {changes.new_entries.length > 0 && (
          <span style={{ marginLeft: 12, color: '#00ff88' }}>
            ➕ Entran: {changes.new_entries.join(', ')}
          </span>
        )}
        {changes.exits.length > 0 && (
          <span style={{ marginLeft: 12, color: '#ff4d6d' }}>
            ➖ Salen: {changes.exits.join(', ')}
          </span>
        )}
      </div>
    </div>
  );
}
