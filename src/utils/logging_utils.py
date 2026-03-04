from __future__ import annotations

import logging
import logging.config
from pathlib import Path
import yaml


def setup_logging(logging_yaml_path: Path) -> None:
    """
    Carga configuración de logging desde YAML.
    """
    with open(logging_yaml_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # asegurar carpeta logs/ (por si no existe)
    log_file = config.get("handlers", {}).get("file", {}).get("filename")
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    logging.config.dictConfig(config)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)