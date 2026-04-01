// components/MacroPanel.tsx
'use client';
import { MacroData } from '@/lib/types';
import { fmtNum, fmtPct } from '@/lib/data';

interface Props { macro: MacroData }

export default function MacroPanel({ macro }: Props) {
  const items = [
    { label: 'USD/CLP', value: macro.usdclp ? `$${macro.usdclp.toLocaleString('es-CL', { maximumFractionDigits: 2 })}` : 'N/D', color: 'var(--cyan)' },
    { label: 'TPM BCCh', value: fmtPct(macro.risk_free_rate), color: 'var(--yellow)' },
    { label: 'IPC Anual', value: fmtPct(macro.inflation), color: 'var(--purple)' },
  ];

  return (
    <>
      {items.map(({ label, value, color }) => (
        <div key={label} className="metric-card">
          <p style={{ fontSize: '0.72rem', color: 'var(--muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            {label}
          </p>
          <p style={{ fontSize: '1.4rem', fontWeight: 700, color }}>{value}</p>
        </div>
      ))}
    </>
  );
}
