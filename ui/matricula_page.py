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
from src.validation.schema_registry import SCHEMA_MATRICULA
from src.validation.schema_validator import validar_columnas
from ui.executive_pdf import generate_pdf_matricula, render_pdf_preview, show_pretty_table
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


def _read_csv_uploaded(uploaded_file, nrows: int | None = None) -> pd.DataFrame:
    """Lee CSV con múltiples encodings y manejo de comillas en campos."""
    import csv as _csv
    last_err: Exception | None = None
    # latin1 primero — Syscol exporta en latin-1
    for enc in ["latin1", "utf-8-sig", "utf-8", "cp1252"]:
        for quoting in [_csv.QUOTE_MINIMAL, _csv.QUOTE_ALL, _csv.QUOTE_NONE]:
            try:
                uploaded_file.seek(0)
                kwargs = dict(sep=";", nrows=nrows, encoding=enc,
                              quoting=quoting, on_bad_lines="skip")
                if quoting == _csv.QUOTE_NONE:
                    kwargs["escapechar"] = "\\"
                df = pd.read_csv(uploaded_file, **kwargs)
                if len(df.columns) >= 3:
                    return df
            except Exception as e:
                last_err = e
    raise ValueError(f"No se pudo leer CSV de matrícula: {last_err}")


def _to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def _procesar_archivo_matricula(uploaded_file, schema: dict, force: bool):
    if uploaded_file is None:
        return False, "No se recibió archivo."

    try:
        # ── Paso 1: Leer preview ──────────────────────────────────────
        st.caption(f"📄 Leyendo: {uploaded_file.name}")
        if uploaded_file.name.lower().endswith(".csv"):
            preview_df = _read_csv_uploaded(uploaded_file, nrows=5)
        else:
            preview_df = pd.read_excel(uploaded_file, nrows=5)

        st.caption(f"✓ Columnas detectadas: {list(preview_df.columns)[:6]}...")
        uploaded_file.seek(0)

        # ── Paso 2: Validar schema (no bloquear si falla columnas opcionales) ──
        resultado_validacion = validar_columnas(preview_df.columns.tolist(), schema)
        mostrar_validacion_esquema(resultado_validacion)
        uploaded_file.seek(0)

        if not resultado_validacion["es_valido"]:
            return False, "El archivo no cumple con la estructura mínima esperada. Verifica las columnas requeridas."

        # ── Paso 3: Leer completo ─────────────────────────────────────
        if uploaded_file.name.lower().endswith(".csv"):
            df_raw = _read_csv_uploaded(uploaded_file)
            ext = ".csv"
        else:
            df_raw = pd.read_excel(uploaded_file)
            ext = ".xlsx"

        st.caption(f"✓ {len(df_raw):,} filas leídas")

        # ── Paso 4: Normalizar columnas ───────────────────────────────
        df_norm, resultado_mapeo = renombrar_dataframe_a_canonico(df_raw, schema)

        renombradas = {k: v for k, v in resultado_mapeo["mapeadas"].items() if k != v}
        if renombradas:
            filas = [{"Columna original": k, "Renombrada como": v} for k, v in renombradas.items()]
            st.markdown("**Renombrado automático aplicado**")
            show_pretty_table(pd.DataFrame(filas), max_rows=50, height=220)

        # Preservar columna Dirección si el schema no la mapeó
        dir_candidates = ["Dirección", "Direccion", "direccion"]
        if "direccion" not in df_norm.columns:
            for d in dir_candidates:
                if d in df_raw.columns:
                    df_norm["direccion"] = df_raw[d].fillna("").astype(str).str.strip()
                    st.caption(f"✓ Columna '{d}' preservada como 'direccion'")
                    break

        # ── Paso 5: Guardar temp y procesar ──────────────────────────
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

            st.caption("⚙️ Ejecutando pipeline...")
            ok, msg = process_enrollment_upload(archivo_normalizado, force=force)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

        return ok, msg

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
        return False, f"Error procesando matrícula: {e}\n\nDetalle técnico:\n{tb}"


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
    # ── Header ────────────────────────────────────────────────────────
    st.markdown("""
    <div class="sigma-header">
        <div>
            <div class="sigma-logo" style="font-size:1.5rem">SIGMA</div>
            <div class="sigma-tagline">Matrícula</div>
        </div>
    </div>""", unsafe_allow_html=True)

    # ── Carga de archivo ──────────────────────────────────────────────
    with st.expander("📂 Cargar nueva matrícula desde Syscol", expanded=True):
        col_up_1, col_up_2 = st.columns([3, 1])
        with col_up_1:
            matricula_file = st.file_uploader(
                "Archivo de matrícula (.csv, .xlsx, .xls)",
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

    # ── Calcular métricas ─────────────────────────────────────────────
    row = metrics.iloc[0].to_dict() if metrics is not None and not metrics.empty else {}
    matriculados  = _safe_int(row.get("matriculados_actuales", 0))
    retirados     = _safe_int(row.get("retirados_reales", 0))
    transferencias = _safe_int(row.get("transferencias_internas", 0))
    ruts_unicos   = _safe_int(row.get("ruts_unicos", 0))

    df_curr = df_current.copy() if df_current is not None else pd.DataFrame()
    df_prev = df_prev_current.copy() if df_prev_current is not None else pd.DataFrame()

    if not df_curr.empty:
        sexo_curr   = df_curr.get("sexo", pd.Series(dtype=str)).astype(str).str.upper().str.strip()
        hombres     = int(sexo_curr.isin(["M", "MASCULINO"]).sum())
        mujeres     = int(sexo_curr.isin(["F", "FEMENINO"]).sum())
        extranjeros = int(
            (~df_curr.get("nacionalidad", pd.Series(dtype=str)).fillna("").astype(str).str.upper().str.strip().isin(
                ["CHILENA", "CHILENO", "CHILE", ""]
            )).sum()
        )
        comunas_count = int(df_curr.get("comuna", pd.Series(dtype=str)).fillna("").astype(str)
                            .str.strip().replace("", pd.NA).dropna().nunique())
        repitentes = int(df_curr["is_repeat"].sum()) if "is_repeat" in df_curr.columns else 0
    else:
        hombres = mujeres = extranjeros = comunas_count = repitentes = 0

    if not df_prev.empty:
        sexo_prev     = df_prev.get("sexo", pd.Series(dtype=str)).astype(str).str.upper().str.strip()
        hombres_prev  = int(sexo_prev.isin(["M", "MASCULINO"]).sum())
        mujeres_prev  = int(sexo_prev.isin(["F", "FEMENINO"]).sum())
        extranjeros_prev = int(
            (~df_prev.get("nacionalidad", pd.Series(dtype=str)).fillna("").astype(str).str.upper().str.strip().isin(
                ["CHILENA", "CHILENO", "CHILE", ""]
            )).sum()
        )
        comunas_prev = int(df_prev.get("comuna", pd.Series(dtype=str)).fillna("").astype(str)
                           .str.strip().replace("", pd.NA).dropna().nunique())
    else:
        hombres_prev = mujeres_prev = extranjeros_prev = comunas_prev = None

    total = matriculados or len(df_curr) or 1
    pct_h   = round(hombres / total * 100, 1) if total else 0
    pct_m   = round(mujeres / total * 100, 1) if total else 0
    pct_ext = round(extranjeros / total * 100, 1) if total else 0
    pct_rep = round(repitentes / total * 100, 1) if total else 0

    # ── TABS ──────────────────────────────────────────────────────────
    tab_dash, tab_nomina, tab_specs, tab_demo, tab_anom, tab_calidad, tab_reportes = st.tabs([
        "⚡ Dashboard", "👥 Nómina", "📐 Especialidades", "🌍 Demografía", "⚠️ Anomalías", "🔍 Calidad de datos", "📄 Reportes"
    ])

    # ════════════════════════════════════════════════════════════════
    # TAB DASHBOARD
    # ════════════════════════════════════════════════════════════════
    with tab_dash:
        st.markdown('<div class="section-title">Indicadores actualizados</div>', unsafe_allow_html=True)

        # Fila 1: KPIs principales
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            _render_kpi_card("Matriculados", f"{matriculados:,}",
                             _delta_mini(matriculados, prev_metrics, "matriculados_actuales"), "green")
        with c2:
            _render_kpi_card("Retirados", f"{retirados:,}",
                             _delta_mini(retirados, prev_metrics, "retirados_reales"), "red")
        with c3:
            _render_kpi_card("Transferencias", f"{transferencias:,}",
                             _delta_mini(transferencias, prev_metrics, "transferencias_internas"), "amber")
        with c4:
            _render_kpi_card("RUT únicos", f"{ruts_unicos:,}",
                             _delta_mini(ruts_unicos, prev_metrics, "ruts_unicos"), "cyan")

        # ── Tabla de retirados ───────────────────────────────────────────
        if not df_curr.empty and "status" in df_curr.columns:
            df_ret = df_curr[df_curr["status"] == "RETIRADO"].copy()
            if not df_ret.empty:
                st.markdown(
                    f'<div class="section-title" style="margin-top:8px">'
                    f'🔴 Alumnos retirados — {len(df_ret)} registro{"s" if len(df_ret) != 1 else ""}</div>',
                    unsafe_allow_html=True,
                )
                # Construir tabla limpia
                col_ret = {}
                if "nombre"       in df_ret.columns: col_ret["nombre"]       = "Nombre"
                if "course_code"  in df_ret.columns: col_ret["course_code"]  = "Curso"
                if "specialty"    in df_ret.columns: col_ret["specialty"]    = "Especialidad"
                if "fecha_retiro" in df_ret.columns: col_ret["fecha_retiro"] = "Fecha retiro"
                if "motivo_retiro_raw" in df_ret.columns: col_ret["motivo_retiro_raw"] = "Motivo"

                df_ret_show = df_ret[list(col_ret.keys())].rename(columns=col_ret).copy()

                # Formatear fecha
                if "Fecha retiro" in df_ret_show.columns:
                    df_ret_show["Fecha retiro"] = pd.to_datetime(
                        df_ret_show["Fecha retiro"], errors="coerce"
                    ).dt.strftime("%d/%m/%Y").fillna("—")

                show_pretty_table(df_ret_show, max_rows=50, height=min(80 + len(df_ret_show)*40, 400))

                # Descarga
                st.download_button(
                    "📥 Descargar listado de retirados",
                    data=df_ret_show.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
                    file_name=f"SIGMA_retirados__{stamp}.csv",
                    mime="text/csv",
                    key="dl_retirados_dashboard",
                )

        # Fila 2: KPIs demográficos con barras de progreso
        st.markdown("""
        <style>
        .kpi-progress { margin-top: 16px; margin-bottom: 24px; }
        .kpi-prog-row {
            display: flex; align-items: center; gap: 12px;
            padding: 10px 16px; background: #0d1220;
            border: 1px solid rgba(99,179,237,0.10);
            border-radius: 10px; margin-bottom: 8px;
        }
        .kpi-prog-icon { font-size: 1.3rem; width: 28px; text-align: center; }
        .kpi-prog-info { flex: 1; min-width: 0; }
        .kpi-prog-label {
            font-family: 'DM Mono', monospace; font-size: 0.6rem;
            color: #4a5568; text-transform: uppercase; letter-spacing: 1.5px;
        }
        .kpi-prog-nums {
            display: flex; align-items: baseline; gap: 6px; margin: 2px 0 5px 0;
        }
        .kpi-prog-val {
            font-family: 'Syne', sans-serif; font-size: 1.4rem;
            font-weight: 800; color: #e2e8f0; line-height: 1;
        }
        .kpi-prog-pct {
            font-family: 'DM Mono', monospace; font-size: 0.72rem; color: #63b3ed;
        }
        .kpi-prog-delta {
            font-family: 'DM Mono', monospace; font-size: 0.62rem; color: #4a5568;
        }
        .kpi-bar-bg {
            background: rgba(99,179,237,0.08); border-radius: 4px;
            height: 4px; overflow: hidden;
        }
        .kpi-bar-fill { height: 100%; border-radius: 4px; }
        </style>
        """, unsafe_allow_html=True)

        pg1, pg2 = st.columns(2)
        with pg1:
            delta_h = _delta_mini_vals(hombres, hombres_prev)
            delta_m = _delta_mini_vals(mujeres, mujeres_prev)
            st.markdown(f"""
            <div class="kpi-progress">
              <div class="kpi-prog-row">
                <div class="kpi-prog-icon">👨</div>
                <div class="kpi-prog-info">
                  <div class="kpi-prog-label">Hombres</div>
                  <div class="kpi-prog-nums">
                    <span class="kpi-prog-val">{hombres:,}</span>
                    <span class="kpi-prog-pct">{pct_h}%</span>
                    <span class="kpi-prog-delta">{delta_h}</span>
                  </div>
                  <div class="kpi-bar-bg"><div class="kpi-bar-fill"
                    style="width:{pct_h}%;background:linear-gradient(90deg,#2563eb,#63b3ed)"></div></div>
                </div>
              </div>
              <div class="kpi-prog-row">
                <div class="kpi-prog-icon">👩</div>
                <div class="kpi-prog-info">
                  <div class="kpi-prog-label">Mujeres</div>
                  <div class="kpi-prog-nums">
                    <span class="kpi-prog-val">{mujeres:,}</span>
                    <span class="kpi-prog-pct">{pct_m}%</span>
                    <span class="kpi-prog-delta">{delta_m}</span>
                  </div>
                  <div class="kpi-bar-bg"><div class="kpi-bar-fill"
                    style="width:{pct_m}%;background:linear-gradient(90deg,#16a34a,#68d391)"></div></div>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        with pg2:
            delta_e = _delta_mini_vals(extranjeros, extranjeros_prev)
            pct_com = round(comunas_count / 52 * 100, 1)  # ~52 comunas RM
            delta_c = _delta_mini_vals(comunas_count, comunas_prev)
            st.markdown(f"""
            <div class="kpi-progress">
              <div class="kpi-prog-row">
                <div class="kpi-prog-icon">🌍</div>
                <div class="kpi-prog-info">
                  <div class="kpi-prog-label">Extranjeros</div>
                  <div class="kpi-prog-nums">
                    <span class="kpi-prog-val">{extranjeros:,}</span>
                    <span class="kpi-prog-pct">{pct_ext}%</span>
                    <span class="kpi-prog-delta">{delta_e}</span>
                  </div>
                  <div class="kpi-bar-bg"><div class="kpi-bar-fill"
                    style="width:{min(pct_ext*3,100):.1f}%;background:linear-gradient(90deg,#7c3aed,#9f7aea)"></div></div>
                </div>
              </div>
              <div class="kpi-prog-row">
                <div class="kpi-prog-icon">📍</div>
                <div class="kpi-prog-info">
                  <div class="kpi-prog-label">Comunas representadas</div>
                  <div class="kpi-prog-nums">
                    <span class="kpi-prog-val">{comunas_count}</span>
                    <span class="kpi-prog-pct">{pct_com:.0f}% de la RM</span>
                    <span class="kpi-prog-delta">{delta_c}</span>
                  </div>
                  <div class="kpi-bar-bg"><div class="kpi-bar-fill"
                    style="width:{min(pct_com,100):.1f}%;background:linear-gradient(90deg,#d97706,#f6ad55)"></div></div>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        # Gráficos
        st.markdown('<div class="section-title">Visualizaciones</div>', unsafe_allow_html=True)
        g1, g2 = st.columns(2)

        with g1:
            # Donut género
            fig_sexo = go.Figure(data=[go.Pie(
                labels=["Hombres", "Mujeres"], values=[hombres, mujeres],
                hole=0.5,
                marker={"colors": ["#2563eb", "#16a34a"]},
                textinfo="label+percent",
                textfont={"size": 11, "color": "#e2e8f0"},
                hovertemplate="<b>%{label}</b>: %{value:,} (%{percent})<extra></extra>",
            )])
            fig_sexo.update_layout(
                paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                font={"color": "#e2e8f0"},
                height=290, margin={"l": 10, "r": 10, "t": 40, "b": 10},
                title={"text": "Distribución por género", "font": {"size": 12, "color": "#63b3ed"}, "x": 0},
                legend={"font": {"size": 10}, "bgcolor": "rgba(0,0,0,0)"},
                annotations=[{"text": f"<b>{matriculados:,}</b>", "x": 0.5, "y": 0.5,
                               "font": {"size": 16, "color": "#e2e8f0"}, "showarrow": False}],
            )
            st.plotly_chart(fig_sexo, use_container_width=True, config={"displayModeBar": False})

        with g2:
            # Barras apiladas H/M por nivel
            if not df_curr.empty and "level" in df_curr.columns:
                df_niv = df_curr.copy()
                df_niv["_nivel"] = pd.to_numeric(df_niv["level"], errors="coerce").fillna(0).astype(int)
                df_niv["_sx"] = df_niv.get("sexo", pd.Series(dtype=str)).astype(str).str.upper().str.strip()
                df_niv = df_niv[df_niv["_nivel"] > 0]
                niveles = sorted(df_niv["_nivel"].unique())
                h_vals = [int((df_niv[df_niv["_nivel"] == n]["_sx"].isin(["M", "MASCULINO"])).sum()) for n in niveles]
                m_vals = [int((df_niv[df_niv["_nivel"] == n]["_sx"].isin(["F", "FEMENINO"])).sum()) for n in niveles]
                labels = [f"{n}° Medio" for n in niveles]
                fig_niv = go.Figure()
                fig_niv.add_trace(go.Bar(
                    name="Hombres", x=labels, y=h_vals,
                    marker_color="#2563eb",
                    text=[f"{v}" for v in h_vals], textposition="inside", textfont={"size": 11},
                    hovertemplate="<b>%{x}</b> — Hombres: %{y}<extra></extra>",
                ))
                fig_niv.add_trace(go.Bar(
                    name="Mujeres", x=labels, y=m_vals,
                    marker_color="#16a34a",
                    text=[f"{v}" for v in m_vals], textposition="inside", textfont={"size": 11},
                    hovertemplate="<b>%{x}</b> — Mujeres: %{y}<extra></extra>",
                ))
                totales = [h + m for h, m in zip(h_vals, m_vals)]
                fig_niv.add_trace(go.Scatter(
                    x=labels, y=[t + max(totales) * 0.04 for t in totales],
                    text=[f"<b>{t}</b>" for t in totales], mode="text",
                    textfont={"size": 11, "color": "#e2e8f0"}, showlegend=False,
                ))
                fig_niv.update_layout(
                    barmode="stack",
                    paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                    font={"color": "#e2e8f0"}, height=290,
                    margin={"l": 10, "r": 10, "t": 40, "b": 10},
                    title={"text": "Matrícula por nivel y género", "font": {"size": 12, "color": "#63b3ed"}, "x": 0},
                    xaxis={"gridcolor": "#1a2035"}, yaxis={"gridcolor": "#1a2035"},
                    legend={"orientation": "h", "y": -0.15, "font": {"size": 10}, "bgcolor": "rgba(0,0,0,0)"},
                )
                st.plotly_chart(fig_niv, use_container_width=True, config={"displayModeBar": False})
            else:
                # Fallback: barras de especialidades
                if not (df_specs is None or df_specs.empty):
                    x_spec = df_specs.iloc[:, 0].astype(str)
                    y_spec = pd.to_numeric(df_specs.iloc[:, 1], errors="coerce").fillna(0)
                    fig_sp = go.Figure(go.Bar(
                        x=x_spec, y=y_spec, marker_color="#7c3aed",
                        hovertemplate="<b>%{x}</b>: %{y}<extra></extra>",
                    ))
                    fig_sp.update_layout(
                        paper_bgcolor="#0d1220", plot_bgcolor="#0d1220", font={"color": "#e2e8f0"},
                        height=290, margin={"l": 10, "r": 10, "t": 40, "b": 10},
                        title={"text": "Especialidades", "font": {"size": 12, "color": "#63b3ed"}, "x": 0},
                        xaxis={"gridcolor": "#1a2035"}, yaxis={"gridcolor": "#1a2035"},
                    )
                    st.plotly_chart(fig_sp, use_container_width=True, config={"displayModeBar": False})

        # Segunda fila de gráficos: comunas + repitentes
        g3, g4 = st.columns(2)
        with g3:
            if df_comunas is not None and not df_comunas.empty:
                df_com = df_comunas.copy().head(10)
                x_com = df_com.iloc[:, 0].astype(str)
                y_com = pd.to_numeric(df_com.iloc[:, 1], errors="coerce").fillna(0)
            elif not df_curr.empty and "comuna" in df_curr.columns:
                tmp = df_curr["comuna"].fillna("SIN DATOS").astype(str).str.upper().value_counts().head(10).reset_index()
                tmp.columns = ["comuna", "total"]
                x_com, y_com = tmp["comuna"], tmp["total"]
            else:
                x_com, y_com = pd.Series(dtype=str), pd.Series(dtype=float)

            if len(x_com) > 0:
                fig_com = go.Figure(go.Bar(
                    y=x_com[::-1], x=y_com[::-1],
                    orientation="h",
                    marker={"color": y_com[::-1], "colorscale": [[0, "#1a2035"], [1, "#d97706"]]},
                    text=y_com[::-1].astype(int), textposition="outside", textfont={"size": 10},
                    hovertemplate="<b>%{y}</b>: %{x}<extra></extra>",
                ))
                fig_com.update_layout(
                    paper_bgcolor="#0d1220", plot_bgcolor="#0d1220", font={"color": "#e2e8f0"},
                    height=290, margin={"l": 10, "r": 80, "t": 40, "b": 10},
                    title={"text": "Top comunas de procedencia", "font": {"size": 12, "color": "#63b3ed"}, "x": 0},
                    xaxis={"gridcolor": "#1a2035"}, yaxis={"gridcolor": "#1a2035"},
                )
                st.plotly_chart(fig_com, use_container_width=True, config={"displayModeBar": False})

        with g4:
            # Repitentes vs nuevos + extranjeros vs chilenos
            labels_pie = ["Repitentes", "Nuevos", "Extranjeros", "Chilenos"]
            n_nuevos   = max(0, matriculados - repitentes)
            n_chilenos = max(0, matriculados - extranjeros)
            fig_doble = go.Figure()
            fig_doble.add_trace(go.Pie(
                labels=["Repitentes", "No repitentes"], values=[repitentes, n_nuevos],
                hole=0.45, domain={"x": [0, 0.46]},
                marker={"colors": ["#d97706", "#1a2035"]},
                textinfo="percent", textfont={"size": 10},
                hovertemplate="<b>%{label}</b>: %{value:,}<extra></extra>",
                name="Repitentes",
            ))
            fig_doble.add_trace(go.Pie(
                labels=["Extranjeros", "Chilenos"], values=[extranjeros, n_chilenos],
                hole=0.45, domain={"x": [0.54, 1]},
                marker={"colors": ["#7c3aed", "#1a2035"]},
                textinfo="percent", textfont={"size": 10},
                hovertemplate="<b>%{label}</b>: %{value:,}<extra></extra>",
                name="Extranjeros",
            ))
            fig_doble.update_layout(
                paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                font={"color": "#e2e8f0"}, height=290,
                margin={"l": 10, "r": 10, "t": 40, "b": 30},
                title={"text": "Repitentes · Extranjeros", "font": {"size": 12, "color": "#63b3ed"}, "x": 0},
                legend={"font": {"size": 9}, "bgcolor": "rgba(0,0,0,0)", "orientation": "h", "y": -0.1},
                annotations=[
                    {"text": f"<b>{pct_rep}%</b>", "x": 0.2, "y": 0.5,
                     "font": {"size": 12, "color": "#f6ad55"}, "showarrow": False},
                    {"text": f"<b>{pct_ext}%</b>", "x": 0.8, "y": 0.5,
                     "font": {"size": 12, "color": "#9f7aea"}, "showarrow": False},
                ],
            )
            st.plotly_chart(fig_doble, use_container_width=True, config={"displayModeBar": False})

    # ════════════════════════════════════════════════════════════════
    # TAB NÓMINA
    # ════════════════════════════════════════════════════════════════
    with tab_nomina:
        st.markdown('<div class="section-title">Nómina de alumnos</div>', unsafe_allow_html=True)

        if df_curr.empty:
            st.info("Sin datos de matrícula para este corte.")
        else:
            # Filtros
            f1, f2, f3, f4 = st.columns(4)
            especialidades = ["Todas"] + sorted(df_curr["specialty"].dropna().unique().tolist()) \
                if "specialty" in df_curr.columns else ["Todas"]
            niveles_opts = ["Todos"] + [f"{n}° Medio" for n in sorted(
                pd.to_numeric(df_curr["level"], errors="coerce").dropna().astype(int).unique()
            )] if "level" in df_curr.columns else ["Todos"]
            cursos_opts = ["Todos"] + sorted(df_curr["course_code"].dropna().unique().tolist()) \
                if "course_code" in df_curr.columns else ["Todos"]
            sexo_opts = ["Todos", "Hombres", "Mujeres"]

            with f1:
                fil_esp  = st.selectbox("Especialidad", especialidades, key="nom_esp")
            with f2:
                fil_niv  = st.selectbox("Nivel", niveles_opts, key="nom_niv")
            with f3:
                fil_cur  = st.selectbox("Curso", cursos_opts, key="nom_cur")
            with f4:
                fil_sex  = st.selectbox("Género", sexo_opts, key="nom_sex")

            df_filtered = df_curr.copy()
            if fil_esp != "Todas" and "specialty" in df_filtered.columns:
                df_filtered = df_filtered[df_filtered["specialty"] == fil_esp]
            if fil_niv != "Todos" and "level" in df_filtered.columns:
                niv_num = int(fil_niv.split("°")[0])
                df_filtered = df_filtered[pd.to_numeric(df_filtered["level"], errors="coerce") == niv_num]
            if fil_cur != "Todos" and "course_code" in df_filtered.columns:
                df_filtered = df_filtered[df_filtered["course_code"] == fil_cur]
            if fil_sex != "Todos" and "sexo" in df_filtered.columns:
                sx_map = {"Hombres": ["M", "MASCULINO"], "Mujeres": ["F", "FEMENINO"]}
                df_filtered = df_filtered[
                    df_filtered["sexo"].astype(str).str.upper().str.strip().isin(sx_map[fil_sex])
                ]

            st.markdown(
                f'<div class="record-count">Mostrando <span>{len(df_filtered):,}</span> de '
                f'<span>{len(df_curr):,}</span> alumnos</div>',
                unsafe_allow_html=True,
            )

            col_display = {
                "nombre": "Nombre", "course_code": "Curso", "level": "Nivel",
                "specialty": "Especialidad", "sexo": "Género", "nacionalidad": "Nacionalidad",
                "comuna": "Comuna", "edad": "Edad", "is_repeat": "Repitente", "status": "Estado",
            }
            cols_show = [c for c in col_display if c in df_filtered.columns]
            df_show = df_filtered[cols_show].rename(columns=col_display).copy()
            if "Repitente" in df_show.columns:
                df_show["Repitente"] = df_show["Repitente"].map(
                    {True: "✓ Sí", False: "No", 1: "✓ Sí", 0: "No"}
                ).fillna("—")
            if "Nivel" in df_show.columns:
                df_show["Nivel"] = df_show["Nivel"].apply(
                    lambda v: f"{int(v)}°" if pd.notna(v) and str(v).strip() not in ("", "0") else "—"
                )
            if "Género" in df_show.columns:
                df_show["Género"] = df_show["Género"].astype(str).str.upper().str.strip().map(
                    {"M": "♂ M", "MASCULINO": "♂ M", "F": "♀ F", "FEMENINO": "♀ F"}
                ).fillna("—")

            show_pretty_table(df_show, max_rows=400, height=500)

            # ── Sección retirados ────────────────────────────────────────
            if "status" in df_curr.columns:
                df_ret_nom = df_curr[df_curr["status"] == "RETIRADO"].copy()
                if not df_ret_nom.empty:
                    st.markdown(
                        f'<div class="section-title" style="margin-top:20px;border-top:1px solid rgba(99,179,237,0.1);padding-top:16px">'
                        f'🔴 Retirados en este corte ({len(df_ret_nom)})</div>',
                        unsafe_allow_html=True,
                    )
                    col_ret = {}
                    if "nombre"       in df_ret_nom.columns: col_ret["nombre"]       = "Nombre"
                    if "course_code"  in df_ret_nom.columns: col_ret["course_code"]  = "Curso"
                    if "specialty"    in df_ret_nom.columns: col_ret["specialty"]    = "Especialidad"
                    if "fecha_retiro" in df_ret_nom.columns: col_ret["fecha_retiro"] = "Fecha retiro"
                    if "motivo_retiro_raw" in df_ret_nom.columns: col_ret["motivo_retiro_raw"] = "Motivo"

                    df_ret_nom_show = df_ret_nom[list(col_ret.keys())].rename(columns=col_ret).copy()
                    if "Fecha retiro" in df_ret_nom_show.columns:
                        df_ret_nom_show["Fecha retiro"] = pd.to_datetime(
                            df_ret_nom_show["Fecha retiro"], errors="coerce"
                        ).dt.strftime("%d/%m/%Y").fillna("—")

                    show_pretty_table(df_ret_nom_show, max_rows=50, height=min(80 + len(df_ret_nom_show)*40, 400))

    # ════════════════════════════════════════════════════════════════
    # TAB ESPECIALIDADES
    # ════════════════════════════════════════════════════════════════
    with tab_specs:
        st.markdown('<div class="section-title">Distribución por especialidad</div>', unsafe_allow_html=True)

        if not df_curr.empty and "specialty" in df_curr.columns:
            df_sp_full = (
                df_curr.assign(_sx=df_curr.get("sexo", pd.Series(dtype=str)).astype(str).str.upper().str.strip())
                .groupby("specialty", as_index=False)
                .agg(
                    Total=("rut_norm" if "rut_norm" in df_curr.columns else df_curr.columns[0], "count"),
                    Hombres=("_sx", lambda x: x.isin(["M", "MASCULINO"]).sum()),
                    Mujeres=("_sx", lambda x: x.isin(["F", "FEMENINO"]).sum()),
                )
                .sort_values("Total", ascending=False)
            )
            df_sp_full["% Total"]   = df_sp_full["Total"].apply(lambda n: f"{round(n/total*100,1)}%")
            df_sp_full["% Hombres"] = df_sp_full.apply(lambda r: f"{round(r['Hombres']/r['Total']*100,1) if r['Total'] else 0}%", axis=1)
            df_sp_full["% Mujeres"] = df_sp_full.apply(lambda r: f"{round(r['Mujeres']/r['Total']*100,1) if r['Total'] else 0}%", axis=1)
            repitentes_sp = df_curr.groupby("specialty")["is_repeat"].sum().astype(int).reset_index().rename(
                columns={"is_repeat": "Repitentes", "specialty": "specialty_r"}
            ) if "is_repeat" in df_curr.columns else None
            if repitentes_sp is not None:
                df_sp_full = df_sp_full.merge(repitentes_sp, left_on="specialty", right_on="specialty_r", how="left")
                df_sp_full["% Repitentes"] = df_sp_full.apply(
                    lambda r: f"{round(r['Repitentes']/r['Total']*100,1) if r['Total'] else 0}%", axis=1
                )
                df_sp_full = df_sp_full.drop(columns=["specialty_r"])

            df_sp_full = df_sp_full.rename(columns={"specialty": "Especialidad"})
            show_pretty_table(df_sp_full, max_rows=20, height=280)

            # Gráfico barras agrupadas por especialidad
            st.markdown('<div class="section-title" style="margin-top:20px">Detalle por curso</div>', unsafe_allow_html=True)
            if "course_code" in df_curr.columns:
                df_crs = (
                    df_curr.assign(_sx=df_curr.get("sexo", pd.Series(dtype=str)).astype(str).str.upper().str.strip())
                    .groupby(["course_code", "specialty"], as_index=False)
                    .agg(Total=("rut_norm" if "rut_norm" in df_curr.columns else df_curr.columns[0], "count"),
                         H=("_sx", lambda x: x.isin(["M","MASCULINO"]).sum()),
                         M=("_sx", lambda x: x.isin(["F","FEMENINO"]).sum()))
                    .sort_values(["specialty","course_code"])
                )
                spec_colors = {"TELECOM": "#2563eb", "ELECTRONICA": "#16a34a", "MECANICA": "#d97706"}
                fig_crs = go.Figure()
                for sp in df_crs["specialty"].unique():
                    grp = df_crs[df_crs["specialty"] == sp]
                    color = spec_colors.get(sp.upper(), "#6b7280")
                    fig_crs.add_trace(go.Bar(
                        name=sp, x=grp["course_code"], y=grp["Total"],
                        marker_color=color,
                        text=grp["Total"], textposition="outside", textfont={"size": 9},
                        hovertemplate="<b>%{x}</b> · " + sp + "<br>Total: %{y}<extra></extra>",
                    ))
                fig_crs.update_layout(
                    barmode="group",
                    paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                    font={"color": "#e2e8f0"}, height=320,
                    margin={"l": 10, "r": 10, "t": 40, "b": 10},
                    title={"text": "Matrícula por curso y especialidad", "font": {"size": 12, "color": "#63b3ed"}, "x": 0},
                    xaxis={"gridcolor": "#1a2035", "tickangle": -30},
                    yaxis={"gridcolor": "#1a2035"},
                    legend={"font": {"size": 10}, "bgcolor": "rgba(0,0,0,0)", "orientation": "h", "y": -0.2},
                )
                st.plotly_chart(fig_crs, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Sin datos de especialidades.")
            if df_specs is not None and not df_specs.empty:
                show_pretty_table(df_specs, max_rows=20, height=280)

    # ════════════════════════════════════════════════════════════════
    # TAB DEMOGRAFÍA
    # ════════════════════════════════════════════════════════════════
    with tab_demo:
        st.markdown('<div class="section-title">Demografía del establecimiento</div>', unsafe_allow_html=True)
        td1, td2 = st.columns(2)
        with td1:
            st.markdown("<div style='font-size:0.78rem;color:#63b3ed;font-weight:600;margin-bottom:8px;text-transform:uppercase;letter-spacing:2px'>🌍 Nacionalidades</div>", unsafe_allow_html=True)
            if df_nacs is not None and not df_nacs.empty:
                df_nacs_show = df_nacs.head(15).copy()
                df_nacs_show = df_nacs_show.rename(columns={
                    "nacionalidad": "Nacionalidad", "count": "Alumnos", "pct": "% del total"
                })
                if "% del total" in df_nacs_show.columns:
                    df_nacs_show["% del total"] = df_nacs_show["% del total"].apply(
                        lambda v: f"{float(v):.1f}%" if pd.notna(v) else "—"
                    )
                show_pretty_table(df_nacs_show, max_rows=15, height=360)
            else:
                st.info("Sin datos de nacionalidades.")

        with td2:
            st.markdown("<div style='font-size:0.78rem;color:#63b3ed;font-weight:600;margin-bottom:8px;text-transform:uppercase;letter-spacing:2px'>📍 Comunas (top 15)</div>", unsafe_allow_html=True)
            if df_comunas is not None and not df_comunas.empty:
                df_com_show = df_comunas.head(15).copy()
                cols_com = list(df_com_show.columns)
                rename_com = {}
                if cols_com: rename_com[cols_com[0]] = "Comuna"
                if len(cols_com) > 1: rename_com[cols_com[1]] = "Alumnos"
                if len(cols_com) > 2: rename_com[cols_com[2]] = "% del total"
                df_com_show = df_com_show.rename(columns=rename_com)
                if "% del total" in df_com_show.columns:
                    df_com_show["% del total"] = df_com_show["% del total"].apply(
                        lambda v: f"{float(v):.1f}%" if pd.notna(v) else "—"
                    )
                show_pretty_table(df_com_show, max_rows=15, height=360)
            elif not df_curr.empty and "comuna" in df_curr.columns:
                tmp = df_curr["comuna"].fillna("SIN DATOS").astype(str).str.upper().value_counts().head(15).reset_index()
                tmp.columns = ["Comuna", "Alumnos"]
                tmp["% del total"] = tmp["Alumnos"].apply(lambda n: f"{round(n/total*100,1)}%")
                show_pretty_table(tmp, max_rows=15, height=360)
            else:
                st.info("Sin datos de comunas.")

    # ════════════════════════════════════════════════════════════════
    # TAB ANOMALÍAS
    # ════════════════════════════════════════════════════════════════
    with tab_anom:
        st.markdown('<div class="section-title">Anomalías detectadas</div>', unsafe_allow_html=True)
        if not df_curr.empty:
            anom_list = []
            # RUTs duplicados
            if "rut_norm" in df_curr.columns:
                dup = df_curr[df_curr["rut_norm"].duplicated(keep=False)]
                if not dup.empty:
                    anom_list.append(("🔁 RUTs duplicados", len(dup), "amber"))
            # Edades fuera de rango
            if "edad" in df_curr.columns:
                df_edad = pd.to_numeric(df_curr["edad"], errors="coerce")
                outliers = df_curr[(df_edad < 10) | (df_edad > 25)]
                if not outliers.empty:
                    anom_list.append(("🎂 Edades fuera de rango (< 10 o > 25)", len(outliers), "red"))
            # Sin curso asignado
            if "course_code" in df_curr.columns:
                sin_curso = df_curr[df_curr["course_code"].fillna("").astype(str).str.strip() == ""]
                if not sin_curso.empty:
                    anom_list.append(("📋 Sin curso asignado", len(sin_curso), "amber"))
            # Sin especialidad
            if "specialty" in df_curr.columns:
                sin_sp = df_curr[df_curr["specialty"].fillna("").astype(str).str.strip().isin(["", "SIN DATOS"])]
                if not sin_sp.empty:
                    anom_list.append(("📐 Sin especialidad asignada", len(sin_sp), "amber"))

            if anom_list:
                color_map = {"red": "#dc2626", "amber": "#d97706", "green": "#16a34a"}
                for label, count, color in anom_list:
                    pct_anom = round(count / len(df_curr) * 100, 1)
                    st.markdown(
                        f'<div class="sigma-alert" style="border-left-color:{color_map[color]};'
                        f'background:rgba({",".join(["220,38,38" if color=="red" else "217,119,6"])},0.06)">'
                        f'<b>{label}</b> — {count:,} registros ({pct_anom}% del total)</div>',
                        unsafe_allow_html=True,
                    )
                st.markdown("<br>", unsafe_allow_html=True)
                # Tabla de edad outliers
                if "edad" in df_curr.columns:
                    df_edad = pd.to_numeric(df_curr["edad"], errors="coerce")
                    df_out = df_curr[(df_edad < 10) | (df_edad > 25)].copy()
                    if not df_out.empty:
                        st.markdown('<div class="section-title">Detalle anomalías de edad</div>', unsafe_allow_html=True)
                        cols_a = [c for c in ["nombre","course_code","specialty","edad","nacimiento","rut_norm"] if c in df_out.columns]
                        show_pretty_table(df_out[cols_a].rename(columns={
                            "nombre":"Nombre","course_code":"Curso","specialty":"Especialidad",
                            "edad":"Edad","nacimiento":"Nacimiento","rut_norm":"RUT"
                        }), max_rows=50, height=350)
            else:
                st.markdown(
                    '<div class="sigma-alert success">✅ No se detectaron anomalías en este corte de matrícula.</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("Sin datos para analizar anomalías.")

    # ════════════════════════════════════════════════════════════════
    # TAB CALIDAD DE DATOS
    # ════════════════════════════════════════════════════════════════
    with tab_calidad:
        st.markdown('<div class="section-title">Calidad de datos — campos incompletos o sospechosos</div>', unsafe_allow_html=True)

        if df_curr.empty:
            st.info("Sin datos de matrícula disponibles.")
        else:
            import re as _re

            def _q_dir(d):
                d = str(d).strip()
                if not d or d.lower() in ("nan","","-","s/d","s/i","sin dato","sin dirección"):
                    return "VACÍA"
                if len(d) < 6: return "MUY CORTA"
                if not _re.search(r"\d", d): return "SIN NÚMERO"
                return "OK"

            def _q_rut(r):
                r = str(r).strip()
                if not r or r in ("","0","nan"): return "VACÍO"
                return "OK"

            def _q_comuna(c):
                c = str(c).strip()
                if not c or c in ("","nan"): return "VACÍA"
                return "OK"

            df_q = df_curr.copy()
            df_q["_q_rut"]  = df_q["rut_norm"].apply(_q_rut)    if "rut_norm"  in df_q.columns else "OK"
            df_q["_q_com"]  = df_q["comuna"].apply(_q_comuna)   if "comuna"    in df_q.columns else "OK"
            df_q["_q_dir"]  = df_q["direccion"].apply(_q_dir)   if "direccion" in df_q.columns else "SIN COLUMNA"
            df_q["_q_edad"] = df_q["edad"].apply(
                lambda v: "VACÍA" if pd.isna(v) or str(v).strip() in ("","nan","0") else "OK"
            ) if "edad" in df_q.columns else "OK"

            # KPIs de calidad
            n_total     = len(df_q)
            n_dir_ok    = (df_q["_q_dir"] == "OK").sum()
            n_dir_mal   = n_total - n_dir_ok
            n_com_mal   = (df_q["_q_com"] != "OK").sum()
            n_rut_mal   = (df_q["_q_rut"] != "OK").sum()
            n_edad_mal  = (df_q["_q_edad"] != "OK").sum()
            tiene_dir   = "direccion" in df_q.columns

            qk1, qk2, qk3, qk4 = st.columns(4)
            def _qkpi(col, val, label, color):
                col.markdown(
                    f"""<div style="background:#0d1220;border-radius:8px;padding:12px 8px;text-align:center;
                        border:1px solid rgba(99,179,237,0.10);border-bottom:3px solid {color}">
                        <div style="font-size:1.5rem;font-weight:700;color:{color}">{val}</div>
                        <div style="font-size:0.65rem;color:#94a3b8;margin-top:2px;text-transform:uppercase">{label}</div>
                    </div>""", unsafe_allow_html=True)

            _qkpi(qk1, f"{n_dir_mal}",  "Direcciones problemáticas", "#dc2626" if n_dir_mal > 0 else "#16a34a")
            _qkpi(qk2, f"{n_com_mal}",  "Sin comuna",                "#d97706" if n_com_mal > 0 else "#16a34a")
            _qkpi(qk3, f"{n_rut_mal}",  "RUT inválidos",             "#dc2626" if n_rut_mal > 0 else "#16a34a")
            _qkpi(qk4, f"{n_edad_mal}",  "Sin edad registrada",       "#d97706" if n_edad_mal > 0 else "#16a34a")
            st.markdown("<br>", unsafe_allow_html=True)

            # Filtro de tipo de problema
            problemas_opts = ["Todos los problemas"]
            if n_dir_mal  > 0: problemas_opts.append("Dirección problemática")
            if n_com_mal  > 0: problemas_opts.append("Sin comuna")
            if n_rut_mal  > 0: problemas_opts.append("RUT inválido")
            if n_edad_mal > 0: problemas_opts.append("Sin edad")
            fil_prob = st.selectbox("Filtrar por tipo de problema", problemas_opts, key="cal_fil_prob")

            # Construir máscara
            mask = (
                (df_q["_q_dir"] != "OK") |
                (df_q["_q_com"] != "OK") |
                (df_q["_q_rut"] != "OK") |
                (df_q["_q_edad"] != "OK")
            )
            if fil_prob == "Dirección problemática": mask = df_q["_q_dir"] != "OK"
            elif fil_prob == "Sin comuna":           mask = df_q["_q_com"] != "OK"
            elif fil_prob == "RUT inválido":         mask = df_q["_q_rut"] != "OK"
            elif fil_prob == "Sin edad":             mask = df_q["_q_edad"] != "OK"

            df_problemas = df_q[mask].copy()

            # Columna de problemas detectados
            df_problemas["Problemas"] = df_problemas.apply(lambda r: " · ".join(filter(None, [
                f"Dirección {r['_q_dir']}" if r["_q_dir"] != "OK" else "",
                f"Comuna {r['_q_com']}"   if r["_q_com"] != "OK" else "",
                f"RUT {r['_q_rut']}"      if r["_q_rut"] != "OK" else "",
                f"Edad {r['_q_edad']}"    if r["_q_edad"] != "OK" else "",
            ])), axis=1)

            if df_problemas.empty:
                st.markdown(
                    '<div class="sigma-alert success">✅ No se detectaron problemas de calidad en este corte.</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="sigma-alert"><b>{len(df_problemas)} alumnos</b> con datos incompletos o sospechosos.</div>',
                    unsafe_allow_html=True,
                )
                # Tabla
                show_cols_q = [c for c in ["nombre","course_code","rut_norm","comuna",
                                            "direccion","edad","Problemas"] if c in df_problemas.columns]
                df_show_q = df_problemas[show_cols_q].rename(columns={
                    "nombre":"Nombre","course_code":"Curso","rut_norm":"RUT",
                    "comuna":"Comuna","direccion":"Dirección","edad":"Edad",
                }).reset_index(drop=True)
                show_pretty_table(df_show_q, max_rows=100, height=420)

                # Descarga
                st.download_button(
                    "📥 Descargar listado para contacto",
                    data=_to_csv_bytes(df_show_q),
                    file_name=f"SIGMA_datos_faltantes__{stamp}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="dl_calidad_faltantes",
                )

                if not tiene_dir:
                    st.markdown(
                        '<div class="sigma-alert info">'
                        '💡 El CSV actual no incluye columna <b>Dirección</b>. '
                        'Solicita a Syscol exportarla para activar el análisis geográfico completo.'
                        '</div>',
                        unsafe_allow_html=True,
                    )

    # ════════════════════════════════════════════════════════════════
    # TAB REPORTES
    # ════════════════════════════════════════════════════════════════
    with tab_reportes:
        st.markdown('<div class="section-title">Reportes y DATA entregable</div>', unsafe_allow_html=True)

        row_m = metrics.iloc[0] if metrics is not None and not metrics.empty else {}
        resumen = pd.DataFrame([{
            "Corte": stamp,
            "Matriculados": int(row_m.get("matriculados_actuales", 0) or 0),
            "Retirados":    int(row_m.get("retirados_reales", 0) or 0),
            "Transferencias": int(row_m.get("transferencias_internas", 0) or 0),
            "RUTs únicos":  int(row_m.get("ruts_unicos", 0) or 0),
        }])
        show_pretty_table(resumen, max_rows=5, height=110)

        d1, d2, d3, d4 = st.columns(4)
        d1.download_button("📥 Resumen",
            data=_to_csv_bytes(resumen), file_name=f"matricula_resumen__{stamp}.csv",
            mime=MIME_CSV, use_container_width=True, key=f"dl_matricula_resumen_{stamp}")
        d2.download_button("📥 Matrícula actual",
            data=_to_csv_bytes(df_current if df_current is not None else pd.DataFrame()),
            file_name=f"enrollment_current__{stamp}.csv",
            mime=MIME_CSV, use_container_width=True, key=f"dl_matricula_current_{stamp}")
        d3.download_button("📥 Especialidades",
            data=_to_csv_bytes(df_specs if df_specs is not None else pd.DataFrame()),
            file_name=f"enrollment_specialty__{stamp}.csv",
            mime=MIME_CSV, use_container_width=True, key=f"dl_matricula_specs_{stamp}")
        d4.download_button("📥 Demografía",
            data=_to_csv_bytes(df_demo if df_demo is not None else pd.DataFrame()),
            file_name=f"enrollment_demographics__{stamp}.csv",
            mime=MIME_CSV, use_container_width=True, key=f"dl_matricula_demo_{stamp}")

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="section-title">PDF Ejecutivo</div>', unsafe_allow_html=True)

        if st.button("📄 Generar PDF Ejecutivo Matrícula", use_container_width=True, key=f"btn_pdf_matricula_{stamp}"):
            with st.spinner("Generando PDF ejecutivo..."):
                pdf_bytes = generate_pdf_matricula(
                    stamp=str(stamp), metrics=metrics, df_current=df_current,
                    df_specs=df_specs, df_comunas=df_comunas, df_nacs=df_nacs,
                    prev_metrics=prev_metrics,
                )
            st.session_state[f"pdf_matricula_{stamp}"] = pdf_bytes

        if f"pdf_matricula_{stamp}" in st.session_state:
            pdf_bytes = st.session_state[f"pdf_matricula_{stamp}"]
            st.download_button("⬇️ Descargar PDF Ejecutivo Matrícula",
                data=pdf_bytes, file_name=f"SIGMA_Matricula_{stamp}.pdf",
                mime="application/pdf", use_container_width=True,
                key=f"dl_matricula_pdf_{stamp}")
            with st.expander("👁️ Ver PDF en pantalla", expanded=False):
                render_pdf_preview(pdf_bytes, height=700)