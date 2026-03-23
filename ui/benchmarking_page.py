"""
SIGMA — Módulo Benchmarking MINEDUC
ui/benchmarking_page.py

Compara el rendimiento del liceo vs promedios comunales y nacionales
usando datos del MINEDUC (Resumen de Rendimiento por UE).
"""
from __future__ import annotations
from pathlib import Path
import zipfile, tempfile
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from ui.executive_pdf import show_pretty_table

GOLD_MINEDUC = Path("data/gold/mineduc")
RBD_LICEO    = 24482
NOMBRE_LICEO = "Liceo Politécnico Andes"
COMUNA_LICEO = "RENCA"

C_LICEO   = "#f6ad55"   # ámbar — nuestro liceo
C_COMUNAL = "#7c3aed"   # púrpura — promedio comunal
C_NAC     = "#6b7280"   # gris — promedio nacional
C_GREEN   = "#16a34a"
C_RED     = "#dc2626"
C_BLUE    = "#2563eb"


def _kpi(col, val, label, color="#2563eb", sub=""):
    col.markdown(f"""
    <div style="background:#0d1220;border-radius:8px;padding:14px 8px;text-align:center;
        border:1px solid rgba(99,179,237,0.10);border-bottom:3px solid {color}">
        <div style="font-size:1.6rem;font-weight:800;color:{color}">{val}</div>
        <div style="font-size:0.62rem;color:#94a3b8;margin-top:3px;text-transform:uppercase">{label}</div>
        {f'<div style="font-size:0.6rem;color:#4a5568">{sub}</div>' if sub else ''}
    </div>""", unsafe_allow_html=True)


def _load(name):
    p = GOLD_MINEDUC / name
    if not p.exists():
        return None
    try:
        return pd.read_csv(p, encoding='utf-8-sig')
    except Exception:
        return None


def _prom(df, col):
    if df is None or col not in df.columns:
        return None
    return round(pd.to_numeric(df[col], errors='coerce').mean(), 1)


