from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from src.config.settings import PATHS
from src.utils.logging_utils import get_logger

log = get_logger("EWS.pipeline")

ALLOWED_INPUT_EXTS = {".csv", ".xlsx", ".xls"}

# ──────────────────────────────────────────────
# Fingerprinting (skip inteligente)
# ──────────────────────────────────────────────

def _sha256_file(p: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(p: Path) -> str:
    return f"{_sha256_file(p)}|{p.stat().st_size}"


def _state_file() -> Path:
    st = PATHS.data / ".state"
    st.mkdir(parents=True, exist_ok=True)
    return st / "run_matricula_last_snapshot.txt"


def load_last_fingerprint() -> str | None:
    sf  = _state_file()
    txt = sf.read_text(encoding="utf-8").strip() if sf.exists() else ""
    return txt or None


def save_last_fingerprint(fp: str) -> None:
    _state_file().write_text(fp, encoding="utf-8")


# ──────────────────────────────────────────────
# Resolución de DESISTE
# ──────────────────────────────────────────────

def _latest_by_mtime(folder: Path, patterns: list[str]) -> Path:
    files: list[Path] = []
    for pat in patterns:
        files.extend(folder.glob(pat))
    if not files:
        raise FileNotFoundError(f"No se encontraron archivos en {folder} con patrones: {patterns}")
    return max(files, key=lambda p: p.stat().st_mtime)


def resolve_desiste(
    desiste_file:   str | None,
    desiste_folder: str | None,
    desiste_auto:   bool,
    label: str = "",
) -> str | None:
    """
    Resuelve qué fuente DESISTE usar y la stagea si es necesario.
    Retorna una etiqueta descriptiva si se resolvió, None si no hay nada usable.

    label: prefijo para logs (ej: "(SKIP)" cuando matrícula no cambió)
    """
    from src.staging.build_stg_desiste import build_staging_desiste

    prefix = f"{label} " if label else ""
    desiste_used: str | None = None

    # 1) Archivo explícito
    if desiste_file:
        p = Path(desiste_file).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"No existe archivo DESISTE: {p}")
        if p.suffix.lower() not in ALLOWED_INPUT_EXTS:
            raise ValueError(f"Extensión no soportada: {p.suffix}")
        build_staging_desiste(str(p))
        desiste_used = f"file:{p.name}"
        log.info(f"📌 {prefix}DESISTE staging OK desde --desiste-file")

    # 2) Auto: usa staging existente o stagea desde folder
    if desiste_auto:
        stg_files = sorted((PATHS.staging / "desiste").glob("desiste_snapshot__*.parquet"))
        if stg_files:
            desiste_used = desiste_used or f"staging:{stg_files[-1].name}"
            log.info(f"📌 {prefix}DESISTE staging: usando el más reciente (ya existente)")
        elif desiste_folder:
            folder = Path(desiste_folder).expanduser().resolve()
            if not folder.is_dir():
                raise NotADirectoryError(f"No es carpeta: {folder}")
            latest = _latest_by_mtime(folder, ["*.csv", "*.xlsx", "*.xls"])
            if latest.suffix.lower() not in ALLOWED_INPUT_EXTS:
                raise ValueError(f"Extensión no soportada: {latest.suffix}")
            build_staging_desiste(str(latest))
            desiste_used = f"folder:{folder.name}->{latest.name}"
            log.info(f"📌 {prefix}DESISTE staging OK (desde folder via auto)")
        else:
            log.warning(f"⚠️ {prefix}--desiste-auto pedido pero no hay staging ni --desiste-folder.")

    # 3) Solo folder (sin auto ni file explícito)
    if not desiste_file and not desiste_auto and desiste_folder:
        folder = Path(desiste_folder).expanduser().resolve()
        if not folder.is_dir():
            raise NotADirectoryError(f"No es carpeta: {folder}")
        latest = _latest_by_mtime(folder, ["*.csv", "*.xlsx", "*.xls"])
        if latest.suffix.lower() not in ALLOWED_INPUT_EXTS:
            raise ValueError(f"Extensión no soportada: {latest.suffix}")
        build_staging_desiste(str(latest))
        desiste_used = f"folder:{folder.name}->{latest.name}"
        log.info(f"📌 {prefix}DESISTE staging OK (desde folder)")

    return desiste_used


# ──────────────────────────────────────────────
# Resumen final
# ──────────────────────────────────────────────

