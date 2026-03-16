from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _env_path(key: str) -> Path | None:
    v = os.getenv(key, "").strip()
    return Path(v).expanduser().resolve() if v else None


def _env_str(key: str, default: str) -> str:
    return os.getenv(key, default).strip() or default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


# ──────────────────────────────────────────────
# Rutas
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class Paths:
    """
    Rutas base del proyecto.
    - Por defecto usa carpetas dentro del repo (data/, logs/).
    - Permite override por variables de entorno:
        EWS_DATA_DIR : cambia la carpeta data (raw/staging/curated/gold)
        EWS_LOG_DIR  : cambia la carpeta logs
    """
    root: Path = Path(__file__).resolve().parents[2]

    # Overridable por env
    data: Path = _env_path("EWS_DATA_DIR") or (root / "data")
    logs: Path = _env_path("EWS_LOG_DIR")  or (root / "logs")

    raw:     Path = data / "raw"
    staging: Path = data / "staging"
    curated: Path = data / "curated"
    gold:    Path = data / "gold"

    raw_matricula:  Path = raw / "matricula"
    raw_asistencia: Path = raw / "asistencia"
    raw_notas_axes: Path = raw / "notas_axes"
    raw_config:     Path = raw / "config"

    def ensure_dirs(self) -> None:
        """Crea carpetas base (evita errores en logging/file outputs)."""
        for p in [self.data, self.logs, self.raw, self.staging, self.curated, self.gold]:
            p.mkdir(parents=True, exist_ok=True)


PATHS = Paths()


# ──────────────────────────────────────────────
# Reglas de negocio
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class BusinessRules:
    """
    Todas las reglas de negocio del pipeline EWS en un solo lugar.

    Cada valor es overridable por variable de entorno, lo que permite
    ajustar umbrales sin tocar código (útil para pruebas o nuevo año escolar).

    Variables de entorno disponibles:
        EWS_ATTENDANCE_RISK_PCT      : umbral % asistencia para riesgo       (default: 84.45)
        EWS_FAIL_GRADE_THRESHOLD     : nota mínima para considerar reprobado  (default: 3.95)
        EWS_MAX_FAILED_SUBJECTS      : máx. asignaturas reprobadas sin riesgo (default: 2)
        EWS_CUTOFF_DESISTE           : fecha corte PRE/POST retiro DESISTE    (default: 2026-03-17)
        EWS_AGE_MIN                  : edad mínima esperada para anomalías    (default: 10)
        EWS_AGE_MAX                  : edad máxima esperada para anomalías    (default: 25)
        EWS_AGE_DIFF_THRESHOLD       : diferencia máx. edad rep vs calc       (default: 1.5)
    """

    # Riesgo académico
    attendance_risk_threshold_pct: float = field(
        default_factory=lambda: _env_float("EWS_ATTENDANCE_RISK_PCT", 84.45)
    )
    fail_grade_threshold: float = field(
        default_factory=lambda: _env_float("EWS_FAIL_GRADE_THRESHOLD", 3.95)
    )
    max_failed_subjects_allowed: int = field(
        default_factory=lambda: _env_int("EWS_MAX_FAILED_SUBJECTS", 2)
    )

    # Calendario escolar: corte PRE/POST retiro para DESISTE
    # PRE  (snapshot_date <= cutoff): DESISTE es universo aparte
    # POST (snapshot_date >  cutoff): DESISTE se ignora (ya entra como Fecha Retiro en matrícula)
    cutoff_desiste: str = field(
        default_factory=lambda: _env_str("EWS_CUTOFF_DESISTE", "2026-03-17")
    )

    # Anomalías de edad
    age_min: int = field(
        default_factory=lambda: _env_int("EWS_AGE_MIN", 10)
    )
    age_max: int = field(
        default_factory=lambda: _env_int("EWS_AGE_MAX", 25)
    )
    age_diff_threshold: float = field(
        default_factory=lambda: _env_float("EWS_AGE_DIFF_THRESHOLD", 1.5)
    )


BUSINESS_RULES = BusinessRules()


# ──────────────────────────────────────────────
# Especialidades por sección
# ──────────────────────────────────────────────

# Mapeo letra de curso → especialidad (A-H según tu liceo)
# Para agregar/cambiar especialidades: solo modifica este dict.
SPECIALTY_BY_SECTION: dict[str, str] = {
    "A": "TELECOM",
    "B": "TELECOM",
    "C": "TELECOM",
    "D": "TELECOM",
    "E": "ELECTRONICA",
    "F": "ELECTRONICA",
    "G": "MECANICA",
    "H": "MECANICA",
}


# ──────────────────────────────────────────────
# Retrocompatibilidad (evita romper imports existentes)
# ──────────────────────────────────────────────

# Estas constantes sueltas siguen funcionando si algún módulo las importa directamente.
# A futuro se pueden eliminar una vez que todo use BUSINESS_RULES.
ATTENDANCE_RISK_THRESHOLD_PCT = BUSINESS_RULES.attendance_risk_threshold_pct
FAIL_GRADE_THRESHOLD          = BUSINESS_RULES.fail_grade_threshold
MAX_FAILED_SUBJECTS_ALLOWED   = BUSINESS_RULES.max_failed_subjects_allowed