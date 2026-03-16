# ui/matricula_page.py
from __future__ import annotations

import os
import tempfile
from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st

from src.validation.column_mapper import renombrar_dataframe_a_canonico
from src.validation.schema_registry import SCHEMA_MATRICULA
from src.validation.schema_validator import validar_columnas
from ui.enrollment_processing import process_enrollment_upload
from ui.schema_feedback import mostrar_validacion_esquema


def _safe_int(value, default: int = 0) -> int:
    try:
        if pd.isna(value):
            return default
        return int(value)
    except Exception:
        return default


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _delta_str(curr: int, prev_df, col: str) -> tuple[str, str]:
    if prev_df is None or prev_df.empty:
        return "—", "neu"
    try:
        prev = _safe_int(prev_df.iloc[0].get(col, 0))
        diff = curr - prev
        if diff > 0:
            return f"+{diff} vs anterior", "up"
        if diff < 0:
            return f"{diff} vs anterior", "down"
        return "Sin cambios", "neu"
    except Exception:
        return "—", "neu"


def _render_kpi_card(label: str, value: str | int, delta: str = "—", klass: str = ""):
    st.markdown(
        f"""
        <div class="kpi-card {klass}">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-delta">{delta}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _usa_desiste_en_corte(stamp: str) -> bool:
    """
    Desiste se usa solo como dato transitorio entre el 1 y el 16 de marzo.
    """
    try:
        fecha = datetime.strptime(stamp, "%Y%m%d")
        return fecha.month == 3 and fecha.day <= 16
    except Exception:
        return False


def render_matricula_page(
    stamp,
    prev_stamp,
    metrics,
    prev_metrics,
    df_current,
    df_demo,
    df_comunas,
    df_nacs,
    df_specs,
    df_anomalies,
    df_master,
    df_transfers,
    df_diff,
    df_desiste_curr,
    df_desiste_prev,
):
    usa_desiste = _usa_desiste_en_corte(stamp)

    st.markdown(
        """
        <div class="sigma-header">
            <div>
                <div class="sigma-logo" style="font-size:1.5rem">SIGMA</div>
                <div class="sigma-tagline">Matrícula</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-title">Carga de matrícula</div>', unsafe_allow_html=True)

    col_up_1, col_up_2 = st.columns([3, 1])

    with col_up_1:
        matricula_file = st.file_uploader(
            "Cargar archivo de matrícula desde Syscol (.csv, .xlsx, .xls)",
            type=["csv", "xlsx", "xls"],
            key="matricula_uploader",
        )

    with col_up_2:
        force_matricula = st.checkbox("Forzar reproceso", value=False)

    resultado_validacion = None

    # Validación visual del archivo
    if matricula_file is not None:
        try:
            if matricula_file.name.lower().endswith(".csv"):
                preview_df = pd.read_csv(matricula_file, nrows=5, sep=";")
            else:
                preview_df = pd.read_excel(matricula_file, nrows=5)

            resultado_validacion = validar_columnas(
                preview_df.columns.tolist(),
                SCHEMA_MATRICULA,
            )
            mostrar_validacion_esquema(resultado_validacion)
            matricula_file.seek(0)

        except Exception as e:
            st.markdown(
                f'<div class="sigma-alert danger">No se pudo analizar la estructura del archivo: {e}</div>',
                unsafe_allow_html=True,
            )
            matricula_file.seek(0)

    if st.button("Procesar matrícula", type="primary", use_container_width=False):
        if matricula_file is None:
            st.warning("Primero debes subir un archivo de matrícula.")
        else:
            try:
                if resultado_validacion is not None and not resultado_validacion["es_valido"]:
                    st.error("El archivo no cumple con la estructura mínima esperada para Matrícula.")
                else:
                    matricula_file.seek(0)

                    if matricula_file.name.lower().endswith(".csv"):
                        df_raw = pd.read_csv(matricula_file, sep=";")
                        ext = ".csv"
                    else:
                        df_raw = pd.read_excel(matricula_file)
                        ext = ".xlsx"

                    df_norm, resultado_mapeo = renombrar_dataframe_a_canonico(
                        df_raw,
                        SCHEMA_MATRICULA,
                    )

                    renombradas = {
                        k: v for k, v in resultado_mapeo["mapeadas"].items()
                        if k != v
                    }

                    if renombradas:
                        filas = [
                            {"Columna original": k, "Renombrada como": v}
                            for k, v in renombradas.items()
                        ]
                        st.markdown("**Renombrado automático aplicado**")
                        st.dataframe(filas, use_container_width=True, hide_index=True)

                    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                        tmp_path = tmp.name

                    try:
                        if ext == ".csv":
                            df_norm.to_csv(tmp_path, index=False, encoding="utf-8-sig", sep=";")
                        else:
                            df_norm.to_excel(tmp_path, index=False)

                        with open(tmp_path, "rb") as f:
                            archivo_normalizado = BytesIO(f.read())
                            archivo_normalizado.name = f"matricula_normalizada{ext}"

                        with st.spinner("Procesando matrícula..."):
                            ok, msg = process_enrollment_upload(
                                archivo_normalizado,
                                force=force_matricula,
                            )

                    finally:
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)

                    if ok:
                        st.success(msg)
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(msg)

            except Exception as e:
                st.error(f"Error validando o procesando el archivo: {e}")

    st.markdown("<br>", unsafe_allow_html=True)

    tab_dash, tab_especialidad, tab_desiste, tab_demo = st.tabs(
        ["Dashboard", "Especialidades", "Desistimientos", "Demografía"]
    )

    with tab_dash:
        if metrics is None or metrics.empty:
            st.markdown(
                '<div class="sigma-alert danger">Sin datos de métricas para este corte.</div>',
                unsafe_allow_html=True,
            )
        else:
            row = metrics.iloc[0].to_dict()

            matriculados = _safe_int(row.get("matriculados_actuales", 0))
            retirados = _safe_int(row.get("retirados_reales", 0))
            transferencias = _safe_int(row.get("transferencias_internas", 0))
            ruts_unicos = _safe_int(row.get("ruts_unicos", 0))

            desiste_total = 0
            total_pre = ""
            phase = ""

            if usa_desiste and df_master is not None and not df_master.empty:
                mr = df_master.iloc[0].to_dict()
                desiste_total = _safe_int(mr.get("desiste_total", 0))
                total_pre = str(mr.get("total_esperado_pre_marzo", "") or "")
                phase = str(mr.get("phase", "") or "")

            sexo_m = sexo_f = 0
            edad_prom = rep_pct = extranjeros_pct = 0.0

            if df_demo is not None and not df_demo.empty:
                dr = df_demo.iloc[0].to_dict()
                sexo_m = _safe_int(dr.get("sexo_m", 0))
                sexo_f = _safe_int(dr.get("sexo_f", 0))
                edad_prom = _safe_float(dr.get("edad_promedio", 0))
                rep_pct = _safe_float(dr.get("repitentes_pct", 0))
                extranjeros_pct = _safe_float(
                    dr.get("extranjeros_pct_sobre_nacionalidad_no_vacia", 0)
                )

            d_mat, _ = _delta_str(matriculados, prev_metrics, "matriculados_actuales")
            d_ret, _ = _delta_str(retirados, prev_metrics, "retirados_reales")
            d_trf, _ = _delta_str(transferencias, prev_metrics, "transferencias_internas")

            pct_m = round((sexo_m / matriculados) * 100, 1) if matriculados else 0
            pct_f = round((sexo_f / matriculados) * 100, 1) if matriculados else 0

            st.markdown('<div class="section-title">Indicadores clave</div>', unsafe_allow_html=True)

            if usa_desiste:
                c1, c2, c3, c4, c5, c6 = st.columns(6)
                with c1:
                    _render_kpi_card("Matriculados", f"{matriculados:,}", d_mat, "green")
                with c2:
                    _render_kpi_card("Hombres", f"{sexo_m:,}", f"{pct_m}% del total", "cyan")
                with c3:
                    _render_kpi_card("Mujeres", f"{sexo_f:,}", f"{pct_f}% del total", "cyan")
                with c4:
                    _render_kpi_card("Desiste", f"{desiste_total:,}", f"Phase: {phase}" if phase else "—", "amber")
                with c5:
                    _render_kpi_card("Retirados reales", f"{retirados:,}", d_ret, "red")
                with c6:
                    _render_kpi_card("Transferencias", f"{transferencias:,}", d_trf)
            else:
                c1, c2, c3, c4, c5 = st.columns(5)
                with c1:
                    _render_kpi_card("Matriculados", f"{matriculados:,}", d_mat, "green")
                with c2:
                    _render_kpi_card("Hombres", f"{sexo_m:,}", f"{pct_m}% del total", "cyan")
                with c3:
                    _render_kpi_card("Mujeres", f"{sexo_f:,}", f"{pct_f}% del total", "cyan")
                with c4:
                    _render_kpi_card("Retirados reales", f"{retirados:,}", d_ret, "red")
                with c5:
                    _render_kpi_card("Transferencias", f"{transferencias:,}", d_trf)

            if usa_desiste and total_pre:
                st.markdown(
                    f"""
                    <div class="sigma-panel">
                        <div class="stat-row">
                            <div class="stat-item">
                                <div class="s-label">Total esperado pre-marzo</div>
                                <div class="s-value">{total_pre}</div>
                            </div>
                            <div class="stat-item">
                                <div class="s-label">Interpretación</div>
                                <div class="s-value">Matrícula + Desiste</div>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            st.markdown('<div class="section-title">Perfil del alumnado</div>', unsafe_allow_html=True)
            st.markdown(
                f"""
                <div class="sigma-panel">
                    <div class="stat-row">
                        <div class="stat-item">
                            <div class="s-label">Edad promedio</div>
                            <div class="s-value">{edad_prom:.1f} años</div>
                        </div>
                        <div class="stat-item">
                            <div class="s-label">% Repitentes</div>
                            <div class="s-value">{rep_pct:.1f}%</div>
                        </div>
                        <div class="stat-item">
                            <div class="s-label">% Extranjeros</div>
                            <div class="s-value">{extranjeros_pct:.1f}%</div>
                        </div>
                        <div class="stat-item">
                            <div class="s-label">RUTs únicos</div>
                            <div class="s-value">{ruts_unicos:,}</div>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if df_diff is not None and not df_diff.empty and "change_type" in df_diff.columns:
            st.markdown('<div class="section-title">Cambios vs corte anterior</div>', unsafe_allow_html=True)

            counts = df_diff["change_type"].value_counts().to_dict()
            new_c = counts.get("NEW", 0)
            upd_c = counts.get("UPDATED", 0)
            del_c = counts.get("DELETED", 0)