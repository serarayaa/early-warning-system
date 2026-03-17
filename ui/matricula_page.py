# ui/matricula_page.py
from __future__ import annotations

import os
import tempfile
from datetime import date, datetime, timedelta
from io import BytesIO

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.config.settings import BUSINESS_RULES
from src.validation.column_mapper import renombrar_dataframe_a_canonico
from src.validation.schema_registry import SCHEMA_DESISTE, SCHEMA_MATRICULA
from src.validation.schema_validator import validar_columnas
from ui.executive_pdf import generate_executive_pdf, render_pdf_preview, show_pretty_table
from ui.enrollment_processing import process_enrollment_upload
from ui.schema_feedback import mostrar_validacion_esquema

MIME_CSV = "text/csv"


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


def _delta_mini(curr: int, prev_df, col: str) -> str:
    if prev_df is None or prev_df.empty:
        return "—"
    try:
        prev = _safe_int(prev_df.iloc[0].get(col, 0))
        diff = curr - prev
        if diff > 0:
            return f"+{diff}"
        if diff < 0:
            return f"{diff}"
        return "0"
    except Exception:
        return "—"


def _delta_mini_vals(curr: int, prev: int | None) -> str:
    if prev is None:
        return "—"
    diff = curr - prev
    if diff > 0:
        return f"+{diff}"
    if diff < 0:
        return f"{diff}"
    return "0"


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
    try:
        cutoff = pd.to_datetime(BUSINESS_RULES.cutoff_desiste).date()
        return date.today() <= cutoff
    except Exception:
        hoy = date.today()
        return hoy.month == 3 and 1 <= hoy.day <= 16


def _usa_desiste_en_corte(stamp: str) -> bool:
    try:
        fecha = datetime.strptime(stamp, "%Y%m%d")
        cutoff = pd.to_datetime(BUSINESS_RULES.cutoff_desiste)
        return fecha <= cutoff
    except Exception:
        return False


def _cutoff_desiste_date() -> date:
    try:
        return pd.to_datetime(BUSINESS_RULES.cutoff_desiste).date()
    except Exception:
        return date(2026, 3, 16)


def _read_csv_uploaded(uploaded_file, nrows: int | None = None) -> pd.DataFrame:
    last_err: Exception | None = None
    for enc in ["utf-8", "utf-8-sig", "cp1252", "latin1"]:
        try:
            uploaded_file.seek(0)
            return pd.read_csv(
                uploaded_file,
                sep=";",
                nrows=nrows,
                encoding=enc,
                on_bad_lines="skip",
            )
        except Exception as e:
            last_err = e
    raise ValueError(f"No se pudo leer CSV de matrícula con encodings esperados: {last_err}")


