from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from src.config.settings import PATHS
from src.utils.logging_utils import get_logger

log = get_logger("EWS.handlers")

ALLOWED_INPUT_EXTS = {".csv", ".xlsx", ".xls"}


def _today_iso() -> str:
    return date.today().isoformat()


def _require_exists(p: Path, what: str = "archivo") -> None:
    if not p.exists():
        raise FileNotFoundError(f"No existe {what}: {p}")


def _require_allowed_ext(p: Path) -> None:
    if p.suffix.lower() not in ALLOWED_INPUT_EXTS:
        raise ValueError(f"Extensión no soportada: {p.suffix}. Permitidas: {sorted(ALLOWED_INPUT_EXTS)}")


def handle(args: argparse.Namespace) -> int:
    """Dispatcher: recibe el Namespace parseado y llama al handler correcto."""
    snapshot_date = getattr(args, "snapshot_date", None) or _today_iso()

    if args.cmd == "ping":
        log.info("✅ Entorno OK")
        log.info(f"Root: {PATHS.root}")
        log.info(f"Data: {PATHS.data}")
        return 0

    if args.cmd == "ingest-matricula":
        from src.ingestion.ingest_matricula import ingest
        p = Path(args.file).expanduser().resolve()
        _require_exists(p, "archivo de entrada")
        _require_allowed_ext(p)
        ingest(p)
        return 0

    if args.cmd == "build-stg-matricula":
        from src.staging.build_stg_matricula import build_staging
        p = (PATHS.raw_matricula / args.snapshot).resolve()
        _require_exists(p, "snapshot en data/raw/matricula")
        build_staging(p)
        return 0

    if args.cmd == "build-stg-desiste":
        from src.staging.build_stg_desiste import build_staging_desiste
        p = Path(args.file).expanduser().resolve()
        _require_exists(p, "archivo DESISTE")
        _require_allowed_ext(p)
        out = build_staging_desiste(str(p))
        log.info(f"✅ OK staging DESISTE -> {out}")
        return 0

    if args.cmd == "build-curated-enrollment":
        from src.curated.build_curated_enrollment import build_curated_enrollment
        build_curated_enrollment()
        return 0

    if args.cmd == "gold-enrollment-status":
        from src.gold.enrollment_status import enrollment_status
        enrollment_status(export_excel=not args.no_excel)
        return 0

    if args.cmd == "gold-enrollment-current":
        from src.gold.enrollment_current import enrollment_current
        enrollment_current(snapshot_date=args.snapshot_date, export_excel=args.excel)
        return 0

    if args.cmd == "gold-enrollment-demographics":
        from src.gold.enrollment_demographics import enrollment_demographics
        enrollment_demographics(snapshot_date=args.snapshot_date, export_excel=args.excel, top_n=args.top_n)
        return 0

    if args.cmd == "gold-enrollment-history":
        from src.gold.enrollment_history import enrollment_history
        enrollment_history(snapshot_date=args.snapshot_date, export_excel=args.excel)
        return 0

    if args.cmd == "gold-enrollment-master":
        from src.gold.enrollment_master import enrollment_master
        enrollment_master(snapshot_date=snapshot_date, export_excel=args.excel)
        return 0

    if args.cmd == "run-matricula":
        from src.cli.pipeline import run_matricula
        return run_matricula(
            file=args.file,
            snapshot_date=snapshot_date,
            export_excel=args.excel,
            top_n=args.top_n,
            force=args.force,
            desiste_file=args.desiste_file,
            desiste_folder=args.desiste_folder,
            desiste_auto=args.desiste_auto,
        )

    log.error(f"Comando no soportado: {args.cmd}")
    return 2