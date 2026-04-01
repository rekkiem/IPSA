// components/ScoreChart.tsx
'use client';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, Cell,
} from 'recharts';
import { StockEntry } from '@/lib/types';

export default function ScoreChart({ top5 }: { top5: StockEntry[] }) {
  const data = top5.map((s) => ({
    name:       s.ticker.replace('.SN', ''),
    Dividendos: parseFloat(((s.factor_dividend ?? 0) * 0.40).toFixed(4)),
    Calidad:    parseFloat(((s.factor_quality  ?? 0) * 0.25).toFixed(4)),
    Momentum:   parseFloat(((s.factor_momentum ?? 0) * 0.20).toFixed(4)),
    Riesgo:     parseFloat(((s.factor_risk     ?? 0) * 0.15).toFixed(4)),
  }));

  const FACTOR_COLORS = {
    Dividendos: '#00d4ff',
    Calidad:    '#00ff88',
    Momentum:   '#a855f7',
    Riesgo:     '#ffd166',
  };

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} barSize={32} barGap={4}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e3a5f" vertical={false} />
        <XAxis
          dataKey="name"
          tick={{ fill: '#64748b', fontSize: 11 }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tick={{ fill: '#64748b', fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          domain={[0, 0.7]}
          tickFormatter={(v) => v.toFixed(2)}
        />
        <Tooltip
          contentStyle={{
            background: '#111827', border: '1px solid #1e3a5f',
            borderRadius: 8, fontSize: '0.82rem', color: '#e2e8f0',
          }}
          formatter={(v: number, name: string) => [
            `${(v * 100).toFixed(1)}% (peso ${name === 'Dividendos' ? '40%' : name === 'Calidad' ? '25%' : name === 'Momentum' ? '20%' : '15%'})`,
            name,
          ]}
        />
        <Legend
          iconType="square"
          iconSize={10}
          wrapperStyle={{ fontSize: '0.78rem', color: '#64748b' }}
        />
        {Object.entries(FACTOR_COLORS).map(([key, color]) => (
          <Bar key={key} dataKey={key} stackId="a" fill={color} radius={key === 'Riesgo' ? [4, 4, 0, 0] : [0, 0, 0, 0]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
