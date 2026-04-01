// components/PortfolioChart.tsx
'use client';
import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { StockEntry } from '@/lib/types';

const COLORS = ['#00d4ff', '#00ff88', '#a855f7', '#ffd166', '#ff4d6d'];

export default function PortfolioChart({ top5 }: { top5: StockEntry[] }) {
  const data = top5.map((s) => ({
    name:  s.ticker.replace('.SN', ''),
    value: s.weight_pct ?? 0,
    score: s.score,
  }));
  const cash = Math.max(0, 100 - data.reduce((a, d) => a + d.value, 0));
  if (cash > 0) data.push({ name: 'CAJA', value: parseFloat(cash.toFixed(1)), score: 0 });

  return (
    <ResponsiveContainer width="100%" height={280}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={70}
          outerRadius={110}
          paddingAngle={3}
          dataKey="value"
        >
          {data.map((_, i) => (
            <Cell
              key={i}
              fill={i === data.length - 1 && data[i].name === 'CAJA'
                ? '#1e3a5f'
                : COLORS[i % COLORS.length]}
              stroke="transparent"
            />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            background: '#111827', border: '1px solid #1e3a5f',
            borderRadius: 8, fontSize: '0.82rem', color: '#e2e8f0',
          }}
          formatter={(v: number) => [`${v.toFixed(1)}%`, 'Peso']}
        />
        <Legend
          iconType="circle"
          iconSize={8}
          wrapperStyle={{ fontSize: '0.78rem', color: '#64748b' }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
