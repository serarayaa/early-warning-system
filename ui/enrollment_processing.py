# ui/enrollment_processing.py
from __future__ import annotations

import os
import tempfile
import traceback
from datetime import date
from pathlib import Path


def process_enrollment_upload(uploaded_file, force: bool = False) -> tuple[bool, str]:
    """
    Procesa un archivo de matrícula subido desde Streamlit.
    Llama directamente a build_stg_matricula + enrollment_current,
    evitando dependencias del pipeline completo (curated requiere 2 snapshots).
    """
    if uploaded_file is None:
        return False, "No se recibió ningún archivo."

    try:
        from src.staging.build_stg_matricula import build_staging
        from src.gold.enrollment_current import enrollment_current
        from src.gold.enrollment_demographics import enrollment_demographics
        from src.gold.enrollment_status import enrollment_status

        suffix = Path(uploaded_file.name).suffix.lower()
        if suffix not in {".csv", ".xlsx", ".xls"}:
            return False, f"Extensión no soportada: {suffix}"

        # ── Guardar archivo temporal ───────────────────────────────
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded_file.getbuffer())
            tmp_path = Path(tmp.name)

        try:
            snapshot_date = date.today().isoformat()
            stamp         = date.today().strftime("%Y%m%d")

            # ── Si force=True, eliminar parquets gold del día para forzar regeneración
            if force:
                gold_dir = Path("data/gold/enrollment")
                for patron in [f"enrollment_current__{stamp}.parquet",
                               f"enrollment_metrics__{stamp}.parquet",
                               f"enrollment_demographics__{stamp}.parquet"]:
                    p = gold_dir / patron
                    if p.exists():
                        p.unlink()
                # También limpiar snapshot curated del día
                curated_d = Path("data/curated/enrollment")
                for p in curated_d.glob(f"enrollment_snapshot__{stamp}*.parquet"):
                    p.unlink()
                # Y staging del día
                stg_d = Path("data/staging/matricula")
                for p in stg_d.glob(f"*{stamp}*.parquet"):
                    p.unlink()

            # ── 1. Staging ─────────────────────────────────────────
            stg_dir = Path("data/staging/matricula")
            stg_dir.mkdir(parents=True, exist_ok=True)
            stg_path = build_staging(tmp_path, out_dir=stg_dir)

            # ── 2. Copiar staging a curated para que Gold lo encuentre
            from src.utils.transforms import ensure_dir
            curated_dir = Path("data/curated/enrollment")
            curated_dir.mkdir(parents=True, exist_ok=True)

            import pandas as pd
            df_stg = pd.read_parquet(stg_path)

            # Guardar como snapshot curated
            snap_out = curated_dir / f"enrollment_snapshot__{stamp}.parquet"
            df_stg.to_parquet(snap_out, index=False)

            # ── 3. Gold ────────────────────────────────────────────
            enrollment_current(snapshot_date=snapshot_date, export_excel=False)

            try:
                enrollment_demographics(snapshot_date=snapshot_date, export_excel=False, top_n=10)
            except Exception:
                pass  # no crítico

            try:
                enrollment_status(export_excel=False)
            except Exception:
                pass  # no crítico

        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

        return True, f"✅ Matrícula procesada correctamente — corte {stamp}."

    except Exception as e:
        detail = traceback.format_exc()
        return False, f"Error procesando matrícula: {e}\n\nDetalle:\n{detail}"