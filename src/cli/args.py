from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Early Warning System Escolar - Runner")
    sub    = parser.add_subparsers(dest="cmd", required=True)

    # ── Utilidades ──────────────────────────────────────────────────
    sub.add_parser("ping", help="Verifica que el entorno está OK")

    # ── Ingesta ─────────────────────────────────────────────────────
    p_ing = sub.add_parser("ingest-matricula", help="Ingesta archivo de matrícula (snapshot)")
    p_ing.add_argument("file", type=str, help="Ruta del archivo CSV/XLSX a cargar")

    # ── Staging ─────────────────────────────────────────────────────
    p_stg = sub.add_parser("build-stg-matricula", help="Construye staging de matrícula (parquet)")
    p_stg.add_argument("snapshot", type=str, help="Nombre del snapshot dentro de data/raw/matricula/")

    p_des = sub.add_parser("build-stg-desiste", help="Construye staging DESISTE (parquet)")
    p_des.add_argument("file", type=str, help="Ruta del archivo DESISTE (.csv/.xlsx/.xls)")

    # ── Curated ─────────────────────────────────────────────────────
    sub.add_parser("build-curated-enrollment", help="Genera curated snapshot + diff")

    # ── Gold ────────────────────────────────────────────────────────
    p_status = sub.add_parser("gold-enrollment-status", help="Reporte auditoría (diff)")
    p_status.add_argument("--no-excel", action="store_true")

    p_current = sub.add_parser("gold-enrollment-current", help="Estado real al corte")
    p_current.add_argument("--snapshot-date", type=str, required=True)
    p_current.add_argument("--excel", action="store_true")

    p_demo = sub.add_parser("gold-enrollment-demographics", help="KPIs demográficos")
    p_demo.add_argument("--snapshot-date", type=str, required=True)
    p_demo.add_argument("--excel", action="store_true")
    p_demo.add_argument("--top-n", type=int, default=10)

    p_hist = sub.add_parser("gold-enrollment-history", help="Histórico KPIs + anomalías edad")
    p_hist.add_argument("--snapshot-date", type=str, required=True)
    p_hist.add_argument("--excel", action="store_true")

    p_master = sub.add_parser("gold-enrollment-master", help="Estado MASTER (matrícula + desiste)")
    p_master.add_argument("--snapshot-date", type=str, default=None)
    p_master.add_argument("--excel", action="store_true")

    # ── Pipeline completo ────────────────────────────────────────────
    p_run = sub.add_parser("run-matricula", help="Pipeline matrícula completo (ingest→stg→curated→gold)")
    p_run.add_argument("file",             type=str,            help="Ruta del archivo CSV/XLSX (matrícula)")
    p_run.add_argument("--snapshot-date",  type=str,            default=None)
    p_run.add_argument("--excel",          action="store_true", help="Exportar Excel en reportes gold")
    p_run.add_argument("--top-n",          type=int,            default=10)
    p_run.add_argument("--force",          action="store_true", help="Fuerza ejecución aunque no haya cambios")
    p_run.add_argument("--desiste-file",   type=str,            default=None)
    p_run.add_argument("--desiste-folder", type=str,            default=None)
    p_run.add_argument("--desiste-auto",   action="store_true")

    return parser