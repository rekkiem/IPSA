// app/page.tsx — Server Component
// Lee el reporte via server-data.ts (Node.js fs, nunca bundleado para cliente)
import { fetchLatestReport } from '@/lib/server-data';
import { getMockReport }     from '@/lib/mock-data';
import type { DailyReport }  from '@/lib/types';

import MacroPanel     from '@/components/MacroPanel';
import RegimePanel    from '@/components/RegimePanel';
import Top5Table      from '@/components/Top5Table';
import StockCards     from '@/components/StockCards';
import PortfolioChart from '@/components/PortfolioChart';
import ScoreChart     from '@/components/ScoreChart';
import RankedAllTable from '@/components/RankedAllTable';
import HistoryPanel   from '@/components/HistoryPanel';
import AlertBanner    from '@/components/AlertBanner';

// Regenerar cada 5 minutos (ISR), nunca cachear como estático
export const dynamic    = 'force-dynamic';
export const revalidate = 300;

export default async function DashboardPage() {
  const report: DailyReport = await fetchLatestReport().catch(() => getMockReport());
  const { date, macro, regime, changes, top5, ranked_all } = report;

  return (
    <main className="min-h-screen p-4 md:p-6 lg:p-8 max-w-[1600px] mx-auto">

      {/* HEADER */}
      <header className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-3">
            <span className="text-3xl">🇨🇱</span>
            <h1 className="text-2xl font-bold" style={{ color: 'var(--cyan)' }}>
              IPSA Agent
            </h1>
            <span style={{
              padding: '2px 10px', fontSize: '0.78rem', borderRadius: 20,
              border: '1px solid var(--border)', color: 'var(--muted)',
              background: 'var(--surface2)',
            }}>
              v2.1
            </span>
          </div>
          <p style={{ color: 'var(--muted)', fontSize: '0.85rem', marginTop: 4 }}>
            Gestor Autónomo de Inversión — Análisis Cuantitativo del Mercado Chileno
          </p>
        </div>
        <span style={{
          background: 'var(--surface2)', border: '1px solid var(--border)',
          borderRadius: 20, padding: '6px 16px', fontSize: '0.85rem', color: 'var(--muted)',
        }}>
          📅 {date}
        </span>
      </header>

      {/* ALERTA CAMBIO TOP 5 */}
      {changes.changed && <AlertBanner changes={changes} />}

      {/* MACRO + RÉGIMEN */}
      <section className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
        <MacroPanel macro={macro} />
        <RegimePanel regime={regime} />
      </section>

      {/* TOP 5 o estado vacío */}
      {top5.length > 0 ? (
        <>
          <section className="card mb-6">
            <h2 style={{ color: 'var(--cyan)', fontSize: '1.1rem', fontWeight: 600, marginBottom: 16 }}>
              🔥 Top 5 IPSA Hoy
            </h2>
            <Top5Table top5={top5} />
          </section>

          <section className="grid grid-cols-1 xl:grid-cols-2 gap-4 mb-6">
            <div className="card">
              <h2 style={{ color: 'var(--cyan)', fontSize: '0.9rem', fontWeight: 600, marginBottom: 12 }}>
                ⚖️ Asignación de Portafolio
              </h2>
              <PortfolioChart top5={top5} />
            </div>
            <div className="card">
              <h2 style={{ color: 'var(--cyan)', fontSize: '0.9rem', fontWeight: 600, marginBottom: 12 }}>
                📊 Score por Factor
              </h2>
              <ScoreChart top5={top5} />
            </div>
          </section>

          <section className="mb-6">
            <h2 style={{ color: 'var(--cyan)', fontSize: '1.1rem', fontWeight: 600, marginBottom: 16 }}>
              🧠 Tesis y Timing de Entrada
            </h2>
            <StockCards top5={top5} />
          </section>
        </>
      ) : (
        <section className="card mb-6" style={{
          textAlign: 'center', padding: '48px 24px',
          border: '1px solid rgba(255,209,102,0.2)',
          background: 'rgba(255,209,102,0.04)',
        }}>
          <div style={{ fontSize: '2rem', marginBottom: 12 }}>⏳</div>
          <h2 style={{ color: 'var(--yellow)', marginBottom: 8 }}>Análisis pendiente</h2>
          <p style={{ color: 'var(--muted)', fontSize: '0.9rem' }}>
            El agente aún no ha ejecutado hoy o no hay acciones elegibles.<br />
            Ejecuta: <code style={{ color: 'var(--cyan)' }}>python main_v2.py --no-ml</code>
          </p>
        </section>
      )}

      {/* RANKING COMPLETO */}
      <section className="card mb-6">
        <h2 style={{ color: 'var(--cyan)', fontSize: '1.1rem', fontWeight: 600, marginBottom: 16 }}>
          📊 Ranking Completo — Universo IPSA
        </h2>
        <RankedAllTable ranked={ranked_all.length > 0 ? ranked_all : top5} />
      </section>

      {/* HISTORIAL */}
      <section className="card mb-6">
        <h2 style={{ color: 'var(--cyan)', fontSize: '1.1rem', fontWeight: 600, marginBottom: 16 }}>
          📚 Historial de Decisiones
        </h2>
        <HistoryPanel />
      </section>

      <footer style={{
        textAlign: 'center', marginTop: 32, paddingBottom: 24,
        color: 'var(--muted)', fontSize: '0.78rem',
        borderTop: '1px solid var(--border)', paddingTop: 16,
      }}>
        IPSA Agent v2.1 — Solo para fines informativos. No constituye asesoramiento financiero.
        <br />USD/CLP: {macro.usdclp?.toLocaleString('es-CL') ?? 'N/D'} · Actualización ISR cada 5 min
      </footer>
    </main>
  );
}