def print_run_summary(snapshot_date: str, export_excel: bool, desiste_used: str | None) -> None:
    try:
        gold_dir = PATHS.gold / "enrollment"
        stamp    = snapshot_date.replace("-", "")

        curr_metrics = gold_dir / f"enrollment_metrics__{stamp}.parquet"
        if curr_metrics.exists():
            m = pd.read_parquet(curr_metrics).iloc[0].to_dict()
            log.info("📌 RESUMEN (GOLD - CURRENT)")
            log.info(
                f"   • RUT únicos: {int(m.get('ruts_unicos', 0))} | "
                f"Matriculados: {int(m.get('matriculados_actuales', 0))} | "
                f"Retirados reales: {int(m.get('retirados_reales', 0))} | "
                f"Transferencias: {int(m.get('transferencias_internas', 0))}"
            )

        demo_path = gold_dir / f"enrollment_demographics__{stamp}.parquet"
        if demo_path.exists():
            d = pd.read_parquet(demo_path).iloc[0].to_dict()
            log.info("📌 RESUMEN (GOLD - DEMOGRAPHICS)")
            log.info(
                f"   • Sexo: H={int(d.get('sexo_m', 0))} | M={int(d.get('sexo_f', 0))} | "
                f"Otro/Vacío={int(d.get('sexo_otro_o_vacio', 0))}"
            )
            log.info(
                f"   • % Renca: {float(d.get('pct_renca_sobre_total_ruts', 0.0)):.2f}% | "
                f"Edad prom: {float(d.get('edad_promedio', 0.0)):.2f} | "
                f"Repitentes: {int(d.get('repitentes', 0))} ({float(d.get('repitentes_pct', 0.0)):.2f}%)"
            )

        master_metrics = gold_dir / f"enrollment_master_metrics__{stamp}.parquet"
        if master_metrics.exists():
            mm    = pd.read_parquet(master_metrics).iloc[0].to_dict()
            phase = str(mm.get("phase", "")).strip()
            log.info("📌 RESUMEN (GOLD - MASTER)")
            log.info(
                f"   • Phase: {phase or '(sin phase)'} | "
                f"Matrícula: {int(mm.get('ruts_unicos_matricula', 0))} | "
                f"Desiste: {int(mm.get('desiste_total', 0))} | "
                f"Intersección warn: {int(mm.get('desiste_intersection_warn', 0))}"
            )
        elif desiste_used:
            log.info("ℹ️ No encontré enrollment_master_metrics del día (aunque se solicitó DESISTE).")

        if export_excel:
            log.info("📦 Export Excel: ACTIVADO")
        if desiste_used:
            log.info(f"🧾 DESISTE usado: {desiste_used}")

        log.info("✅ Pipeline finalizado OK 🎉")

    except Exception as e:
        log.warning(f"⚠️ No pude imprimir el resumen final (no crítico): {e}")


# ──────────────────────────────────────────────
# Orquestador run-matricula
# ──────────────────────────────────────────────

def run_matricula(
    file:           str,
    snapshot_date:  str,
    export_excel:   bool,
    top_n:          int,
    force:          bool,
    desiste_file:   str | None,
    desiste_folder: str | None,
    desiste_auto:   bool,
) -> int:
    """
    Pipeline completo: ingest → staging → curated → gold.
    Retorna exit code (0 = OK, 1 = error).
    """
    from src.ingestion.ingest_matricula import ingest as ingest_matricula
    from src.staging.build_stg_matricula import build_staging as build_stg_matricula
    from src.curated.build_curated_enrollment import build_curated_enrollment
    from src.gold.enrollment_current import enrollment_current
    from src.gold.enrollment_status import enrollment_status
    from src.gold.enrollment_demographics import enrollment_demographics
    from src.gold.enrollment_history import enrollment_history
    from src.gold.enrollment_master import enrollment_master

    file_path = Path(file).expanduser().resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"No existe archivo de entrada: {file_path}")
    if file_path.suffix.lower() not in ALLOWED_INPUT_EXTS:
        raise ValueError(f"Extensión no soportada: {file_path.suffix}")

    fp_now  = fingerprint(file_path)
    fp_last = load_last_fingerprint()

    want_desiste = bool(desiste_file or desiste_auto or desiste_folder)

    # ── Sin cambios en matrícula ────────────────────────────────────
    if not force and fp_last == fp_now:
        log.info("🟦 Sin cambios en el archivo de entrada (hash igual al último run).")
        log.info("🟦 Saltando INGEST/STAGING/CURATED/GOLD (usa --force para forzar).")

        desiste_used: str | None = None
        if want_desiste:
            try:
                desiste_used = resolve_desiste(desiste_file, desiste_folder, desiste_auto, label="(SKIP)")
                if desiste_used:
                    log.info("⏳ (SKIP) Recalculando MASTER por DESISTE...")
                    enrollment_master(snapshot_date=snapshot_date, export_excel=export_excel)
                else:
                    log.warning("⚠️ (SKIP) No se pudo resolver DESISTE usable. Se omite MASTER.")
            except Exception as e:
                log.warning(f"⚠️ (SKIP) No pude recalcular MASTER: {e}")

        print_run_summary(snapshot_date, export_excel, desiste_used)
        return 0

    # ── Pipeline completo ───────────────────────────────────────────
    # 1) Ingest
    ingest_matricula(file_path)

    # 2) Staging matrícula
    latest_raw = _latest_by_mtime(
        PATHS.raw_matricula,
        ["matricula_snapshot_*.csv", "matricula_snapshot_*.xlsx", "matricula_snapshot_*.xls"],
    )
    log.info(f"📌 Último snapshot raw detectado: {latest_raw.name}")
    build_stg_matricula(latest_raw)

    # 3) Curated
    build_curated_enrollment()

    # 4) Gold
    enrollment_current(snapshot_date=snapshot_date, export_excel=export_excel)
    enrollment_status(export_excel=export_excel)
    enrollment_demographics(snapshot_date=snapshot_date, export_excel=export_excel, top_n=top_n)
    enrollment_history(snapshot_date=snapshot_date, export_excel=export_excel)

    # 5) DESISTE + MASTER
    desiste_used = None
    if want_desiste:
        desiste_used = resolve_desiste(desiste_file, desiste_folder, desiste_auto)
        if desiste_used:
            log.info("⏳ Ejecutando MASTER...")
            enrollment_master(snapshot_date=snapshot_date, export_excel=export_excel)
        else:
            log.warning("⚠️ Se solicitó DESISTE pero no se pudo resolver. Se omite MASTER.")

    # 6) Guardar fingerprint
    save_last_fingerprint(fp_now)

    # 7) Resumen
    print_run_summary(snapshot_date, export_excel, desiste_used)
    return 0