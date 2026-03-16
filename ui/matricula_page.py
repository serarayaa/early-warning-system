# ui/matricula_page.py
from __future__ import annotations

import os
import tempfile
from datetime import date, datetime
from io import BytesIO

import pandas as pd
import streamlit as st

from src.comparison.compare_enrollment import (
    compare_enrollment_snapshots,
    summarize_enrollment_comparison,
)
from src.validation.column_mapper import renombrar_dataframe_a_canonico
from src.validation.schema_registry import SCHEMA_DESISTE, SCHEMA_MATRICULA
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


def _usa_desiste_en_fecha_operativa() -> bool:
    hoy = date.today()
    return hoy.month == 3 and 1 <= hoy.day <= 16


def _usa_desiste_en_corte(stamp: str) -> bool:
    try:
        fecha = datetime.strptime(stamp, "%Y%m%d")
        return fecha.month == 3 and fecha.day <= 16
    except Exception:
        return False


def _procesar_archivo_matricula(uploaded_file, schema: dict, force: bool):
    resultado_validacion = None

    if uploaded_file is None:
        return False, "No se recibió archivo."

    try:
        if uploaded_file.name.lower().endswith(".csv"):
            preview_df = pd.read_csv(
                uploaded_file,
                sep=";",
                nrows=5,
                encoding="latin1",
                on_bad_lines="skip",
            )
        else:
            preview_df = pd.read_excel(uploaded_file, nrows=5)

        resultado_validacion = validar_columnas(preview_df.columns.tolist(), schema)
        mostrar_validacion_esquema(resultado_validacion)
        uploaded_file.seek(0)

        if not resultado_validacion["es_valido"]:
            return False, "El archivo no cumple con la estructura mínima esperada."

        if uploaded_file.name.lower().endswith(".csv"):
            df_raw = pd.read_csv(
                uploaded_file,
                sep=";",
                encoding="latin1",
                on_bad_lines="skip",
            )
            ext = ".csv"
        else:
            df_raw = pd.read_excel(uploaded_file)
            ext = ".xlsx"

        df_norm, resultado_mapeo = renombrar_dataframe_a_canonico(df_raw, schema)

        renombradas = {k: v for k, v in resultado_mapeo["mapeadas"].items() if k != v}
        if renombradas:
            filas = [{"Columna original": k, "Renombrada como": v} for k, v in renombradas.items()]
            st.markdown("**Renombrado automático aplicado**")
            st.dataframe(filas, use_container_width=True, hide_index=True)

        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp_path = tmp.name

        try:
            if ext == ".csv":
                df_norm.to_csv(tmp_path, index=False, sep=";", encoding="utf-8-sig")
            else:
                df_norm.to_excel(tmp_path, index=False)

            with open(tmp_path, "rb") as f:
                archivo_normalizado = BytesIO(f.read())
                archivo_normalizado.name = f"archivo_normalizado{ext}"

            ok, msg = process_enrollment_upload(archivo_normalizado, force=force)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

        return ok, msg

    except Exception as e:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
        return False, f"Error validando o procesando el archivo: {e}"


