from __future__ import annotations

import argparse
import hashlib
from datetime import date
from pathlib import Path
from time import perf_counter

from src.config.settings import PATHS
from src.utils.logging_utils import setup_logging, get_logger

ALLOWED_INPUT_EXTS = {".csv", ".xlsx", ".xls"}


# -----------------------------
# Basics
# -----------------------------
def _setup_logging_safe() -> None:
    cfg = PATHS.root / "src" / "config" / "logging.yaml"
    if cfg.exists():
        setup_logging(cfg)


def _require_exists(p: Path, what: str = "archivo") -> None:
    if not p.exists():
        raise FileNotFoundError(f"No existe {what}: {p}")


def _require_allowed_ext(p: Path) -> None:
    if p.suffix.lower() not in ALLOWED_INPUT_EXTS:
        raise ValueError(f"Extensión no soportada: {p.suffix}. Permitidas: {sorted(ALLOWED_INPUT_EXTS)}")


def _today_iso() -> str:
    return date.today().isoformat()


def _latest_by_mtime(folder: Path, patterns: list[str]) -> Path:
    files: list[Path] = []
    for pat in patterns:
        files.extend(folder.glob(pat))
    if not files:
        raise FileNotFoundError(f"No se encontraron archivos en {folder} con patrones: {patterns}")
    return max(files, key=lambda p: p.stat().st_mtime)


def _warmup_pandas(log) -> None:
    t0 = perf_counter()
    import pandas as pd  # noqa: F401

    dt = perf_counter() - t0
    import pandas as pd2

    log.info(f"✅ Pandas cargado ({pd2.__version__}) en {dt:.2f}s")


# -----------------------------
# New: snapshot fingerprinting
# -----------------------------
def _sha256_file(p: Path, chunk_size: int = 1024 * 1024) -> str:
    """
    Hash robusto para saber si un archivo realmente cambió.
    (Más confiable que mtime/size.)
    """
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _fingerprint(p: Path) -> str:
    """
    Fingerprint simple: sha256 + size.
    """
    return f"{_sha256_file(p)}|{p.stat().st_size}"


def _state_file() -> Path:
    """
    Guardamos el estado en data/.state para que sobreviva entre ejecuciones.
    """
    st = PATHS.data / ".state"
    st.mkdir(parents=True, exist_ok=True)
    return st / "run_matricula_last_snapshot.txt"


def _load_last_fingerprint() -> str | None:
    sf = _state_file()
    if not sf.exists():
        return None
    txt = sf.read_text(encoding="utf-8").strip()
    return txt or None


def _save_last_fingerprint(fp: str) -> None:
    sf = _state_file()
    sf.write_text(fp, encoding="utf-8")


