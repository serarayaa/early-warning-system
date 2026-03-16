# src/validation/schema_validator.py

from __future__ import annotations

from src.validation.column_mapper import mapear_columnas


def validar_columnas(columnas_archivo: list[str], schema: dict) -> dict:
    """
    Valida columnas de un archivo contra un esquema esperado.
    """
    resultado_mapeo = mapear_columnas(columnas_archivo, schema)
    mapeadas = resultado_mapeo["mapeadas"]
    no_reconocidas = resultado_mapeo["no_reconocidas"]

    canonicas_detectadas = set(mapeadas.values())

    required = set(schema.get("required", []))
    optional = set(schema.get("optional", []))

    obligatorias_detectadas = sorted(required.intersection(canonicas_detectadas))
    obligatorias_faltantes = sorted(required - canonicas_detectadas)
    opcionales_detectadas = sorted(optional.intersection(canonicas_detectadas))

    es_valido = len(obligatorias_faltantes) == 0

    return {
        "es_valido": es_valido,
        "nombre_esquema": schema.get("nombre", "Archivo"),
        "columnas_originales": columnas_archivo,
        "mapeo_original_a_canonico": mapeadas,
        "columnas_no_reconocidas": no_reconocidas,
        "obligatorias_detectadas": obligatorias_detectadas,
        "obligatorias_faltantes": obligatorias_faltantes,
        "opcionales_detectadas": opcionales_detectadas,
        "total_obligatorias": len(required),
        "total_detectadas": len(obligatorias_detectadas),
    }