def render_benchmarking_page():
    st.markdown("""
    <div class="sigma-header">
        <div>
            <div class="sigma-logo" style="font-size:1.5rem">SIGMA</div>
            <div class="sigma-tagline">Benchmarking MINEDUC · Rendimiento comparado</div>
        </div>
    </div>""", unsafe_allow_html=True)

    df_nuestro  = _load("mineduc_nuestro_liceo.csv")
    df_comunal  = _load("mineduc_comunal_renca.csv")
    df_nac_tp   = _load("mineduc_nacional_tp.csv")

    if df_nuestro is None:
        st.markdown("""
        <div class="sigma-alert info">
            <b>Sin datos MINEDUC cargados.</b><br>
            Sube el ZIP del MINEDUC en el tab "📂 Cargar datos" para activar el benchmarking.
        </div>""", unsafe_allow_html=True)
        _render_uploader()
        return

    tab_bench, tab_niveles, tab_ranking, tab_cargar = st.tabs([
        "📊 Benchmarking",
        "📐 Por nivel",
        "🏆 Ranking nacional",
        "📂 Cargar datos",
    ])

    # ════════════════════════════════════
    # TAB BENCHMARKING
    # ════════════════════════════════════
    with tab_bench:
        st.markdown('<div class="section-title">Nuestro liceo vs comunal vs nacional</div>',
                    unsafe_allow_html=True)

        # Calcular métricas para Media TP (510) que es lo principal
        df_tp = df_nuestro[df_nuestro['COD_ENSE'] == 510] if df_nuestro is not None else pd.DataFrame()
        df_hc = df_nuestro[df_nuestro['COD_ENSE'] == 310] if df_nuestro is not None else pd.DataFrame()

        # Media TP
        if not df_tp.empty:
            pct_apr_tp  = round(float(df_tp['pct_aprobacion'].iloc[0]), 1)
            prom_asis_tp = round(float(df_tp['prom_asistencia'].iloc[0]), 1)
            tot_tp = int(df_tp['tot_alumnos'].iloc[0])
            rep_tp = int(df_tp['rep_total'].iloc[0])
        else:
            pct_apr_tp = prom_asis_tp = tot_tp = rep_tp = 0

        # Promedios comparativos
        df_com_tp = df_comunal[df_comunal['COD_ENSE'] == 510] if df_comunal is not None else pd.DataFrame()
        df_nac_510 = df_nac_tp[df_nac_tp['COD_ENSE'] == 510] if df_nac_tp is not None else pd.DataFrame()

        pct_apr_com = _prom(df_com_tp, 'pct_aprobacion') or 0
        pct_apr_nac = _prom(df_nac_510, 'pct_aprobacion') or 0
        prom_asis_com = _prom(df_com_tp, 'prom_asistencia') or 0
        prom_asis_nac = _prom(df_nac_510, 'prom_asistencia') or 0

        # Ranking
        if df_nac_510 is not None and not df_nac_510.empty:
            df_rank = df_nac_510[df_nac_510['tot_alumnos'] >= 100].copy()
            df_rank = df_rank.sort_values('pct_aprobacion', ascending=False).reset_index(drop=True)
            df_rank['ranking'] = df_rank.index + 1
            nuestro_pos = df_rank[df_rank['RBD'] == RBD_LICEO]
            ranking = int(nuestro_pos['ranking'].iloc[0]) if not nuestro_pos.empty else None
            total_estab = len(df_rank)
        else:
            ranking = total_estab = None

        # KPIs
        k1,k2,k3,k4,k5 = st.columns(5)
        _kpi(k1, f"{pct_apr_tp}%", "% Aprobación (TP)",
             C_GREEN if pct_apr_tp >= pct_apr_nac else C_RED,
             f"{'↑' if pct_apr_tp >= pct_apr_nac else '↓'} vs nacional {pct_apr_nac}%")
        _kpi(k2, f"{pct_apr_com}%", "Promedio comunal", C_COMUNAL)
        _kpi(k3, f"{pct_apr_nac}%", "Promedio nacional TP", C_NAC)
        _kpi(k4, f"{prom_asis_tp}%", "Asistencia prom. (aprobados)",
             C_GREEN if prom_asis_tp >= prom_asis_nac else C_RED)
        _kpi(k5, f"#{ranking}" if ranking else "—", "Ranking nacional",
             C_LICEO, f"de {total_estab} liceos TP" if total_estab else "")
        st.markdown("<br>", unsafe_allow_html=True)

        # Gráfico comparativo de barras agrupadas
        g1, g2 = st.columns(2)

        with g1:
            categorias = ["% Aprobación", "% Asistencia promedio"]
            vals_liceo  = [pct_apr_tp, prom_asis_tp]
            vals_com    = [pct_apr_com, prom_asis_com]
            vals_nac    = [pct_apr_nac, prom_asis_nac]

            fig_comp = go.Figure()
            fig_comp.add_trace(go.Bar(
                name=NOMBRE_LICEO, x=categorias, y=vals_liceo,
                marker_color=C_LICEO,
                text=[f"{v}%" for v in vals_liceo],
                textposition="outside", textfont={"size":11,"color":"#e2e8f0"},
            ))
            fig_comp.add_trace(go.Bar(
                name=f"Promedio {COMUNA_LICEO}", x=categorias, y=vals_com,
                marker_color=C_COMUNAL,
                text=[f"{v}%" for v in vals_com],
                textposition="outside", textfont={"size":10,"color":"#e2e8f0"},
            ))
            fig_comp.add_trace(go.Bar(
                name="Promedio Nacional TP", x=categorias, y=vals_nac,
                marker_color=C_NAC,
                text=[f"{v}%" for v in vals_nac],
                textposition="outside", textfont={"size":10,"color":"#e2e8f0"},
            ))
            fig_comp.update_layout(
                barmode="group",
                paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                font={"color":"#e2e8f0"}, height=320,
                margin={"l":10,"r":10,"t":10,"b":10},
                yaxis={"gridcolor":"#1a2035","range":[80,102]},
                xaxis={"gridcolor":"rgba(0,0,0,0)"},
                legend={"font":{"size":10},"bgcolor":"rgba(0,0,0,0)","orientation":"h","y":-0.15},
            )
            st.plotly_chart(fig_comp, use_container_width=True, config={"displayModeBar":False})

        with g2:
            # HC vs TP del propio liceo
            if not df_hc.empty and not df_tp.empty:
                pct_apr_hc   = round(float(df_hc['pct_aprobacion'].iloc[0]), 1)
                prom_asis_hc = round(float(df_hc['prom_asistencia'].iloc[0]), 1)
                rep_hc = int(df_hc['rep_total'].iloc[0])
                tot_hc = int(df_hc['tot_alumnos'].iloc[0])

                fig_interno = go.Figure()
                for tipo, pct_apr, prom_a, tot, rep, color in [
                    ("Media HC", pct_apr_hc, prom_asis_hc, tot_hc, rep_hc, C_BLUE),
                    ("Media TP", pct_apr_tp, prom_asis_tp, tot_tp, rep_tp, C_LICEO),
                ]:
                    fig_interno.add_trace(go.Bar(
                        name=tipo,
                        x=["% Aprobación","% Asistencia","% Reprobación"],
                        y=[pct_apr, prom_a, round(rep/tot*100,1) if tot else 0],
                        marker_color=color,
                        text=[f"{pct_apr}%", f"{prom_a}%", f"{round(rep/tot*100,1) if tot else 0}%"],
                        textposition="outside", textfont={"size":10,"color":"#e2e8f0"},
                    ))
                fig_interno.update_layout(
                    barmode="group",
                    paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                    font={"color":"#e2e8f0"}, height=320,
                    margin={"l":10,"r":10,"t":40,"b":10},
                    title={"text":"HC vs TP — nuestro liceo","font":{"size":12,"color":"#63b3ed"},"x":0},
                    yaxis={"gridcolor":"#1a2035"},
                    xaxis={"gridcolor":"rgba(0,0,0,0)"},
                    legend={"font":{"size":10},"bgcolor":"rgba(0,0,0,0)","orientation":"h","y":-0.15},
                )
                st.plotly_chart(fig_interno, use_container_width=True, config={"displayModeBar":False})

        # Insight automático
        diff_nac = round(pct_apr_tp - pct_apr_nac, 1)
        diff_com = round(pct_apr_tp - pct_apr_com, 1)
        color_insight = C_GREEN if diff_nac >= 0 else C_RED
        st.markdown(
            f'<div class="sigma-alert" style="border-left-color:{color_insight}">'
            f'En aprobación Media TP, el liceo está <b>{"+" if diff_nac >= 0 else ""}{diff_nac}pp '
            f'{"sobre" if diff_nac >= 0 else "bajo"} el promedio nacional</b> '
            f'y <b>{"+" if diff_com >= 0 else ""}{diff_com}pp '
            f'{"sobre" if diff_com >= 0 else "bajo"} el promedio comunal de {COMUNA_LICEO}</b>.'
            f'{f" Posición #{ranking} de {total_estab} liceos TP a nivel nacional." if ranking else ""}'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ════════════════════════════════════
    # TAB POR NIVEL
    # ════════════════════════════════════
    with tab_niveles:
        st.markdown('<div class="section-title">Rendimiento por nivel — 1° a 4° Medio</div>',
                    unsafe_allow_html=True)

        if df_nuestro is not None:
            niveles = {"01":"1° Medio","02":"2° Medio","03":"3° Medio","04":"4° Medio"}
            rows = []
            for cod, label in niveles.items():
                col_apr = f'apr_{cod}'
                col_rep = f'rep_{cod}'
                if col_apr not in df_nuestro.columns:
                    continue
                apr = df_nuestro[col_apr].fillna(0).sum()
                rep = df_nuestro[col_rep].fillna(0).sum() if col_rep in df_nuestro.columns else 0
                total = apr + rep
                if total > 0:
                    rows.append({
                        "Nivel": label,
                        "Aprobados": int(apr),
                        "Reprobados": int(rep),
                        "Total": int(total),
                        "% Aprobación": f"{round(apr/total*100,1)}%",
                        "% Reprobación": f"{round(rep/total*100,1)}%",
                    })

            if rows:
                df_niv = pd.DataFrame(rows)

                n1, n2 = st.columns(2)
                with n1:
                    show_pretty_table(df_niv, max_rows=10, height=220)

                with n2:
                    pct_apr_vals = [float(r["% Aprobación"].replace("%","")) for r in rows]
                    pct_rep_vals = [float(r["% Reprobación"].replace("%","")) for r in rows]
                    labels = [r["Nivel"] for r in rows]

                    fig_niv = go.Figure()
                    fig_niv.add_trace(go.Bar(
                        name="% Aprobación", x=labels, y=pct_apr_vals,
                        marker_color=C_GREEN,
                        text=[f"{v}%" for v in pct_apr_vals],
                        textposition="inside", textfont={"size":11,"color":"#fff"},
                    ))
                    fig_niv.add_trace(go.Bar(
                        name="% Reprobación", x=labels, y=pct_rep_vals,
                        marker_color=C_RED,
                        text=[f"{v}%" for v in pct_rep_vals],
                        textposition="inside", textfont={"size":10,"color":"#fff"},
                    ))
                    fig_niv.update_layout(
                        barmode="stack",
                        paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                        font={"color":"#e2e8f0"}, height=280,
                        margin={"l":10,"r":10,"t":10,"b":10},
                        yaxis={"gridcolor":"#1a2035","range":[0,102]},
                        xaxis={"gridcolor":"rgba(0,0,0,0)"},
                        legend={"font":{"size":10},"bgcolor":"rgba(0,0,0,0)","orientation":"h","y":-0.15},
                    )
                    st.plotly_chart(fig_niv, use_container_width=True, config={"displayModeBar":False})

    # ════════════════════════════════════
    # TAB RANKING
    # ════════════════════════════════════
    with tab_ranking:
        st.markdown('<div class="section-title">Posición en el contexto nacional</div>',
                    unsafe_allow_html=True)

        if df_nac_tp is not None and not df_nac_tp.empty:
            df_rank = df_nac_tp[
                (df_nac_tp['COD_ENSE'] == 510) &
                (df_nac_tp['tot_alumnos'] >= 100)
            ].copy()
            df_rank['pct_aprobacion'] = pd.to_numeric(df_rank['pct_aprobacion'], errors='coerce')
            df_rank['prom_asistencia'] = pd.to_numeric(df_rank['prom_asistencia'], errors='coerce')
            df_rank = df_rank.sort_values('pct_aprobacion', ascending=False).reset_index(drop=True)
            df_rank['Ranking'] = df_rank.index + 1
            df_rank['Es_nuestro'] = df_rank['RBD'] == RBD_LICEO

            # Highlight nuestro liceo
            nuestro_row = df_rank[df_rank['RBD'] == RBD_LICEO]
            ranking = int(nuestro_row['Ranking'].iloc[0]) if not nuestro_row.empty else None

            if ranking:
                percentil = round((1 - ranking/len(df_rank))*100, 1)
                k1,k2,k3 = st.columns(3)
                _kpi(k1, f"#{ranking}", "Posición nacional", C_LICEO,
                     f"de {len(df_rank)} liceos TP")
                _kpi(k2, f"Top {100-percentil:.0f}%", "Percentil", C_GREEN)
                _kpi(k3, f"{pct_apr_tp}%", "% Aprobación", C_LICEO,
                     f"vs {pct_apr_nac}% nacional")
                st.markdown("<br>", unsafe_allow_html=True)

            # Top 20 + nuestro liceo
            top20 = df_rank.head(20)
            if ranking and ranking > 20:
                top20 = pd.concat([top20, nuestro_row])

            df_show = top20[['Ranking','NOM_RBD','NOM_COM_RBD','pct_aprobacion','prom_asistencia','tot_alumnos']].rename(columns={
                'NOM_RBD':'Establecimiento','NOM_COM_RBD':'Comuna',
                'pct_aprobacion':'% Aprobación','prom_asistencia':'Asist. prom.',
                'tot_alumnos':'Alumnos'
            }).copy()
            df_show['% Aprobación'] = df_show['% Aprobación'].apply(lambda v: f"{v:.1f}%")
            df_show['Asist. prom.'] = df_show['Asist. prom.'].apply(lambda v: f"{v:.1f}%")
            df_show['Alumnos'] = df_show['Alumnos'].astype(int)

            st.markdown(f'<div class="sigma-alert info">Mostrando top 20{"  +  posición del liceo" if ranking and ranking > 20 else ""}. El liceo figura en <b>#{ranking}</b>.</div>',
                        unsafe_allow_html=True)
            show_pretty_table(df_show, max_rows=25, height=500)

    # ════════════════════════════════════
    # TAB CARGAR
    # ════════════════════════════════════
    with tab_cargar:
        _render_uploader()


def _render_uploader():
    st.markdown('<div class="section-title">Cargar archivo MINEDUC</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="sigma-alert info">
        Sube el archivo ZIP del MINEDUC <b>Resumen de Rendimiento por Unidad Educativa</b>.
        Disponible en <a href="https://datosabiertos.mineduc.cl" target="_blank" style="color:#63b3ed">datosabiertos.mineduc.cl</a>.<br>
        Se procesarán automáticamente todos los años incluidos en el ZIP.
    </div>""", unsafe_allow_html=True)

    uploaded = st.file_uploader("ZIP del MINEDUC", type=["zip","csv"], key="mineduc_uploader")

    if uploaded is not None:
        with st.spinner("Procesando datos MINEDUC..."):
            try:
                GOLD_MINEDUC.mkdir(parents=True, exist_ok=True)

                if uploaded.name.endswith('.zip'):
                    with tempfile.TemporaryDirectory() as tmpdir:
                        zip_path = Path(tmpdir) / "mineduc.zip"
                        zip_path.write_bytes(uploaded.read())
                        with zipfile.ZipFile(zip_path) as zf:
                            zf.extractall(tmpdir)
                        csvs = list(Path(tmpdir).rglob("*.csv"))
                        if not csvs:
                            st.error("No se encontraron CSV dentro del ZIP")
                        else:
                            df = _procesar_csv_mineduc(csvs[0])
                            _guardar_mineduc(df)
                            st.success(f"✅ {len(df):,} registros procesados")
                            st.cache_data.clear()
                            st.rerun()
                else:
                    # CSV directo
                    import io
                    df = _procesar_csv_mineduc(io.BytesIO(uploaded.read()))
                    _guardar_mineduc(df)
                    st.success(f"✅ {len(df):,} registros procesados")
                    st.cache_data.clear()
                    st.rerun()
            except Exception as e:
                import traceback
                st.error(f"Error: {e}\n{traceback.format_exc()}")


def _procesar_csv_mineduc(path_or_buf):
    for enc in ['utf-8-sig','latin-1','utf-8','cp1252']:
        try:
            df = pd.read_csv(path_or_buf, sep=';', encoding=enc)
            df.columns = [c.strip() for c in df.columns]
            if 'RBD' in df.columns:
                break
        except Exception:
            try:
                path_or_buf.seek(0)
            except Exception:
                pass
    for c in df.columns:
        if any(x in c for x in ['APR','REP','SI_','TRA','RET','PROM']):
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(',','.'), errors='coerce')
    df['apr_total'] = df['APR_HOM_TO'].fillna(0) + df['APR_MUJ_TO'].fillna(0)
    df['rep_total'] = df['REP_HOM_TO'].fillna(0) + df['REP_MUJ_TO'].fillna(0)
    df['tot_alumnos'] = df['apr_total'] + df['rep_total']
    df['pct_aprobacion'] = (df['apr_total'] / df['tot_alumnos'].replace(0, float('nan')) * 100).round(1)
    df['prom_asistencia'] = pd.to_numeric(df.get('PROM_ASIS', pd.Series()).astype(str).str.replace(',','.'), errors='coerce').round(1)
    for nivel in ['01','02','03','04']:
        for t in ['APR','REP']:
            h,m = f'{t}_HOM_{nivel}', f'{t}_MUJ_{nivel}'
            df[f'{t.lower()}_{nivel}'] = df.get(h, 0).fillna(0) + df.get(m, 0).fillna(0)
    return df


def _guardar_mineduc(df):
    df[df['RBD'] == RBD_LICEO].to_csv(GOLD_MINEDUC / 'mineduc_nuestro_liceo.csv', index=False, encoding='utf-8-sig')
    if 'NOM_COM_RBD' in df.columns:
        df[df['NOM_COM_RBD'].str.upper() == COMUNA_LICEO].to_csv(GOLD_MINEDUC / 'mineduc_comunal_renca.csv', index=False, encoding='utf-8-sig')
    if 'COD_ENSE' in df.columns:
        df[df['COD_ENSE'] == 510].to_csv(GOLD_MINEDUC / 'mineduc_nacional_tp.csv', index=False, encoding='utf-8-sig')
    df.to_csv(GOLD_MINEDUC / 'mineduc_todos.csv', index=False, encoding='utf-8-sig')