# -----------------------------
# Summary (your original, intact)
# -----------------------------
def _print_run_summary(
    log,
    snapshot_date: str,
    export_excel: bool,
    desiste_used: str | None,
) -> None:
    try:
        import pandas as pd

        gold_dir = PATHS.gold / "enrollment"
        stamp = snapshot_date.replace("-", "")

        curr_metrics = gold_dir / f"enrollment_metrics__{stamp}.parquet"
        if curr_metrics.exists():
            m = pd.read_parquet(curr_metrics).iloc[0].to_dict()
            log.info("📌 RESUMEN (GOLD - CURRENT)")
            log.info(
                f"   • RUT únicos: {int(m.get('ruts_unicos', 0))} | "
                f"Matriculados actuales: {int(m.get('matriculados_actuales', 0))} | "
                f"Retirados reales: {int(m.get('retirados_reales', 0))} | "
                f"Transferencias internas: {int(m.get('transferencias_internas', 0))}"
            )
        else:
            log.info("ℹ️ No encontré enrollment_metrics del día (current).")

        demo_path = gold_dir / f"enrollment_demographics__{stamp}.parquet"
        if demo_path.exists():
            d = pd.read_parquet(demo_path).iloc[0].to_dict()
            log.info("📌 RESUMEN (GOLD - DEMOGRAPHICS)")
            log.info(
                f"   • Sexo: H={int(d.get('sexo_m', 0))} | M={int(d.get('sexo_f', 0))} | "
                f"Otro/Vacío={int(d.get('sexo_otro_o_vacio', 0))}"
            )
            log.info(
                f"   • % Renca (sobre total): {float(d.get('pct_renca_sobre_total', 0.0)):.2f}% | "
                f"Edad prom: {float(d.get('edad_promedio', 0.0)):.2f} | "
                f"Repitentes: {int(d.get('repitentes', 0))} ({float(d.get('repitentes_pct', 0.0)):.2f}%)"
            )
        else:
            log.info("ℹ️ No encontré enrollment_demographics del día.")

        master_metrics = gold_dir / f"enrollment_master_metrics__{stamp}.parquet"
        if master_metrics.exists():
            mm = pd.read_parquet(master_metrics).iloc[0].to_dict()
            phase = str(mm.get("phase", "")).strip()
            log.info("📌 RESUMEN (GOLD - MASTER)")
            log.info(
                f"   • Phase: {phase or '(sin phase)'} | "
                f"Matrícula: {int(mm.get('ruts_unicos_matricula', mm.get('ruts_unicos', 0)))} | "
                f"Desiste total: {int(mm.get('desiste_total', mm.get('desiste_master', 0)))} | "
                f"Intersección warn: {int(mm.get('desiste_intersection_warn', 0))}"
            )
        else:
            if desiste_used:
                log.info("ℹ️ No encontré enrollment_master_metrics del día (aunque se solicitó DESISTE).")

        if export_excel:
            log.info("📦 Export Excel: ACTIVADO (se generaron .xlsx donde corresponde)")
        if desiste_used:
            log.info(f"🧾 DESISTE usado: {desiste_used}")

        log.info("✅ Pipeline finalizado OK 🎉")

    except Exception as e:
        log.warning(f"⚠️ No pude imprimir el resumen final (no crítico): {e}")