def _to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def _procesar_archivo_matricula(uploaded_file, schema: dict, force: bool):
    resultado_validacion = None

    if uploaded_file is None:
        return False, "No se recibió archivo."

    try:
        if uploaded_file.name.lower().endswith(".csv"):
            preview_df = _read_csv_uploaded(uploaded_file, nrows=5)
        else:
            preview_df = pd.read_excel(uploaded_file, nrows=5)

        resultado_validacion = validar_columnas(preview_df.columns.tolist(), schema)
        mostrar_validacion_esquema(resultado_validacion)
        uploaded_file.seek(0)

        if not resultado_validacion["es_valido"]:
            return False, "El archivo no cumple con la estructura mínima esperada."

        if uploaded_file.name.lower().endswith(".csv"):
            df_raw = _read_csv_uploaded(uploaded_file)
            ext = ".csv"
        else:
            df_raw = pd.read_excel(uploaded_file)
            ext = ".xlsx"

        df_norm, resultado_mapeo = renombrar_dataframe_a_canonico(df_raw, schema)

        renombradas = {k: v for k, v in resultado_mapeo["mapeadas"].items() if k != v}
        if renombradas:
            filas = [{"Columna original": k, "Renombrada como": v} for k, v in renombradas.items()]
            st.markdown("**Renombrado automático aplicado**")
            show_pretty_table(pd.DataFrame(filas), max_rows=50, height=220)

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
    metrics,
    prev_metrics,
    df_current,
    df_prev_current,
    df_demo,
    df_comunas,
    df_nacs,
    df_specs,
):
    usa_desiste_historico = _usa_desiste_en_corte(stamp)
    usa_desiste_operativo = _usa_desiste_en_fecha_operativa()
    hoy = date.today()
    cutoff_desiste = _cutoff_desiste_date()
    inicio_desiste = date(cutoff_desiste.year, 3, 1)
    dia_post = cutoff_desiste + timedelta(days=1)

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
                transitorio del <b>{inicio_desiste.strftime('%d/%m')} al {cutoff_desiste.strftime('%d/%m')}</b>.
            </div>
            """,
            unsafe_allow_html=True,
        )

        desiste_file = st.file_uploader(
            "Cargar archivo de estudiantes que desistieron (.csv, .xlsx, .xls)",
            type=["csv", "xlsx", "xls"],
            key="desiste_uploader_enabled",
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
                entre el <b>{inicio_desiste.strftime('%d/%m')}</b> y el <b>{cutoff_desiste.strftime('%d/%m')}</b>.<br>
                Desde el <b>{dia_post.strftime('%d/%m')}</b> en adelante, los movimientos deben analizarse desde
                el archivo de <b>Matrícula</b>, donde los casos pasan a considerarse <b>Retirados</b>.
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.file_uploader(
            "Carga de Desiste deshabilitada fuera de período",
            type=["csv", "xlsx", "xls"],
            key="desiste_uploader_disabled",
            disabled=True,
            help="Habilitado solo en el período transitorio de DESISTE.",
        )

    st.markdown("<br>", unsafe_allow_html=True)

    row = metrics.iloc[0].to_dict() if metrics is not None and not metrics.empty else {}

    matriculados = _safe_int(row.get("matriculados_actuales", 0))
    retirados = _safe_int(row.get("retirados_reales", 0))
    transferencias = _safe_int(row.get("transferencias_internas", 0))
    ruts_unicos = _safe_int(row.get("ruts_unicos", 0))

    df_curr = df_current.copy() if df_current is not None else pd.DataFrame()
    df_prev = df_prev_current.copy() if df_prev_current is not None else pd.DataFrame()

    if not df_curr.empty:
        sexo_curr = df_curr.get("sexo", pd.Series(dtype=str)).astype(str).str.upper().str.strip()
        hombres = int(sexo_curr.isin(["M", "MASCULINO"]).sum())
        mujeres = int(sexo_curr.isin(["F", "FEMENINO"]).sum())
        extranjeros = int(
            ~df_curr.get("nacionalidad", pd.Series(dtype=str)).fillna("").astype(str).str.upper().str.strip().isin(
                ["CHILENA", "CHILENO", "CHILE", ""]
            )
        .sum())
        comunas_count = int(df_curr.get("comuna", pd.Series(dtype=str)).fillna("").astype(str).str.strip().replace("", pd.NA).dropna().nunique())
    else:
        hombres = mujeres = extranjeros = comunas_count = 0

    if not df_prev.empty:
        sexo_prev = df_prev.get("sexo", pd.Series(dtype=str)).astype(str).str.upper().str.strip()
        hombres_prev = int(sexo_prev.isin(["M", "MASCULINO"]).sum())
        mujeres_prev = int(sexo_prev.isin(["F", "FEMENINO"]).sum())
        extranjeros_prev = int(
            ~df_prev.get("nacionalidad", pd.Series(dtype=str)).fillna("").astype(str).str.upper().str.strip().isin(
                ["CHILENA", "CHILENO", "CHILE", ""]
            )
        .sum())
        comunas_prev = int(df_prev.get("comuna", pd.Series(dtype=str)).fillna("").astype(str).str.strip().replace("", pd.NA).dropna().nunique())
    else:
        hombres_prev = mujeres_prev = extranjeros_prev = comunas_prev = None

    st.markdown('<div class="section-title">Indicadores actualizados</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _render_kpi_card("Matriculados", f"{matriculados:,}", _delta_mini(matriculados, prev_metrics, "matriculados_actuales"), "green")
    with c2:
        _render_kpi_card("Retirados", f"{retirados:,}", _delta_mini(retirados, prev_metrics, "retirados_reales"), "red")
    with c3:
        _render_kpi_card("Transferencias", f"{transferencias:,}", _delta_mini(transferencias, prev_metrics, "transferencias_internas"), "amber")
    with c4:
        _render_kpi_card("RUT únicos", f"{ruts_unicos:,}", _delta_mini(ruts_unicos, prev_metrics, "ruts_unicos"), "cyan")

    c5, c6, c7, c8 = st.columns(4)
    with c5:
        _render_kpi_card("Hombres", f"{hombres:,}", _delta_mini_vals(hombres, hombres_prev), "cyan")
    with c6:
        _render_kpi_card("Mujeres", f"{mujeres:,}", _delta_mini_vals(mujeres, mujeres_prev), "cyan")
    with c7:
        _render_kpi_card("Extranjeros", f"{extranjeros:,}", _delta_mini_vals(extranjeros, extranjeros_prev), "amber")
    with c8:
        _render_kpi_card("Comunas", f"{comunas_count:,}", _delta_mini_vals(comunas_count, comunas_prev), "green")

    st.markdown('<div class="section-title">Visualizaciones relevantes</div>', unsafe_allow_html=True)

    sexo_df = pd.DataFrame({"Sexo": ["Hombres", "Mujeres"], "Cantidad": [hombres, mujeres]})

    if df_specs is not None and not df_specs.empty:
        specs_chart = df_specs.copy().head(10)
        x_spec = specs_chart.iloc[:, 0].astype(str)
        y_spec = pd.to_numeric(specs_chart.iloc[:, 1], errors="coerce").fillna(0)
    elif not df_curr.empty and "specialty" in df_curr.columns:
        tmp_spec = (
            df_curr["specialty"].fillna("SIN DATOS").astype(str).str.upper().value_counts().head(10).reset_index()
        )
        tmp_spec.columns = ["Especialidad", "Total"]
        x_spec, y_spec = tmp_spec["Especialidad"], tmp_spec["Total"]
    else:
        x_spec, y_spec = pd.Series(dtype=str), pd.Series(dtype=float)

    if df_comunas is not None and not df_comunas.empty:
        comunas_chart = df_comunas.copy().head(10)
        x_com, y_com = comunas_chart.iloc[:, 0].astype(str), pd.to_numeric(comunas_chart.iloc[:, 1], errors="coerce").fillna(0)
    elif not df_curr.empty and "comuna" in df_curr.columns:
        tmp_com = (
            df_curr["comuna"].fillna("SIN DATOS").astype(str).str.upper().value_counts().head(10).reset_index()
        )
        tmp_com.columns = ["Comuna", "Total"]
        x_com, y_com = tmp_com["Comuna"], tmp_com["Total"]
    else:
        x_com, y_com = pd.Series(dtype=str), pd.Series(dtype=float)

    g1, g2, g3 = st.columns(3)
    with g1:
        fig_sexo = go.Figure(
            data=[go.Pie(labels=sexo_df["Sexo"], values=sexo_df["Cantidad"], hole=0.45, marker={"colors": ["#2563eb", "#16a34a"]})]
        )
        fig_sexo.update_layout(
            paper_bgcolor="#0d1220",
            plot_bgcolor="#0d1220",
            font={"color": "#e2e8f0"},
            height=300,
            margin={"l": 10, "r": 10, "t": 40, "b": 10},
            title={"text": "Distribución por sexo", "font": {"size": 12, "color": "#63b3ed"}, "x": 0},
        )
        st.plotly_chart(fig_sexo, use_container_width=True, config={"displayModeBar": False})

    with g2:
        fig_specs = go.Figure(
            data=[go.Bar(x=x_spec, y=y_spec, marker_color="#7c3aed", hovertemplate="<b>%{x}</b>: %{y}<extra></extra>")]
        )
        fig_specs.update_layout(
            paper_bgcolor="#0d1220",
            plot_bgcolor="#0d1220",
            font={"color": "#e2e8f0"},
            height=300,
            margin={"l": 10, "r": 10, "t": 40, "b": 10},
            title={"text": "Top especialidades", "font": {"size": 12, "color": "#63b3ed"}, "x": 0},
            xaxis={"tickangle": -20, "gridcolor": "#1a2035"},
            yaxis={"gridcolor": "#1a2035"},
        )
        st.plotly_chart(fig_specs, use_container_width=True, config={"displayModeBar": False})

    with g3:
        fig_com = go.Figure(
            data=[go.Bar(x=x_com, y=y_com, marker_color="#d97706", hovertemplate="<b>%{x}</b>: %{y}<extra></extra>")]
        )
        fig_com.update_layout(
            paper_bgcolor="#0d1220",
            plot_bgcolor="#0d1220",
            font={"color": "#e2e8f0"},
            height=300,
            margin={"l": 10, "r": 10, "t": 40, "b": 10},
            title={"text": "Top comunas", "font": {"size": 12, "color": "#63b3ed"}, "x": 0},
            xaxis={"tickangle": -20, "gridcolor": "#1a2035"},
            yaxis={"gridcolor": "#1a2035"},
        )
        st.plotly_chart(fig_com, use_container_width=True, config={"displayModeBar": False})

    st.markdown('<div class="section-title">Detalle actualizado</div>', unsafe_allow_html=True)
    d1, d2 = st.columns(2)
    with d1:
        st.markdown("**Nacionalidades (top)**")
        if df_nacs is not None and not df_nacs.empty:
            show_pretty_table(df_nacs.head(15), max_rows=15, height=320)
        else:
            st.info("No hay datos de nacionalidades para este corte.")

    with d2:
        st.markdown("**Especialidades**")
        if df_specs is not None and not df_specs.empty:
            show_pretty_table(df_specs.head(15), max_rows=15, height=320)
        else:
            st.info("No hay datos de especialidades para este corte.")

    if df_current is not None and not df_current.empty:
        with st.expander("Ver matrícula actual completa", expanded=False):
            show_pretty_table(df_current, max_rows=250, height=430)

    st.markdown('<div class="section-title">Reportes y DATA entregable</div>', unsafe_allow_html=True)

    resumen = pd.DataFrame(
        [
            {
                "corte": stamp,
                "matriculados": int(metrics.iloc[0].get("matriculados_actuales", 0)) if metrics is not None and not metrics.empty else 0,
                "retirados_reales": int(metrics.iloc[0].get("retirados_reales", 0)) if metrics is not None and not metrics.empty else 0,
                "transferencias_internas": int(metrics.iloc[0].get("transferencias_internas", 0)) if metrics is not None and not metrics.empty else 0,
                "ruts_unicos": int(metrics.iloc[0].get("ruts_unicos", 0)) if metrics is not None and not metrics.empty else 0,
                "usa_desiste_en_corte": "SI" if usa_desiste_historico else "NO",
            }
        ]
    )
    show_pretty_table(resumen, max_rows=5, height=110)

    d1, d2, d3, d4 = st.columns(4)
    d1.download_button(
        "Resumen",
        data=_to_csv_bytes(resumen),
        file_name=f"matricula_resumen__{stamp}.csv",
        mime=MIME_CSV,
        use_container_width=True,
        key=f"dl_matricula_resumen_{stamp}",
    )
    d2.download_button(
        "Matrícula actual",
        data=_to_csv_bytes(df_current if df_current is not None else pd.DataFrame()),
        file_name=f"enrollment_current__{stamp}.csv",
        mime=MIME_CSV,
        use_container_width=True,
        key=f"dl_matricula_current_{stamp}",
    )
    d3.download_button(
        "Especialidades",
        data=_to_csv_bytes(df_specs if df_specs is not None else pd.DataFrame()),
        file_name=f"enrollment_specialty__{stamp}.csv",
        mime=MIME_CSV,
        use_container_width=True,
        key=f"dl_matricula_specs_{stamp}",
    )
    d4.download_button(
        "Demografía",
        data=_to_csv_bytes(df_demo if df_demo is not None else pd.DataFrame()),
        file_name=f"enrollment_demographics__{stamp}.csv",
        mime=MIME_CSV,
        use_container_width=True,
        key=f"dl_matricula_demo_{stamp}",
    )

    pdf_kpis = {
        "corte": stamp,
        "matriculados": int(metrics.iloc[0].get("matriculados_actuales", 0)) if metrics is not None and not metrics.empty else 0,
        "retirados_reales": int(metrics.iloc[0].get("retirados_reales", 0)) if metrics is not None and not metrics.empty else 0,
        "transferencias_internas": int(metrics.iloc[0].get("transferencias_internas", 0)) if metrics is not None and not metrics.empty else 0,
        "ruts_unicos": int(metrics.iloc[0].get("ruts_unicos", 0)) if metrics is not None and not metrics.empty else 0,
        "usa_desiste_en_corte": "SI" if usa_desiste_historico else "NO",
    }

    tables_for_pdf: list[tuple[str, pd.DataFrame]] = [("Resumen ejecutivo", resumen)]
    if df_current is not None and not df_current.empty:
        tables_for_pdf.append(("Matricula actual (muestra)", df_current.head(25)))
    if df_specs is not None and not df_specs.empty:
        tables_for_pdf.append(("Distribucion por especialidad", df_specs.head(25)))
    if df_demo is not None and not df_demo.empty:
        tables_for_pdf.append(("Demografia general", df_demo.head(25)))

    pdf_bytes = generate_executive_pdf(
        module_name="Matricula",
        corte=str(stamp),
        kpis=pdf_kpis,
        tables=tables_for_pdf,
    )

    st.markdown('<div class="section-title">PDF Ejecutivo del módulo</div>', unsafe_allow_html=True)
    st.download_button(
        "Descargar PDF Ejecutivo Matrícula",
        data=pdf_bytes,
        file_name=f"matricula_ejecutivo__{stamp}.pdf",
        mime="application/pdf",
        use_container_width=True,
        key=f"dl_matricula_pdf_{stamp}",
    )
    with st.expander("Ver PDF Ejecutivo en pantalla", expanded=False):
        render_pdf_preview(pdf_bytes, height=700)