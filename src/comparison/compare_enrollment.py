# src/comparison/compare_enrollment.py
from __future__ import annotations

import pandas as pd


def _pick_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _prepare_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    """
    Estandariza columnas clave para comparar snapshots de matrícula.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["rut_key", "nombre_ref", "curso_ref", "estado_ref"])

    df2 = df.copy()

    rut_col = _pick_col(df2, ["rut_norm", "rut", "numero_rut", "Número Rut"])
    nombre_col = _pick_col(df2, ["nombre", "Nombre"])
    curso_col = _pick_col(df2, ["course_code", "codigo_curso", "curso", "Código Curso", "CCurso"])
    estado_col = _pick_col(df2, ["estado_matricula", "Estado Matrícula"])

    if rut_col is None:
        raise ValueError("No se encontró columna de RUT para comparar snapshots de matrícula.")

    df2["rut_key"] = df2[rut_col].astype(str).str.strip()
    df2["nombre_ref"] = df2[nombre_col].astype(str).str.strip() if nombre_col else ""
    df2["curso_ref"] = df2[curso_col].astype(str).str.strip() if curso_col else ""
    df2["estado_ref"] = df2[estado_col].astype(str).str.strip() if estado_col else ""

    df2 = df2.drop_duplicates(subset=["rut_key"], keep="last")

    return df2[["rut_key", "nombre_ref", "curso_ref", "estado_ref"]]


def compare_enrollment_snapshots(
    df_prev: pd.DataFrame | None,
    df_curr: pd.DataFrame | None,
) -> pd.DataFrame:
    """
    Compara dos snapshots de matrícula y clasifica cada RUT.
    """
    prev = _prepare_snapshot(df_prev) if df_prev is not None else pd.DataFrame(
        columns=["rut_key", "nombre_ref", "curso_ref", "estado_ref"]
    )
    curr = _prepare_snapshot(df_curr) if df_curr is not None else pd.DataFrame(
        columns=["rut_key", "nombre_ref", "curso_ref", "estado_ref"]
    )

    merged = prev.merge(
        curr,
        on="rut_key",
        how="outer",
        suffixes=("_prev", "_curr"),
        indicator=True,
    )

    def classify(row):
        if row["_merge"] == "right_only":
            return "NEW"

        if row["_merge"] == "left_only":
            return "REMOVED"

        curso_prev = str(row.get("curso_ref_prev", "") or "").strip()
        curso_curr = str(row.get("curso_ref_curr", "") or "").strip()
        estado_prev = str(row.get("estado_ref_prev", "") or "").strip()
        estado_curr = str(row.get("estado_ref_curr", "") or "").strip()

        if curso_prev != curso_curr:
            return "TRANSFER_INTERNAL"

        if estado_prev != estado_curr:
            return "UPDATED"

        return "UNCHANGED"

    merged["change_type"] = merged.apply(classify, axis=1)

    def changed_fields(row):
        fields = []

        if row["_merge"] == "both":
            curso_prev = str(row.get("curso_ref_prev", "") or "").strip()
            curso_curr = str(row.get("curso_ref_curr", "") or "").strip()
            estado_prev = str(row.get("estado_ref_prev", "") or "").strip()
            estado_curr = str(row.get("estado_ref_curr", "") or "").strip()

            if curso_prev != curso_curr:
                fields.append("curso")
            if estado_prev != estado_curr:
                fields.append("estado_matricula")

        return ", ".join(fields)

    merged["changed_fields"] = merged.apply(changed_fields, axis=1)

    merged["nombre"] = merged["nombre_ref_curr"].fillna(merged["nombre_ref_prev"]).fillna("")
    merged["curso_anterior"] = merged["curso_ref_prev"].fillna("")
    merged["curso_actual"] = merged["curso_ref_curr"].fillna("")
    merged["estado_anterior"] = merged["estado_ref_prev"].fillna("")
    merged["estado_actual"] = merged["estado_ref_curr"].fillna("")

    return merged[
        [
            "rut_key",
            "nombre",
            "curso_anterior",
            "curso_actual",
            "estado_anterior",
            "estado_actual",
            "change_type",
            "changed_fields",
        ]
    ].rename(columns={"rut_key": "rut_norm"})


def summarize_enrollment_comparison(df_cmp: pd.DataFrame | None) -> dict[str, int]:
    if df_cmp is None or df_cmp.empty:
        return {
            "new": 0,
            "removed": 0,
            "updated": 0,
            "unchanged": 0,
            "transfers": 0,
            "status_changes": 0,
        }

    return {
        "new": int((df_cmp["change_type"] == "NEW").sum()),
        "removed": int((df_cmp["change_type"] == "REMOVED").sum()),
        "updated": int((df_cmp["change_type"] == "UPDATED").sum()),
        "unchanged": int((df_cmp["change_type"] == "UNCHANGED").sum()),
        "transfers": int((df_cmp["change_type"] == "TRANSFER_INTERNAL").sum()),
        "status_changes": int(df_cmp["changed_fields"].fillna("").str.contains("estado_matricula").sum()),
    }