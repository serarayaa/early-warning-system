# src/validation/column_mapper.py

from __future__ import annotations

import re
import unicodedata
import pandas as pd


def normalizar_texto(texto: str) -> str:
    if texto is None:
        return ""

    texto = str(texto).strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.replace("_", " ")
    texto = re.sub(r"\s+", " ", texto)

    return texto.strip()


def construir_diccionario_aliases(schema: dict) -> dict[str, str]:
    """
    Devuelve un diccionario:
    alias_normalizado -> campo_canonico
    """
    resultado = {}

    aliases = schema.get("aliases", {})
    for canonico, lista_aliases in aliases.items():
        resultado[normalizar_texto(canonico)] = canonico
        for alias in lista_aliases:
            resultado[normalizar_texto(alias)] = canonico

    return resultado


def mapear_columnas(columnas_originales: list[str], schema: dict) -> dict:
    """
    Intenta mapear columnas reales del archivo a nombres canónicos.
    """
    alias_map = construir_diccionario_aliases(schema)

    columnas_mapeadas = {}
    columnas_no_reconocidas = []

    for col in columnas_originales:
        col_norm = normalizar_texto(col)

        if col_norm in alias_map:
            columnas_mapeadas[col] = alias_map[col_norm]
        else:
            columnas_no_reconocidas.append(col)

    return {
        "mapeadas": columnas_mapeadas,
        "no_reconocidas": columnas_no_reconocidas,
    }


def renombrar_dataframe_a_canonico(df: pd.DataFrame, schema: dict) -> tuple[pd.DataFrame, dict]:
    """
    Renombra columnas del DataFrame usando el esquema y devuelve:
    - df renombrado
    - resultado del mapeo
    """
    resultado = mapear_columnas(df.columns.tolist(), schema)
    mapping = resultado["mapeadas"]

    df_out = df.copy()
    df_out = df_out.rename(columns=mapping)

    return df_out, resultado