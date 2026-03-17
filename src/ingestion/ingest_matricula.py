from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

from src.config.settings import PATHS
from src.utils.logging_utils import get_logger

log = get_logger("EWS.ingest_matricula")

MANIFEST_PATH = PATHS.raw_matricula / "manifest.json"
ALLOWED_EXTS = {".csv", ".xlsx", ".xls"}


# ---------------------------------------------------
# Helpers
# ---------------------------------------------------
def compute_file_hash(file_path: Path) -> str:
    """
    Calcula hash SHA256 del archivo para detectar cambios reales.
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {"files": []}

    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        log.warning("⚠️ Manifest corrupto. Se reiniciará.")
        return {"files": []}


def save_manifest(data: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


# ---------------------------------------------------
# Ingest principal
# ---------------------------------------------------
def ingest(file_path: Path) -> Path:

    if not file_path.exists():
        raise FileNotFoundError(f"Archivo no encontrado: {file_path}")

    if file_path.suffix.lower() not in ALLOWED_EXTS:
        raise ValueError(f"Extensión no soportada: {file_path.suffix}")

    PATHS.raw_matricula.mkdir(parents=True, exist_ok=True)

    file_hash = compute_file_hash(file_path)
    file_size = file_path.stat().st_size

    manifest = load_manifest()

    # Buscar si el hash ya existe
    existing_entry = next(
        (entry for entry in manifest["files"] if entry["hash"] == file_hash),
        None
    )

    if existing_entry:
        existing_snapshot = PATHS.raw_matricula / existing_entry["snapshot_name"]
        log.info("🟦 Archivo ya fue cargado anteriormente.")
        log.info(f"   ↳ Snapshot existente: {existing_entry['snapshot_name']}")
        log.info(f"   ↳ Cargado en: {existing_entry['loaded_at']}")
        return existing_snapshot

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_name = f"matricula_snapshot_{timestamp}{file_path.suffix.lower()}"
    destination = PATHS.raw_matricula / snapshot_name

    shutil.copy2(file_path, destination)

    manifest["files"].append({
        "original_name": file_path.name,
        "snapshot_name": snapshot_name,
        "hash": file_hash,
        "size_bytes": file_size,
        "loaded_at": timestamp
    })

    save_manifest(manifest)

    log.info(f"✅ Snapshot guardado: {snapshot_name}")
    log.info(f"📦 Tamaño: {file_size:,} bytes")
    log.info("📘 Manifest actualizado correctamente.")
    return destination