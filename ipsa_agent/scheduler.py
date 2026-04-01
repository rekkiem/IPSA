"""
IPSA Agent - Scheduler Automatizado
Ejecuta el análisis diario a hora configurada (días hábiles).
Uso: python scheduler.py
"""

import logging
import os
import sys
import time
from datetime import datetime

logger = logging.getLogger("ipsa_agent.scheduler")


def is_business_day(dt: datetime) -> bool:
    """Verifica si es día hábil (L-V, sin feriados)."""
    # Lunes=0, Domingo=6
    if dt.weekday() >= 5:
        return False

    # Feriados Chile 2025-2026 (simplificado)
    HOLIDAYS = {
        # 2025
        (2025, 1, 1),   # Año Nuevo
        (2025, 4, 18),  # Viernes Santo
        (2025, 4, 19),  # Sábado Santo
        (2025, 5, 1),   # Día del Trabajo
        (2025, 5, 21),  # Glorias Navales
        (2025, 6, 20),  # Día de los Pueblos Originarios
        (2025, 6, 29),  # San Pedro y San Pablo
        (2025, 7, 16),  # Virgen del Carmen
        (2025, 8, 15),  # Asunción de la Virgen
        (2025, 9, 18),  # Independencia
        (2025, 9, 19),  # Glorias del Ejército
        (2025, 10, 12), # Encuentro dos Mundos
        (2025, 10, 31), # Día de las Iglesias Evangélicas
        (2025, 11, 1),  # Día de Todos los Santos
        (2025, 12, 8),  # Inmaculada Concepción
        (2025, 12, 25), # Navidad
        # 2026
        (2026, 1, 1),
        (2026, 4, 3),   # Viernes Santo 2026
        (2026, 4, 4),   # Sábado Santo 2026
        (2026, 5, 1),
        (2026, 5, 21),
        (2026, 9, 18),
        (2026, 9, 19),
        (2026, 12, 25),
    }

    return (dt.year, dt.month, dt.day) not in HOLIDAYS


def run_scheduler(
    run_hour:   int = 9,   # 09:00 AM (después de apertura Bolsa de Santiago)
    run_minute: int = 15,
    max_days:   int = None, # None = indefinido
):
    """
    Loop principal del scheduler.
    Ejecuta el pipeline diario en días hábiles a la hora configurada.
    """
    print(f"🕐 IPSA Agent Scheduler iniciado")
    print(f"   Hora de ejecución: {run_hour:02d}:{run_minute:02d}")
    print(f"   Solo días hábiles (L-V, sin feriados chilenos)")
    print(f"   Ctrl+C para detener\n")

    days_run = 0

    while True:
        now = datetime.now()

        # Verificar si es el momento de ejecutar
        if (
            now.hour == run_hour and
            now.minute == run_minute and
            is_business_day(now)
        ):
            logger.info(f"[SCHEDULER] Disparando análisis: {now.strftime('%Y-%m-%d %H:%M')}")
            try:
                from main import run_daily_pipeline
                result = run_daily_pipeline()
                days_run += 1
                logger.info(f"[SCHEDULER] Análisis completado. Días ejecutados: {days_run}")

                if max_days and days_run >= max_days:
                    logger.info("[SCHEDULER] Máximo de días alcanzado. Deteniendo.")
                    break

            except Exception as e:
                logger.error(f"[SCHEDULER] Error en pipeline: {e}", exc_info=True)

            # Esperar 90 segundos para evitar doble ejecución en el mismo minuto
            time.sleep(90)

        else:
            # Calcular tiempo hasta próxima ejecución
            next_run = now.replace(hour=run_hour, minute=run_minute, second=0, microsecond=0)
            if next_run <= now:
                from datetime import timedelta
                next_run += timedelta(days=1)

            wait_seconds = (next_run - now).total_seconds()

            # Log cada hora
            if now.minute == 0 and now.second < 5:
                logger.info(f"[SCHEDULER] En espera. Próxima ejecución: {next_run.strftime('%Y-%m-%d %H:%M')}")

            time.sleep(30)  # Verificar cada 30 segundos


def generate_crontab_line(hour: int = 9, minute: int = 15) -> str:
    """Genera la línea de crontab equivalente."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    python_path = sys.executable
    return (
        f"{minute} {hour} * * 1-5 "
        f"cd {script_dir} && {python_path} main.py --quiet "
        f">> {script_dir}/logs/cron.log 2>&1"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="IPSA Agent Scheduler")
    parser.add_argument("--hour",   type=int, default=9,  help="Hora de ejecución (default: 9)")
    parser.add_argument("--minute", type=int, default=15, help="Minuto de ejecución (default: 15)")
    parser.add_argument("--crontab", action="store_true", help="Solo mostrar línea crontab equivalente")
    args = parser.parse_args()

    if args.crontab:
        print(f"\nLínea crontab equivalente:")
        print(f"  {generate_crontab_line(args.hour, args.minute)}\n")
        print("Instalar con:")
        print("  crontab -e")
        print("  # Pegar la línea anterior\n")
    else:
        run_scheduler(run_hour=args.hour, run_minute=args.minute)
