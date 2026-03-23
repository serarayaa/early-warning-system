"""
SIGMA — Módulo de Notas
ui/notas_page.py
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd
import streamlit as st

from ui.executive_pdf import show_pretty_table, _safe

GOLD_NOTAS = Path("data/gold/notas")
RAW_EJES   = Path("data/raw/notas")


# ── helpers ──────────────────────────────────────────────────────────

def _load(name: str) -> pd.DataFrame:
    p = GOLD_NOTAS / name
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(p, encoding="utf-8")
    except Exception:
        return pd.DataFrame()


def _color_nota(nota: float) -> str:
    if nota < 4.0:  return "🔴"
    if nota < 4.5:  return "🟠"
    if nota < 5.5:  return "🟡"
    return "🟢"


def _badge_alerta(alerta: str) -> str:
    return {
        "REPROBADO":  "🔴 Reprobado",
        "EN_RIESGO":  "🟠 En riesgo",
        "INCOMPLETO": "🔵 Incompleto",
        "OK":         "🟢 OK",
    }.get(str(alerta).upper(), alerta)


# ══════════════════════════════════════════════════════════════════════

def render_notas_page():
    # ── CSS heredado del sistema ──────────────────────────────────────
    st.markdown("""
    <style>
    .section-title {
        font-family: 'DM Mono', monospace;
        font-size: 0.65rem;
        color: #63b3ed;
        text-transform: uppercase;
        letter-spacing: 2px;
        border-left: 3px solid #63b3ed;
        padding-left: 10px;
        margin: 18px 0 10px 0;
    }
    .record-count {
        font-family: 'DM Mono', monospace;
        font-size: 0.7rem;
        color: #4a5568;
        margin-bottom: 8px;
    }
    .record-count span { color: #63b3ed; font-weight: bold; }
    .sigma-alert {
        padding: 10px 16px;
        border-radius: 8px;
        font-size: 0.85rem;
        margin-bottom: 12px;
    }
    .sigma-alert.info  { background: #0d1e35; border-left: 3px solid #63b3ed; color: #90cdf4; }
    .sigma-alert.warn  { background: #1a1200; border-left: 3px solid #d97706; color: #fbd38d; }
    .sigma-alert.error { background: #1a0505; border-left: 3px solid #dc2626; color: #feb2b2; }
    </style>
    """, unsafe_allow_html=True)

    # Encabezado
    st.markdown("""
    <div style='margin-bottom:8px'>
      <div style='font-family:DM Mono,monospace;font-size:1.6rem;font-weight:700;
                  color:#63b3ed;letter-spacing:2px'>SIGMA</div>
      <div style='font-family:DM Mono,monospace;font-size:0.55rem;color:#4a5568;
                  letter-spacing:3px;text-transform:uppercase'>
        Módulo de Notas · 2026
      </div>
    </div>
    <hr style='border-color:#1a2035;margin:8px 0 16px 0'>
    """, unsafe_allow_html=True)

    # ── Cargar datos disponibles ──────────────────────────────────────
    df_ejes    = _load("notas_ejes.csv")
    df_alumnos = _load("notas_alumnos.csv")
    df_cursos  = _load("notas_cursos.csv")
    df_detalle = _load("notas_detalle_ejes.csv")
    df_meta    = _load("notas_meta.csv")

    ejes_ok    = not df_ejes.empty
    notas_ok   = not df_alumnos.empty

    # ── TABS ──────────────────────────────────────────────────────────
    tab_config, tab_notas, tab_cursos, tab_riesgo, tab_cargar = st.tabs([
        "⚙️ Configuración",
        "📊 Notas por alumno",
        "📐 Por curso",
        "⚠️ Riesgo académico",
        "📂 Cargar datos",
    ])

    # ══════════════════════════════════════════════════════════════════
    # TAB CONFIGURACIÓN — tabla maestra de ejes
    # ══════════════════════════════════════════════════════════════════
    with tab_config:
        st.markdown('<div class="section-title">Tabla maestra de ejes de evaluación 2026</div>',
                    unsafe_allow_html=True)

        if not ejes_ok:
            st.markdown(
                '<div class="sigma-alert warn">⚠️ No hay tabla de ejes cargada. '
                'Ve al tab <b>📂 Cargar datos</b> y sube el Excel de ejes.</div>',
                unsafe_allow_html=True)
        else:
            # KPIs
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Asignaturas", df_ejes["asignatura"].nunique())
            k2.metric("Ejes totales", len(df_ejes))
            n_esp = df_ejes[df_ejes["specialty"] != "COMUN"]["specialty"].nunique()
            k3.metric("Especialidades", n_esp)
            k4.metric("Niveles", df_ejes["level"].nunique())

            st.markdown('<div class="section-title">Filtrar tabla</div>', unsafe_allow_html=True)
            fc1, fc2, fc3 = st.columns(3)
            with fc1:
                f_nivel = st.selectbox("Nivel", ["Todos"] + sorted(df_ejes["level"].dropna().unique().astype(int).tolist()), key="cfg_nivel")
            with fc2:
                f_spec  = st.selectbox("Especialidad", ["Todas"] + sorted(df_ejes["specialty"].unique()), key="cfg_spec")
            with fc3:
                f_term  = st.selectbox("Semestre", ["Todos"] + sorted(df_ejes["term_id"].unique()), key="cfg_term")

            df_show = df_ejes.copy()
            if f_nivel != "Todos":
                df_show = df_show[df_show["level"] == int(f_nivel)]
            if f_spec != "Todas":
                df_show = df_show[df_show["specialty"] == f_spec]
            if f_term != "Todos":
                df_show = df_show[df_show["term_id"] == f_term]

            st.markdown(
                f'<div class="record-count">Mostrando <span>{len(df_show)}</span> ejes</div>',
                unsafe_allow_html=True)

            cols_show = ["level","specialty","term_id","cod_asignatura","asignatura",
                         "cod_eje","eje_evaluacion","ponderacion_eje"]
            cols_show = [c for c in cols_show if c in df_show.columns]
            df_display = df_show[cols_show].rename(columns={
                "level":"Nivel","specialty":"Especialidad","term_id":"Semestre",
                "cod_asignatura":"Cód. Asig.","asignatura":"Asignatura",
                "cod_eje":"Cód. Eje","eje_evaluacion":"Eje de Evaluación",
                "ponderacion_eje":"Pond. %"
            })
            show_pretty_table(df_display, max_rows=400, height=500)

            # Verificar ponderaciones
            problemas = []
            for (lvl, spec, asig, term), grp in df_ejes.groupby(["level","specialty","asignatura","term_id"]):
                total = grp["ponderacion_eje"].sum()
                if abs(total - 100) > 1:
                    problemas.append(f"{lvl}° {spec} | {asig} | {term}: {total:.0f}%")

            if problemas:
                st.markdown(
                    f'<div class="sigma-alert warn">⚠️ Ponderaciones != 100%: '
                    f'{" | ".join(problemas)}</div>',
                    unsafe_allow_html=True)
            else:
                st.markdown(
                    '<div class="sigma-alert info">✅ Todas las ponderaciones suman 100%</div>',
                    unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════
    # TAB NOTAS POR ALUMNO
    # ══════════════════════════════════════════════════════════════════
    with tab_notas:
        if not notas_ok:
            st.markdown(
                '<div class="sigma-alert warn">⚠️ Sin notas procesadas aún. '
                'Sube el ZIP de notas en el tab <b>📂 Cargar datos</b>.</div>',
                unsafe_allow_html=True)
        else:
            st.markdown('<div class="section-title">Notas por alumno</div>',
                        unsafe_allow_html=True)

            # Filtros
            f1, f2, f3, f4 = st.columns(4)
            cursos_uniq = sorted(df_alumnos["curso"].dropna().unique())
            asigs_uniq  = sorted(df_alumnos["asignatura"].dropna().unique()) if "asignatura" in df_alumnos.columns else []
            terms_uniq  = sorted(df_alumnos["term_id"].dropna().unique())
            alertas_uniq = ["Todas", "REPROBADO", "EN_RIESGO", "INCOMPLETO", "OK"]

            with f1:
                f_curso = st.selectbox("Curso", ["Todos"] + cursos_uniq, key="n_curso")
            with f2:
                f_asig  = st.selectbox("Asignatura", ["Todas"] + asigs_uniq, key="n_asig")
            with f3:
                f_term2 = st.selectbox("Semestre", ["Todos"] + terms_uniq, key="n_term")
            with f4:
                f_alerta = st.selectbox("Estado", alertas_uniq, key="n_alerta")

            df_n = df_alumnos.copy()
            if f_curso  != "Todos":  df_n = df_n[df_n["curso"] == f_curso]
            if f_asig   != "Todas":  df_n = df_n[df_n["asignatura"] == f_asig]
            if f_term2  != "Todos":  df_n = df_n[df_n["term_id"] == f_term2]
            if f_alerta != "Todas":  df_n = df_n[df_n["alerta"] == f_alerta]

            # KPIs dinámicos
            if not df_n.empty:
                kn1, kn2, kn3, kn4 = st.columns(4)
                prom_g = df_n["nota"].mean()
                n_rep  = int((df_n["nota"] < 4.0).sum())
                n_ries = int((df_n["alerta"] == "EN_RIESGO").sum())
                pct_ap = round((df_n["nota"] >= 4.0).mean() * 100, 1)
                kn1.metric("Promedio", f"{prom_g:.1f}")
                kn2.metric("Reprobados", n_rep)
                kn3.metric("En riesgo", n_ries)
                kn4.metric("% Aprobados", f"{pct_ap}%")

            st.markdown(
                f'<div class="record-count">Mostrando <span>{len(df_n)}</span> registros</div>',
                unsafe_allow_html=True)

            # Formatear para mostrar
            df_nd = df_n.copy()
            if "nota" in df_nd.columns:
                df_nd["Nota"] = df_nd["nota"].apply(
                    lambda v: f"{_color_nota(v)} {v:.1f}" if pd.notna(v) else "—")
            if "alerta" in df_nd.columns:
                df_nd["Estado"] = df_nd["alerta"].apply(_badge_alerta)

            col_map = {
                "nombre":"Nombre","curso":"Curso","asignatura":"Asignatura",
                "term_id":"Semestre","n_ejes_con_nota":"Ejes c/nota",
                "n_ejes_total":"Ejes total",
            }
            cols_final = ["nombre","curso","asignatura","term_id","Nota","n_ejes_con_nota","n_ejes_total","Estado"]
            cols_final = [c for c in cols_final if c in df_nd.columns]
            df_nd2 = df_nd[cols_final].rename(columns=col_map)

            show_pretty_table(df_nd2, max_rows=500, height=520)

            st.download_button(
                "📥 Descargar notas por alumno",
                data=df_n.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
                file_name="SIGMA_notas_alumnos.csv",
                mime="text/csv",
                key="dl_notas_alumnos",
            )

    # ══════════════════════════════════════════════════════════════════
    # TAB POR CURSO
    # ══════════════════════════════════════════════════════════════════
    with tab_cursos:
        if not notas_ok or df_cursos.empty:
            st.markdown(
                '<div class="sigma-alert warn">⚠️ Sin datos de cursos aún.</div>',
                unsafe_allow_html=True)
        else:
            st.markdown('<div class="section-title">Promedios por curso y asignatura</div>',
                        unsafe_allow_html=True)

            fc1, fc2 = st.columns(2)
            with fc1:
                f_curs2 = st.selectbox("Curso", ["Todos"] + sorted(df_cursos["curso"].unique()), key="c_curso")
            with fc2:
                f_term3 = st.selectbox("Semestre", ["Todos"] + sorted(df_cursos["term_id"].unique()), key="c_term")

            df_c = df_cursos.copy()
            if f_curs2 != "Todos": df_c = df_c[df_c["curso"] == f_curs2]
            if f_term3 != "Todos": df_c = df_c[df_c["term_id"] == f_term3]

            df_c["Promedio"] = df_c["prom_curso"].apply(
                lambda v: f"{_color_nota(v)} {v:.1f}" if pd.notna(v) else "—")
            df_c["Estado"] = df_c["alerta_curso"].apply(
                lambda v: {"CRITICO":"🔴 Crítico","ATENCION":"🟠 Atención","OK":"🟢 OK"}.get(str(v).upper(), v))
            df_c["% Aprobados"] = df_c["pct_aprobado"].apply(lambda v: f"{v:.1f}%" if pd.notna(v) else "—")

            cols_c = ["curso","asignatura","term_id","Promedio","n_alumnos",
                      "n_aprobados","% Aprobados","nota_max","nota_min","Estado"]
            cols_c = [c for c in cols_c if c in df_c.columns]
            df_c2 = df_c[cols_c].rename(columns={
                "curso":"Curso","asignatura":"Asignatura","term_id":"Semestre",
                "n_alumnos":"Alumnos","n_aprobados":"Aprobados",
                "nota_max":"Máx","nota_min":"Mín",
            })

            show_pretty_table(df_c2, max_rows=300, height=500)

    # ══════════════════════════════════════════════════════════════════
    # TAB RIESGO ACADÉMICO
    # ══════════════════════════════════════════════════════════════════
    with tab_riesgo:
        if not notas_ok:
            st.markdown(
                '<div class="sigma-alert warn">⚠️ Sin notas procesadas aún.</div>',
                unsafe_allow_html=True)
        else:
            st.markdown('<div class="section-title">Alumnos en riesgo académico</div>',
                        unsafe_allow_html=True)

            # KPIs globales
            total_reg  = len(df_alumnos)
            n_rep      = int((df_alumnos["alerta"] == "REPROBADO").sum())
            n_riesgo   = int((df_alumnos["alerta"] == "EN_RIESGO").sum())
            n_incomp   = int((df_alumnos["alerta"] == "INCOMPLETO").sum())

            kr1, kr2, kr3, kr4 = st.columns(4)
            kr1.metric("Total registros", total_reg)
            kr2.metric("🔴 Reprobados",   n_rep,    delta=None)
            kr3.metric("🟠 En riesgo",    n_riesgo, delta=None)
            kr4.metric("🔵 Incompletos",  n_incomp, delta=None)

            # Alumnos con más asignaturas reprobadas
            st.markdown('<div class="section-title">Alumnos con asignaturas reprobadas</div>',
                        unsafe_allow_html=True)

            df_rep = df_alumnos[df_alumnos["alerta"] == "REPROBADO"].copy()
            if df_rep.empty:
                st.markdown(
                    '<div class="sigma-alert info">✅ Sin alumnos reprobados en el corte actual.</div>',
                    unsafe_allow_html=True)
            else:
                # Agrupar por alumno — cuántas asignaturas reprobadas
                resumen_rep = (
                    df_rep.groupby(["nombre","curso"])
                    .agg(
                        asigs_reprobadas=("asignatura", lambda x: ", ".join(sorted(x))),
                        n_reprobadas    =("asignatura", "count"),
                        nota_minima     =("nota",        "min"),
                    )
                    .reset_index()
                    .sort_values("n_reprobadas", ascending=False)
                )
                resumen_rep["Nota mín"] = resumen_rep["nota_minima"].apply(lambda v: f"{v:.1f}")

                show_pretty_table(
                    resumen_rep[["nombre","curso","n_reprobadas","asigs_reprobadas","Nota mín"]].rename(columns={
                        "nombre":"Nombre","curso":"Curso",
                        "n_reprobadas":"N° Reprobadas","asigs_reprobadas":"Asignaturas"
                    }),
                    max_rows=300, height=400
                )

                st.download_button(
                    "📥 Descargar listado de riesgo",
                    data=df_rep.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
                    file_name="SIGMA_alumnos_riesgo_academico.csv",
                    mime="text/csv",
                    key="dl_riesgo",
                )

    # ══════════════════════════════════════════════════════════════════
    # TAB CARGAR DATOS
    # ══════════════════════════════════════════════════════════════════
    with tab_cargar:
        st.markdown('<div class="section-title">1. Tabla maestra de ejes de evaluación</div>',
                    unsafe_allow_html=True)

        if ejes_ok:
            st.markdown(
                f'<div class="sigma-alert info">✅ Ejes cargados: '
                f'{df_ejes["asignatura"].nunique()} asignaturas · '
                f'{len(df_ejes)} ejes totales</div>',
                unsafe_allow_html=True)

        archivo_ejes = st.file_uploader(
            "Sube el Excel de ejes (EJES_EVALUACION_2026.xlsx)",
            type=["xlsx","xls"],
            key="uploader_ejes",
        )

        if archivo_ejes is not None:
            if st.button("✅ Cargar tabla de ejes", type="primary", key="btn_ejes"):
                with st.spinner("Cargando ejes..."):
                    try:
                        import tempfile, os
                        from src.staging.build_stg_notas import load_ejes

                        RAW_EJES.mkdir(parents=True, exist_ok=True)
                        GOLD_NOTAS.mkdir(parents=True, exist_ok=True)

                        # Guardar temporalmente y cargar
                        with tempfile.NamedTemporaryFile(
                            delete=False, suffix=".xlsx"
                        ) as tmp:
                            tmp.write(archivo_ejes.getbuffer())
                            tmp_path = tmp.name

                        df_nuevos_ejes = load_ejes(tmp_path)
                        df_nuevos_ejes.to_csv(GOLD_NOTAS / "notas_ejes.csv",
                                              index=False, encoding="utf-8")
                        # Windows: esperar que openpyxl libere el archivo
                        import gc
                        gc.collect()
                        try:
                            os.unlink(tmp_path)
                        except PermissionError:
                            pass  # Windows lo eliminará al reiniciar

                        st.success(
                            f"✅ Ejes cargados: {df_nuevos_ejes['asignatura'].nunique()} "
                            f"asignaturas · {len(df_nuevos_ejes)} ejes"
                        )
                        st.cache_data.clear()
                        st.rerun()

                    except Exception as e:
                        import traceback
                        st.error(f"Error cargando ejes: {e}\n\n{traceback.format_exc()}")

        st.markdown("---")
        st.markdown('<div class="section-title">2. ZIP con notas de Syscol</div>',
                    unsafe_allow_html=True)

        st.markdown(
            '<div class="sigma-alert info">'
            '📁 El ZIP debe contener archivos con formato: '
            '<b>CURSO-CODASIG-Nper_ID.xls</b><br>'
            'Ejemplo: <code>1EMA-LENG-1per_234122.xls</code> · '
            '<code>3EMB-MAT-2per_99999.xls</code><br>'
            'Puedes subir el ZIP completo con todos los cursos y asignaturas. '
            'SIGMA deduplica automáticamente al subir semanas parciales.'
            '</div>',
            unsafe_allow_html=True)

        if not ejes_ok:
            st.markdown(
                '<div class="sigma-alert warn">⚠️ Primero debes cargar la tabla de ejes (paso 1).</div>',
                unsafe_allow_html=True)
        else:
            archivo_zip = st.file_uploader(
                "Sube el ZIP de notas Syscol",
                type=["zip"],
                key="uploader_notas_zip",
            )

            col_opts = st.columns(2)
            with col_opts[0]:
                forzar = st.checkbox("Forzar reproceso completo", value=False,
                                     help="Elimina el acumulado anterior y recalcula desde cero",
                                     key="chk_forzar_notas")

            if archivo_zip is not None:
                if st.button("📊 Procesar notas", type="primary", key="btn_procesar_notas"):
                    with st.spinner("Procesando archivos de notas..."):
                        try:
                            import tempfile, os
                            from src.staging.build_stg_notas import process_zip_notas

                            # Forzar reproceso: eliminar acumulado
                            if forzar:
                                raw_acum = GOLD_NOTAS / "_raw_ejes_acumulado.csv"
                                if raw_acum.exists():
                                    raw_acum.unlink()
                                    st.info("🗑️ Acumulado anterior eliminado")

                            # Guardar ZIP temporal
                            with tempfile.NamedTemporaryFile(
                                delete=False, suffix=".zip"
                            ) as tmp:
                                tmp.write(archivo_zip.getbuffer())
                                tmp_path = tmp.name

                            # Recargar ejes desde gold
                            df_ejes_actual = pd.read_csv(
                                GOLD_NOTAS / "notas_ejes.csv", encoding="utf-8"
                            )

                            # Invalidar módulo cacheado
                            import sys
                            if "src.staging.build_stg_notas" in sys.modules:
                                del sys.modules["src.staging.build_stg_notas"]
                            from src.staging.build_stg_notas import process_zip_notas

                            resultado = process_zip_notas(
                                zip_path  = tmp_path,
                                df_ejes   = df_ejes_actual,
                                gold_dir  = GOLD_NOTAS,
                            )
                            os.unlink(tmp_path)

                            df_a = resultado.get("alumnos", pd.DataFrame())
                            df_c = resultado.get("cursos",  pd.DataFrame())

                            if df_a.empty:
                                st.warning("⚠️ No se procesaron notas. Verifica que los nombres de archivo coincidan con los códigos del Excel de ejes.")
                            else:
                                n_alumnos  = df_a["nombre"].nunique() if "nombre" in df_a.columns else 0
                                n_asigs    = df_a["cod_asig"].nunique() if "cod_asig" in df_a.columns else 0
                                n_cursos   = df_a["curso"].nunique() if "curso" in df_a.columns else 0
                                n_rep      = int((df_a["alerta"] == "REPROBADO").sum()) if "alerta" in df_a.columns else 0
                                st.success(
                                    f"✅ Notas procesadas: "
                                    f"{n_alumnos} alumnos · "
                                    f"{n_asigs} asignaturas · "
                                    f"{n_cursos} cursos · "
                                    f"{n_rep} reprobados"
                                )
                                st.cache_data.clear()
                                st.rerun()

                        except Exception as e:
                            import traceback
                            st.error(f"Error procesando notas: {e}\n\n{traceback.format_exc()}")

        # Estado actual
        if notas_ok and not df_meta.empty:
            st.markdown("---")
            st.markdown('<div class="section-title">Estado del último procesamiento</div>',
                        unsafe_allow_html=True)
            meta = df_meta.iloc[0].to_dict()
            m1, m2, m3 = st.columns(3)
            m1.metric("Archivos procesados", int(meta.get("archivos_ok", 0)))
            m2.metric("Archivos saltados",   int(meta.get("archivos_skip", 0)))
            m3.metric("Generado",
                      str(meta.get("generado","—"))[:16].replace("T"," "))