def render_matricula_page(
    stamp,
    prev_stamp,
    metrics,
    prev_metrics,
    df_current,
    df_prev_current,
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
    usa_desiste_historico = _usa_desiste_en_corte(stamp)
    usa_desiste_operativo = _usa_desiste_en_fecha_operativa()
    hoy = date.today()

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

    if matricula_file is not None:
        with st.spinner("Procesando matrícula..."):
            ok, msg = _procesar_archivo_matricula(
                uploaded_file=matricula_file,
                schema=SCHEMA_MATRICULA,
                force=force_matricula,
            )
        if ok:
            st.success(msg)
            st.cache_data.clear()
            st.rerun()
        else:
            st.error(msg)

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown('<div class="section-title">Carga de desiste</div>', unsafe_allow_html=True)

    if usa_desiste_operativo:
        st.markdown(
            f"""
            <div class="sigma-alert info">
                La fecha operativa actual es <b>{hoy.strftime('%d/%m/%Y')}</b>.<br>
                El archivo <b>Desiste</b> está habilitado porque aún estamos dentro del período
                transitorio del <b>1 al 16 de marzo</b>.
            </div>
            """,
            unsafe_allow_html=True,
        )

        desiste_file = st.file_uploader(
            "Cargar archivo de estudiantes que desistieron (.csv, .xlsx, .xls)",
            type=["csv", "xlsx", "xls"],
            key="desiste_uploader",
        )

        if desiste_file is not None:
            with st.spinner("Validando archivo Desiste..."):
                ok_des, msg_des = _procesar_archivo_matricula(
                    uploaded_file=desiste_file,
                    schema=SCHEMA_DESISTE,
                    force=force_matricula,
                )
            if ok_des:
                st.success("Archivo Desiste validado y procesado correctamente.")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(msg_des)
    else:
        st.markdown(
            f"""
            <div class="sigma-alert info">
                La fecha operativa actual es <b>{hoy.strftime('%d/%m/%Y')}</b>.<br><br>
                El archivo <b>Desiste</b> ya no corresponde cargarlo, porque su uso es solo
                entre el <b>1 y el 16 de marzo</b>.<br>
                Desde el <b>17 de marzo</b> en adelante, los movimientos deben analizarse desde
                el archivo de <b>Matrícula</b>, donde los casos pasan a considerarse <b>Retirados</b>.
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Comparación automática
    df_cmp = None
    resumen_cmp = None
    if (
        df_current is not None
        and not df_current.empty
        and df_prev_current is not None
        and not df_prev_current.empty
    ):
        try:
            df_cmp = compare_enrollment_snapshots(df_prev_current, df_current)
            resumen_cmp = summarize_enrollment_comparison(df_cmp)
        except Exception as e:
            st.markdown(
                f'<div class="sigma-alert danger">No se pudo comparar el corte actual con el anterior: {e}</div>',
                unsafe_allow_html=True,
            )

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

            if usa_desiste_historico and df_master is not None and not df_master.empty:
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

            if usa_desiste_historico:
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

            if usa_desiste_historico and total_pre:
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

        st.markdown('<div class="section-title">Comparación automática entre cargas</div>', unsafe_allow_html=True)

        if resumen_cmp is None:
            st.info("No hay suficiente información para comparar este corte con el anterior.")
        else:
            c1, c2, c3, c4, c5 = st.columns(5)
            with c1:
                _render_kpi_card("Nuevos", resumen_cmp["new"], "Comparado con el corte anterior", "green")
            with c2:
                _render_kpi_card("Removidos", resumen_cmp["removed"], "Comparado con el corte anterior", "red")
            with c3:
                _render_kpi_card("Actualizados", resumen_cmp["updated"], "Comparado con el corte anterior", "amber")
            with c4:
                _render_kpi_card("Transferencias", resumen_cmp["transfers"], "Detectadas", "cyan")
            with c5:
                _render_kpi_card("Cambios de estado", resumen_cmp["status_changes"], "Detectados")

            if (
                resumen_cmp["new"] == 0
                and resumen_cmp["removed"] == 0
                and resumen_cmp["updated"] == 0
                and resumen_cmp["transfers"] == 0
            ):
                st.markdown(
                    '<div class="sigma-alert success">✅ Sin cambios relevantes respecto al corte anterior.</div>',
                    unsafe_allow_html=True,
                )

            if df_cmp is not None and not df_cmp.empty:
                col_a, col_b = st.columns(2)

                with col_a:
                    st.markdown("**Nuevos ingresos**")
                    nuevos = df_cmp[df_cmp["change_type"] == "NEW"]
                    if nuevos.empty:
                        st.info("Sin nuevos ingresos.")
                    else:
                        st.dataframe(
                            nuevos[["rut_norm", "nombre", "curso_actual"]],
                            use_container_width=True,
                            hide_index=True,
                        )

                    st.markdown("**Transferencias internas detectadas**")
                    transfers = df_cmp[df_cmp["change_type"] == "TRANSFER_INTERNAL"]
                    if transfers.empty:
                        st.info("Sin transferencias internas detectadas.")
                    else:
                        st.dataframe(
                            transfers[
                                [
                                    "rut_norm",
                                    "nombre",
                                    "curso_anterior",
                                    "curso_actual",
                                    "estado_anterior",
                                    "estado_actual",
                                ]
                            ],
                            use_container_width=True,
                            hide_index=True,
                        )

                with col_b:
                    st.markdown("**Removidos**")
                    removidos = df_cmp[df_cmp["change_type"] == "REMOVED"]
                    if removidos.empty:
                        st.info("Sin removidos.")
                    else:
                        st.dataframe(
                            removidos[["rut_norm", "nombre", "curso_anterior"]],
                            use_container_width=True,
                            hide_index=True,
                        )

                st.markdown("**Cambios de estado**")
                cambios = df_cmp[df_cmp["change_type"] == "UPDATED"]
                if cambios.empty:
                    st.info("Sin cambios de estado.")
                else:
                    st.dataframe(
                        cambios[
                            [
                                "rut_norm",
                                "nombre",
                                "curso_anterior",
                                "curso_actual",
                                "estado_anterior",
                                "estado_actual",
                                "changed_fields",
                            ]
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )

        if df_current is not None and not df_current.empty:
            with st.expander("Ver matrícula actual completa", expanded=False):
                st.dataframe(df_current, use_container_width=True, hide_index=True)

        if df_transfers is not None and not df_transfers.empty:
            with st.expander("Ver transferencias detectadas", expanded=False):
                st.dataframe(df_transfers, use_container_width=True, hide_index=True)

    with tab_especialidad:
        st.markdown('<div class="section-title">Distribución por especialidad</div>', unsafe_allow_html=True)
        if df_specs is not None and not df_specs.empty:
            st.dataframe(df_specs, use_container_width=True, hide_index=True)
        else:
            st.info("No hay datos de especialidades para este corte.")

    with tab_desiste:
        if usa_desiste_historico:
            st.markdown('<div class="section-title">Desistimientos del corte actual</div>', unsafe_allow_html=True)

            if df_desiste_curr is not None and not df_desiste_curr.empty:
                st.dataframe(df_desiste_curr, use_container_width=True, hide_index=True)
            else:
                st.info("No hay desistimientos para este corte.")

            st.markdown('<div class="section-title">Comparación con corte anterior</div>', unsafe_allow_html=True)

            if df_desiste_prev is not None and not df_desiste_prev.empty:
                st.dataframe(df_desiste_prev, use_container_width=True, hide_index=True)
            else:
                st.info("No hay snapshot previo de desistimientos disponible.")
        else:
            st.markdown(
                """
                <div class="sigma-alert info">
                    El archivo <b>Desiste</b> se usa solo como dato transitorio entre el 1 y el 16 de marzo.
                    Desde el 17 de marzo en adelante, los movimientos deben analizarse desde el archivo de <b>Matrícula</b>.
                </div>
                """,
                unsafe_allow_html=True,
            )

    with tab_demo:
        st.markdown('<div class="section-title">Demografía general</div>', unsafe_allow_html=True)

        if df_demo is not None and not df_demo.empty:
            st.dataframe(df_demo, use_container_width=True, hide_index=True)
        else:
            st.info("No hay datos demográficos para este corte.")

        if df_comunas is not None and not df_comunas.empty:
            st.markdown("**Por comuna**")
            st.dataframe(df_comunas, use_container_width=True, hide_index=True)

        if df_nacs is not None and not df_nacs.empty:
            st.markdown("**Por nacionalidad**")
            st.dataframe(df_nacs, use_container_width=True, hide_index=True)

        if df_anomalies is not None and not df_anomalies.empty:
            st.markdown("**Anomalías de edad**")
            st.dataframe(df_anomalies, use_container_width=True, hide_index=True)

        if df_master is not None and not df_master.empty:
            st.markdown("**Métricas maestras**")
            st.dataframe(df_master, use_container_width=True, hide_index=True)