# -----------------------------
# Main
# -----------------------------
def main() -> int:
    _setup_logging_safe()
    log = get_logger("EWS")

    parser = argparse.ArgumentParser(description="Early Warning System Escolar - Runner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ping", help="Verifica que el entorno está OK")

    # INGEST
    p_ing_matr = sub.add_parser("ingest-matricula", help="Ingesta archivo de matrícula (snapshot)")
    p_ing_matr.add_argument("file", type=str, help="Ruta del archivo CSV/XLSX a cargar")

    # STAGING
    p_stg_matr = sub.add_parser("build-stg-matricula", help="Construye staging de matrícula (parquet)")
    p_stg_matr.add_argument("snapshot", type=str, help="Nombre del snapshot dentro de data/raw/matricula/")

    # STAGING DESISTE
    p_stg_des = sub.add_parser("build-stg-desiste", help="Construye staging DESISTE (parquet)")
    p_stg_des.add_argument("file", type=str, help="Ruta del archivo DESISTE (.csv/.xlsx/.xls)")

    # CURATED
    sub.add_parser("build-curated-enrollment", help="Genera curated snapshot + diff usando 2 staging más recientes")

    # GOLD
    p_gold_status = sub.add_parser("gold-enrollment-status", help="Reporte auditoría (diff)")
    p_gold_status.add_argument("--no-excel", action="store_true")

    p_gold_current = sub.add_parser("gold-enrollment-current", help="Estado real al corte (Syscol Fecha Retiro)")
    p_gold_current.add_argument("--snapshot-date", type=str, required=True)
    p_gold_current.add_argument("--excel", action="store_true")

    p_gold_demo = sub.add_parser("gold-enrollment-demographics", help="KPIs demográficos")
    p_gold_demo.add_argument("--snapshot-date", type=str, required=True)
    p_gold_demo.add_argument("--excel", action="store_true")
    p_gold_demo.add_argument("--top-n", type=int, default=10)

    p_gold_hist = sub.add_parser("gold-enrollment-history", help="Histórico de KPIs + anomalías edad/nacimiento")
    p_gold_hist.add_argument("--snapshot-date", type=str, required=True)
    p_gold_hist.add_argument("--excel", action="store_true")

    p_gold_master = sub.add_parser(
        "gold-enrollment-master",
        help="Estado MASTER (matrícula + desiste + regla 17/18 marzo)",
    )
    p_gold_master.add_argument("--snapshot-date", type=str, default=None, help="YYYY-MM-DD (default: hoy)")
    p_gold_master.add_argument("--excel", action="store_true")

    # PIPELINE FULL
    p_run = sub.add_parser("run-matricula", help="Pipeline matrícula AUTOMÁTICO (ingest->stg->curated->gold)")
    p_run.add_argument("file", type=str, help="Ruta del archivo CSV/XLSX a cargar (matrícula)")
    p_run.add_argument("--snapshot-date", type=str, default=None, help="Fecha corte (YYYY-MM-DD) (default: hoy)")
    p_run.add_argument("--excel", action="store_true", help="Exportar Excel en reportes gold")
    p_run.add_argument("--top-n", type=int, default=10, help="Top N para rankings (default 10)")
    p_run.add_argument("--force", action="store_true", help="Fuerza ejecución completa aunque no haya cambios")

    # DESISTE
    p_run.add_argument("--desiste-file", type=str, default=None, help="Ruta DESISTE para stagear + correr MASTER")
    p_run.add_argument("--desiste-folder", type=str, default=None, help="Carpeta donde buscar el DESISTE más reciente")
    p_run.add_argument("--desiste-auto", action="store_true", help="Usa staging DESISTE más reciente o stagea desde folder")

    args = parser.parse_args()
    snapshot_date = getattr(args, "snapshot_date", None) or _today_iso()

    try:
        if args.cmd == "ping":
            log.info("✅ Entorno OK")
            log.info(f"Root: {PATHS.root}")
            log.info(f"Data: {PATHS.data}")
            return 0

        if args.cmd == "ingest-matricula":
            from src.ingestion.ingest_matricula import ingest as ingest_matricula

            file_path = Path(args.file).expanduser().resolve()
            _require_exists(file_path, "archivo de entrada")
            _require_allowed_ext(file_path)
            ingest_matricula(file_path)
            return 0

        if args.cmd == "build-stg-matricula":
            from src.staging.build_stg_matricula import build_staging as build_stg_matricula

            snapshot_path = (PATHS.raw_matricula / args.snapshot).resolve()
            _require_exists(snapshot_path, "snapshot en data/raw/matricula")
            build_stg_matricula(snapshot_path)
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
            log.info("⏳ Ejecutando MASTER... (warmup pandas)")
            _warmup_pandas(log)

            from src.gold.enrollment_master import enrollment_master

            enrollment_master(snapshot_date=snapshot_date, export_excel=args.excel)
            return 0

        if args.cmd == "run-matricula":
            desiste_used: str | None = None

            # 0) Detectar si hay cambios reales en el input
            file_path = Path(args.file).expanduser().resolve()
            _require_exists(file_path, "archivo de entrada matrícula")
            _require_allowed_ext(file_path)

            fp_now = _fingerprint(file_path)
            fp_last = _load_last_fingerprint()

            # ---------------------------------------------------------
            # ✅ MEJORA: si matrícula no cambia, pero DESISTE fue pedido,
            #           recalculamos MASTER (porque DESISTE puede cambiar)
            # ---------------------------------------------------------
            if (not args.force) and (fp_last == fp_now):
                log.info("🟦 No hay cambios en el archivo de entrada (hash igual al último run).")
                log.info("🟦 Saltando INGEST/STAGING/CURATED/GOLD pesados (usa --force si quieres correr igual).")

                want_desiste = bool(args.desiste_file) or bool(args.desiste_auto) or bool(args.desiste_folder)

                if want_desiste:
                    # Intentar resolver DESISTE igual que en el flujo normal
                    try:
                        # 1) Si viene archivo explícito: stagear
                        if args.desiste_file:
                            from src.staging.build_stg_desiste import build_staging_desiste

                            des_path = Path(args.desiste_file).expanduser().resolve()
                            _require_exists(des_path, "archivo DESISTE")
                            _require_allowed_ext(des_path)
                            build_staging_desiste(str(des_path))
                            desiste_used = f"file:{des_path.name}"
                            log.info("📌 (SKIP) DESISTE staging OK desde --desiste-file")

                        # 2) Auto: preferir staging existente, si no existe y hay folder, stagear desde folder
                        if args.desiste_auto:
                            stg_des_dir = PATHS.staging / "desiste"
                            stg_files = sorted(stg_des_dir.glob("desiste_snapshot__*.parquet"))
                            if stg_files:
                                desiste_used = desiste_used or f"staging:{stg_files[-1].name}"
                                log.info("📌 (SKIP) DESISTE staging: usando el más reciente (ya existente)")
                            else:
                                if args.desiste_folder:
                                    from src.staging.build_stg_desiste import build_staging_desiste

                                    folder = Path(args.desiste_folder).expanduser().resolve()
                                    _require_exists(folder, "carpeta DESISTE")
                                    if not folder.is_dir():
                                        raise NotADirectoryError(f"No es carpeta: {folder}")

                                    latest_des = _latest_by_mtime(folder, ["*.csv", "*.xlsx", "*.xls"])
                                    _require_allowed_ext(latest_des)
                                    build_staging_desiste(str(latest_des))
                                    desiste_used = f"folder:{folder.name}->{latest_des.name}"
                                    log.info("📌 (SKIP) DESISTE staging OK (desde folder)")
                                else:
                                    log.warning(
                                        "⚠️ (SKIP) --desiste-auto pedido, pero no hay staging DESISTE y no se entregó --desiste-folder."
                                    )

                        # 3) Solo folder (sin auto y sin file): stagear desde folder
                        if (not args.desiste_file) and (not args.desiste_auto) and args.desiste_folder:
                            from src.staging.build_stg_desiste import build_staging_desiste

                            folder = Path(args.desiste_folder).expanduser().resolve()
                            _require_exists(folder, "carpeta DESISTE")
                            if not folder.is_dir():
                                raise NotADirectoryError(f"No es carpeta: {folder}")

                            latest_des = _latest_by_mtime(folder, ["*.csv", "*.xlsx", "*.xls"])
                            _require_allowed_ext(latest_des)
                            build_staging_desiste(str(latest_des))
                            desiste_used = f"folder:{folder.name}->{latest_des.name}"
                            log.info("📌 (SKIP) DESISTE staging OK (solo folder)")

                        # Si logramos resolver DESISTE -> correr MASTER
                        if desiste_used:
                            log.info("⏳ (SKIP) Recalculando MASTER por DESISTE...")
                            _warmup_pandas(log)

                            from src.gold.enrollment_master import enrollment_master

                            enrollment_master(snapshot_date=snapshot_date, export_excel=args.excel)
                        else:
                            log.warning("⚠️ (SKIP) Se solicitó DESISTE, pero no se pudo resolver un staging usable. Se omite MASTER.")

                    except Exception as e:
                        log.warning(f"⚠️ (SKIP) No pude recalcular MASTER por DESISTE: {e}")

                _print_run_summary(
                    log=log,
                    snapshot_date=snapshot_date,
                    export_excel=args.excel,
                    desiste_used=desiste_used,
                )
                return 0

            # 1) ingest
            from src.ingestion.ingest_matricula import ingest as ingest_matricula

            ingest_matricula(file_path)

            # 2) staging matrícula (último snapshot raw por mtime)
            from src.staging.build_stg_matricula import build_staging as build_stg_matricula

            latest_raw = _latest_by_mtime(
                PATHS.raw_matricula,
                ["matricula_snapshot_*.csv", "matricula_snapshot_*.xlsx", "matricula_snapshot_*.xls"],
            )
            log.info(f"📌 Último snapshot matrícula detectado (mtime): {latest_raw.name}")
            build_stg_matricula(latest_raw)

            # 3) curated
            from src.curated.build_curated_enrollment import build_curated_enrollment

            build_curated_enrollment()

            # 4) gold
            from src.gold.enrollment_current import enrollment_current
            from src.gold.enrollment_status import enrollment_status
            from src.gold.enrollment_demographics import enrollment_demographics
            from src.gold.enrollment_history import enrollment_history

            enrollment_current(snapshot_date=snapshot_date, export_excel=args.excel)
            enrollment_status(export_excel=args.excel)
            enrollment_demographics(snapshot_date=snapshot_date, export_excel=args.excel, top_n=args.top_n)
            enrollment_history(snapshot_date=snapshot_date, export_excel=args.excel)

            # 5) desiste + master
            want_desiste = bool(args.desiste_file) or bool(args.desiste_auto) or bool(args.desiste_folder)
            if want_desiste:
                if args.desiste_file:
                    from src.staging.build_stg_desiste import build_staging_desiste

                    des_path = Path(args.desiste_file).expanduser().resolve()
                    _require_exists(des_path, "archivo DESISTE")
                    _require_allowed_ext(des_path)
                    out = build_staging_desiste(str(des_path))
                    desiste_used = f"file:{des_path.name}"
                    log.info(f"📌 DESISTE staging OK: {out}")

                if args.desiste_auto:
                    stg_des_dir = PATHS.staging / "desiste"
                    stg_files = sorted(stg_des_dir.glob("desiste_snapshot__*.parquet"))
                    if stg_files:
                        desiste_used = desiste_used or f"staging:{stg_files[-1].name}"
                        log.info("📌 DESISTE staging: usando el más reciente (ya existente)")
                    else:
                        if args.desiste_folder:
                            from src.staging.build_stg_desiste import build_staging_desiste

                            folder = Path(args.desiste_folder).expanduser().resolve()
                            _require_exists(folder, "carpeta DESISTE")
                            if not folder.is_dir():
                                raise NotADirectoryError(f"No es carpeta: {folder}")

                            latest_des = _latest_by_mtime(folder, ["*.csv", "*.xlsx", "*.xls"])
                            _require_allowed_ext(latest_des)
                            out = build_staging_desiste(str(latest_des))
                            desiste_used = f"folder:{folder.name}->{latest_des.name}"
                            log.info(f"📌 DESISTE staging OK (desde folder): {out}")
                        else:
                            log.warning("⚠️ --desiste-auto pedido, pero no hay staging DESISTE y no se entregó --desiste-folder.")

                if (not args.desiste_file) and (not args.desiste_auto) and args.desiste_folder:
                    from src.staging.build_stg_desiste import build_staging_desiste

                    folder = Path(args.desiste_folder).expanduser().resolve()
                    _require_exists(folder, "carpeta DESISTE")
                    if not folder.is_dir():
                        raise NotADirectoryError(f"No es carpeta: {folder}")

                    latest_des = _latest_by_mtime(folder, ["*.csv", "*.xlsx", "*.xls"])
                    _require_allowed_ext(latest_des)
                    out = build_staging_desiste(str(latest_des))
                    desiste_used = f"folder:{folder.name}->{latest_des.name}"
                    log.info(f"📌 DESISTE staging OK (desde folder): {out}")

                if desiste_used:
                    log.info("⏳ Ejecutando MASTER... (warmup pandas)")
                    _warmup_pandas(log)

                    from src.gold.enrollment_master import enrollment_master

                    enrollment_master(snapshot_date=snapshot_date, export_excel=args.excel)
                else:
                    log.warning("⚠️ Se solicitó DESISTE, pero no se pudo resolver un staging usable. Se omite MASTER.")

            # 6) guardamos fingerprint para “modo skip” futuro
            _save_last_fingerprint(fp_now)

            # 7) resumen final
            _print_run_summary(
                log=log,
                snapshot_date=snapshot_date,
                export_excel=args.excel,
                desiste_used=desiste_used,
            )
            return 0

        log.error(f"Comando no soportado: {args.cmd}")
        return 2

    except Exception as e:
        log.exception(f"❌ Error ejecutando comando '{args.cmd}': {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())