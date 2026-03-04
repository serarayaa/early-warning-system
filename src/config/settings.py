from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_path(key: str) -> Path | None:
    v = os.getenv(key, "").strip()
    return Path(v).expanduser().resolve() if v else None


@dataclass(frozen=True)
class Paths:
    """
    Rutas base del proyecto (public-friendly).
    - Por defecto usa carpetas dentro del repo (data/, logs/).
    - Permite override por variables de entorno:
        EWS_DATA_DIR: cambia la carpeta data (raw/staging/curated/gold)
        EWS_LOG_DIR:  cambia la carpeta logs
    """
    root: Path = Path(__file__).resolve().parents[2]  # .../early-warning-system-escolar

    # Overridable
    data: Path = _env_path("EWS_DATA_DIR") or (root / "data")
    logs: Path = _env_path("EWS_LOG_DIR") or (root / "logs")

    raw: Path = data / "raw"
    staging: Path = data / "staging"
    curated: Path = data / "curated"
    gold: Path = data / "gold"

    raw_matricula: Path = raw / "matricula"
    raw_asistencia: Path = raw / "asistencia"
    raw_notas_axes: Path = raw / "notas_axes"
    raw_config: Path = raw / "config"

    def ensure_dirs(self) -> None:
        """
        Crea carpetas base (evita errores en logging/file outputs).
        """
        self.data.mkdir(parents=True, exist_ok=True)
        self.logs.mkdir(parents=True, exist_ok=True)
        self.raw.mkdir(parents=True, exist_ok=True)
        self.staging.mkdir(parents=True, exist_ok=True)
        self.curated.mkdir(parents=True, exist_ok=True)
        self.gold.mkdir(parents=True, exist_ok=True)


PATHS = Paths()

# Reglas de negocio (versión 1 / MVP)
ATTENDANCE_RISK_THRESHOLD_PCT = 84.45
FAIL_GRADE_THRESHOLD = 3.95
MAX_FAILED_SUBJECTS_ALLOWED = 2  # riesgo si > 2

# Especialidades según letra de curso (A-H)
SPECIALTY_BY_SECTION = {
    "A": "TELECOM",
    "B": "TELECOM",
    "C": "TELECOM",
    "D": "TELECOM",
    "E": "ELECTRONICA",
    "F": "ELECTRONICA",
    "G": "MECANICA",
    "H": "MECANICA",
}