# ui/enrollment_processing.py
from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path


def process_enrollment_upload(uploaded_file, force: bool = False) -> tuple[bool, str]:
    """
    Procesa un archivo de matrícula subido desde Streamlit.

    Retorna:
        (True, mensaje) si salió bien
        (False, mensaje) si falló
    """
    if uploaded_file is None:
        return False, "No se recibió ningún archivo."

    try:
        from src.cli.pipeline import run_matricula

        suffix = Path(uploaded_file.name).suffix.lower()
        if suffix not in {".csv", ".xlsx", ".xls"}:
            return False, f"Extensión no soportada: {suffix}"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded_file.getbuffer())
            tmp_path = tmp.name

        try:
            exit_code = run_matricula(
                file=tmp_path,
                snapshot_date=date.today().isoformat(),
                export_excel=False,
                top_n=10,
                force=force,
                desiste_file=None,
                desiste_folder=None,
                desiste_auto=False,
            )
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

        if exit_code == 0:
            return True, "Matrícula procesada correctamente."
        return False, f"El pipeline terminó con código {exit_code}."

    except Exception as e:
        return False, f"Error procesando matrícula: {e}"