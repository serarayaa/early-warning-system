"""
SIGMA — Módulo Geolocalización
ui/geo_page.py

Mapa de procedencia de alumnos cruzado con atrasos.
Fase 1: coordenadas por centroide de comuna (sin API externa).
Fase 2 (futura): geocodificación por dirección exacta + rutas Red.
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui.executive_pdf import show_pretty_table
from pathlib import Path
import glob as _glob

# ── Coordenadas centroide por comuna (Gran Santiago + alrededores) ────
COORD_COMUNAS: dict[str, tuple[float, float]] = {
    "BUIN":              (-33.7312, -70.7456),
    "CERRILLOS":         (-33.4934, -70.7123),
    "CERRO NAVIA":       (-33.4282, -70.7398),
    "COLINA":            (-33.2023, -70.6734),
    "CONCHALÍ":          (-33.3836, -70.6731),
    "ESTACIÓN CENTRAL":  (-33.4512, -70.6834),
    "HUECHURABA":        (-33.3634, -70.6512),
    "INDEPENDENCIA":     (-33.4162, -70.6583),
    "LA FLORIDA":        (-33.5234, -70.5983),
    "LAMPA":             (-33.2881, -70.8812),
    "LO ESPEJO":         (-33.5198, -70.6923),
    "LO PRADO":          (-33.4534, -70.7234),
    "MAIPÚ":             (-33.5123, -70.7634),
    "PADRE HURTADO":     (-33.5612, -70.8234),
    "PEÑALOLÉN":         (-33.4834, -70.5412),
    "PROVIDENCIA":       (-33.4323, -70.6134),
    "PUDAHUEL":          (-33.4456, -70.7612),
    "PUENTE ALTO":       (-33.6123, -70.5756),
    "QUILICURA":         (-33.3589, -70.7281),
    "QUINTA NORMAL":     (-33.4342, -70.7001),
    "RECOLETA":          (-33.3978, -70.6428),
    "RENCA":             (-33.4024, -70.7215),  # centroide zona sur-poniente
    "SANTIAGO":          (-33.4569, -70.6483),
    "TILTIL":            (-33.0934, -70.9234),
}

# Ubicación del liceo — Av. Domingo Santa María 3640, Renca
LICEO_LAT  = -33.4024
LICEO_LNG  = -70.7215
LICEO_NAME = "Liceo (Av. Domingo Santa María 3640)"


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distancia en km entre dos coordenadas (línea recta)."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def _tiempo_estimado(km: float) -> str:
    """Estimación muy conservadora de tiempo en transporte público."""
    if km < 1:   return "< 10 min"
    if km < 3:   return f"~{int(km * 8)} min"   # velocidad media 7-8 km/h caminando
    if km < 10:  return f"~{int(km * 4)} min"   # bus ~15 km/h promedio con paradas
    if km < 20:  return f"~{int(km * 3.5)} min" # combinación bus+metro
    return f"~{int(km * 3)} min"                 # viajes largos


def _build_geo_df(
    df_matricula: pd.DataFrame,
    df_atrasos_alumnos: pd.DataFrame | None = None,
    df_geocoded: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Construye DataFrame con coordenadas por alumno.
    Prioridad: coordenadas exactas de geocodificación > centroide de comuna.
    """
    df = df_matricula.copy()
    df["comuna_up"] = df["comuna"].fillna("").astype(str).str.strip().str.upper()

    # Coordenadas exactas si están disponibles
    if df_geocoded is not None and not df_geocoded.empty and "geo_lat" in df_geocoded.columns:
        key = "rut_norm" if "rut_norm" in df.columns and "rut_norm" in df_geocoded.columns else None
        if key:
            df = df.merge(
                df_geocoded[[key,"geo_lat","geo_lng","geo_source","geo_dist_km"]].drop_duplicates(key),
                on=key, how="left"
            )
        df["lat"]      = df.get("geo_lat", pd.Series([None]*len(df)))
        df["lng"]      = df.get("geo_lng", pd.Series([None]*len(df)))
        df["geo_mode"] = df.get("geo_source", "centroide_comuna")
        df["dist_km"]  = df.get("geo_dist_km", pd.Series([None]*len(df)))
    else:
        df["lat"]      = df["comuna_up"].map(lambda c: COORD_COMUNAS.get(c, (None, None))[0])
        df["lng"]      = df["comuna_up"].map(lambda c: COORD_COMUNAS.get(c, (None, None))[1])
        df["geo_mode"] = "centroide_comuna"
        df["dist_km"]  = None

    # Calcular distancia donde falte
    mask_sin_dist = df["dist_km"].isna() & df["lat"].notna()
    df.loc[mask_sin_dist, "dist_km"] = df[mask_sin_dist].apply(
        lambda r: round(_haversine_km(r["lat"], r["lng"], LICEO_LAT, LICEO_LNG), 1), axis=1
    )

    # Fallback comunas para filas sin coordenadas
    mask_sin_lat = df["lat"].isna()
    df.loc[mask_sin_lat, "lat"] = df.loc[mask_sin_lat, "comuna_up"].map(
        lambda c: COORD_COMUNAS.get(c, (None, None))[0]
    )
    df.loc[mask_sin_lat, "lng"] = df.loc[mask_sin_lat, "comuna_up"].map(
        lambda c: COORD_COMUNAS.get(c, (None, None))[1]
    )
    df.loc[mask_sin_lat, "geo_mode"] = "centroide_comuna"

    df["tiempo_est"] = df["dist_km"].apply(
        lambda d: _tiempo_estimado(d) if pd.notna(d) else "—"
    )

    # Cruce con atrasos
    if df_atrasos_alumnos is not None and not df_atrasos_alumnos.empty:
        def _norm(s): return str(s).strip().upper()
        df["_key"] = df["nombre"].apply(_norm)
        df_atr = df_atrasos_alumnos.copy()
        df_atr["_key"] = df_atr["nombre"].apply(_norm)
        df = df.merge(
            df_atr[["_key","n_atrasos","alerta","pct_justificados"]].drop_duplicates("_key"),
            on="_key", how="left",
        )
        df["n_atrasos"]        = df["n_atrasos"].fillna(0).astype(int)
        df["alerta"]           = df["alerta"].fillna("SIN ATRASOS")
        df["pct_justificados"] = df["pct_justificados"].fillna(0)
    else:
        df["n_atrasos"]        = 0
        df["alerta"]           = "SIN ATRASOS"
        df["pct_justificados"] = 0.0

    return df[df["lat"].notna()].copy()


def _color_alerta(alerta: str) -> str:
    return {
        "CRITICO":     "#dc2626",
        "ALTO":        "#d97706",
        "MEDIO":       "#7c3aed",
        "BAJO":        "#2563eb",
        "SIN ATRASOS": "#16a34a",
    }.get(alerta, "#6b7280")


def render_geo_page(
    df_matricula: pd.DataFrame | None,
    df_atrasos_alumnos: pd.DataFrame | None = None,
    stamp: str = "",
    df_geocoded: pd.DataFrame | None = None,
):
    st.markdown("""
    <div class="sigma-header">
        <div>
            <div class="sigma-logo" style="font-size:1.5rem">SIGMA</div>
            <div class="sigma-tagline">Geolocalización · Procedencia de alumnos</div>
        </div>
    </div>""", unsafe_allow_html=True)

    if df_matricula is None or df_matricula.empty:
        st.markdown(
            '<div class="sigma-alert info">Sin datos de matrícula disponibles.</div>',
            unsafe_allow_html=True,
        )
        return

    # ── Construir GeoDF ───────────────────────────────────────────────
    # ── Cargar geocodificación existente si hay ──────────────────────
    _geo_gold = Path("data/gold/geocoding")
    _geo_path = _geo_gold / "alumnos_geocoded.parquet"
    if df_geocoded is None and _geo_path.exists():
        try:
            df_geocoded = pd.read_parquet(_geo_path)
        except Exception:
            df_geocoded = None

    tiene_geocodificacion = df_geocoded is not None and not df_geocoded.empty
    n_exactos = int((df_geocoded["geo_source"].str.contains("nominatim")).sum()) if tiene_geocodificacion else 0
    n_centroide = int((df_geocoded["geo_source"] == "centroide_comuna").sum()) if tiene_geocodificacion else 0

    df_geo = _build_geo_df(df_matricula, df_atrasos_alumnos, df_geocoded)
    tiene_atrasos = df_atrasos_alumnos is not None and not df_atrasos_alumnos.empty

    # ── Panel de geocodificación ─────────────────────────────────────
    tiene_dir = "direccion" in (df_matricula.columns if df_matricula is not None else [])

    with st.expander(
        f"{'✅ Geocodificación activa' if tiene_geocodificacion else '⚙️ Activar geocodificación exacta por dirección'} "
        f"({'exactas: ' + str(n_exactos) + ', centroide: ' + str(n_centroide) if tiene_geocodificacion else 'usando centroide de comuna'})",
        expanded=not tiene_geocodificacion,
    ):
        if not tiene_dir:
            st.markdown(
                '<div class="sigma-alert info">'
                'El CSV de matrícula actual <b>no incluye columna Dirección</b>. '
                'Carga el CSV actualizado de Syscol con la columna Dirección para activar la geocodificación exacta.'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            col_g1, col_g2 = st.columns([3, 1])
            with col_g1:
                if tiene_geocodificacion:
                    st.markdown(
                        f'<div class="sigma-alert success">'
                        f'✅ <b>{n_exactos}</b> alumnos con coordenadas exactas · '
                        f'<b>{n_centroide}</b> por centroide de comuna'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        '<div class="sigma-alert info">'
                        'Presiona <b>Geocodificar</b> para obtener coordenadas exactas de cada alumno '
                        'usando Nominatim (OpenStreetMap, gratuito). '
                        f'Tiempo estimado: <b>~{len(df_matricula) * 1.2 / 60:.0f} minutos</b> para {len(df_matricula)} alumnos. '
                        'El resultado se guarda en caché — solo procesa alumnos nuevos en futuras cargas.'
                        '</div>',
                        unsafe_allow_html=True,
                    )
            with col_g2:
                force_geo = st.checkbox("Forzar reproceso", value=False, key="geo_force")
                if st.button("🌍 Geocodificar", use_container_width=True, key="btn_geocodificar",
                             type="primary" if not tiene_geocodificacion else "secondary"):
                    if df_matricula is not None and "direccion" in df_matricula.columns:
                        from src.staging.geocode_matricula import run as run_geocode
                        progress_bar = st.progress(0, text="Iniciando geocodificación...")
                        try:
                            with st.spinner(f"Geocodificando {len(df_matricula)} alumnos..."):
                                df_geocoded = run_geocode(df_matricula, _geo_gold, force=force_geo)
                            st.success(f"✅ Geocodificación completa — {len(df_geocoded)} alumnos procesados")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error en geocodificación: {e}")
                    else:
                        st.warning("El CSV de matrícula no tiene columna 'direccion'.")

    # ── KPIs ──────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Resumen geográfico</div>', unsafe_allow_html=True)

    n_total    = len(df_geo)
    n_comunas  = df_geo["comuna_up"].nunique()
    dist_max   = df_geo["dist_km"].max()
    dist_prom  = round(df_geo["dist_km"].mean(), 1)
    com_lejana = df_geo.loc[df_geo["dist_km"].idxmax(), "comuna_up"] if n_total else "—"

    c1, c2, c3, c4, c5 = st.columns(5)
    def _kpi(col, val, label, color="#2563eb"):
        col.markdown(
            f"""<div style="background:#0d1220;border-radius:8px;padding:14px 8px;text-align:center;
                border:1px solid rgba(99,179,237,0.10);border-bottom:3px solid {color}">
                <div style="font-size:1.5rem;font-weight:700;color:{color}">{val}</div>
                <div style="font-size:0.65rem;color:#94a3b8;margin-top:2px;text-transform:uppercase">{label}</div>
            </div>""",
            unsafe_allow_html=True,
        )

    _kpi(c1, f"{n_total:,}",       "Alumnos mapeados",     "#2563eb")
    _kpi(c2, str(n_comunas),        "Comunas de origen",    "#7c3aed")
    _kpi(c3, f"{dist_prom} km",     "Distancia promedio",   "#d97706")
    _kpi(c4, f"{dist_max:.1f} km",  f"Máx. ({com_lejana})", "#dc2626")
    if tiene_atrasos:
        n_con_atrasos = int((df_geo["n_atrasos"] > 0).sum())
        _kpi(c5, f"{n_con_atrasos:,}", "Con atrasos registrados", "#d97706")
    else:
        _kpi(c5, "—", "Atrasos (sin datos)", "#4a5568")
    st.markdown("<br>", unsafe_allow_html=True)

    # ── TABS ──────────────────────────────────────────────────────────
    tab_mapa, tab_distancia, tab_tabla, tab_futuro = st.tabs([
        "🗺️ Mapa de procedencia",
        "📏 Análisis de distancia",
        "📋 Detalle por alumno",
        "🔮 Próximamente",
    ])

    # ════════════════════════════════════════════════════════════════
    # TAB MAPA
    # ════════════════════════════════════════════════════════════════
    with tab_mapa:
        # Filtro de vista
        f1, f2 = st.columns([2, 2])
        with f1:
            vista = st.selectbox(
                "Colorear por",
                ["Nivel de alerta (atrasos)", "Distancia al liceo", "Especialidad", "Nivel"],
                key="geo_vista",
            )
        with f2:
            solo_atrasos = st.checkbox(
                "Mostrar solo alumnos con atrasos",
                value=False,
                key="geo_solo_atrasos",
                disabled=not tiene_atrasos,
            )

        df_plot = df_geo[df_geo["n_atrasos"] > 0].copy() if solo_atrasos else df_geo.copy()

        # Agrupar por comuna para el mapa de burbujas
        grp_cols = ["comuna_up", "lat", "lng"]
        agg_dict: dict = {
            "nombre":  "count",
            "dist_km": "first",
        }
        if tiene_atrasos:
            agg_dict["n_atrasos"] = "sum"

        df_com_map = df_plot.groupby(grp_cols, as_index=False).agg(agg_dict)
        df_com_map = df_com_map.rename(columns={"nombre": "alumnos"})
        if "n_atrasos" not in df_com_map.columns:
            df_com_map["n_atrasos"] = 0

        # Color según vista
        if vista == "Nivel de alerta (atrasos)" and tiene_atrasos:
            max_atr = df_com_map["n_atrasos"].max() or 1
            colores_map = [
                "#dc2626" if v/max_atr >= 0.6 else
                ("#d97706" if v/max_atr >= 0.3 else "#2563eb")
                for v in df_com_map["n_atrasos"]
            ]
            size_col = "n_atrasos"
            legend_text = "🔴 muchos atrasos  🟡 moderados  🔵 pocos"
        elif vista == "Distancia al liceo":
            max_dist = df_com_map["dist_km"].max() or 1
            colores_map = [
                "#dc2626" if v/max_dist >= 0.7 else
                ("#d97706" if v/max_dist >= 0.4 else "#2563eb")
                for v in df_com_map["dist_km"]
            ]
            size_col = "alumnos"
            legend_text = "🔴 muy lejos  🟡 lejos  🔵 cerca"
        else:
            colores_map = ["#2563eb"] * len(df_com_map)
            size_col = "alumnos"
            legend_text = "Tamaño = cantidad de alumnos"

        # Tamaño de burbuja proporcional
        max_size_col = df_com_map[size_col].max() or 1
        sizes = [max(8, int(v / max_size_col * 50)) for v in df_com_map[size_col]]

        fig_map = go.Figure()

        # Burbujas comunas
        fig_map.add_trace(go.Scattermapbox(
            lat=df_com_map["lat"],
            lon=df_com_map["lng"],
            mode="markers+text",
            marker={"size": sizes, "color": colores_map, "opacity": 0.8},
            text=df_com_map["comuna_up"],
            textposition="top center",
            textfont={"size": 10, "color": "#e2e8f0"},
            customdata=df_com_map[["alumnos","n_atrasos","dist_km"]].values,
            hovertemplate=(
                "<b>%{text}</b><br>"
                "Alumnos: %{customdata[0]}<br>"
                "Atrasos: %{customdata[1]}<br>"
                "Dist. al liceo: %{customdata[2]:.1f} km<extra></extra>"
            ),
            name="Comunas",
        ))

        # Marcador del liceo
        fig_map.add_trace(go.Scattermapbox(
            lat=[LICEO_LAT],
            lon=[LICEO_LNG],
            mode="markers+text",
            marker={"size": 18, "color": "#f6ad55", "symbol": "star"},
            text=[LICEO_NAME],
            textposition="bottom center",
            textfont={"size": 11, "color": "#f6ad55"},
            hovertemplate=f"<b>{LICEO_NAME}</b><br>Lat: {LICEO_LAT}<br>Lng: {LICEO_LNG}<extra></extra>",
            name="Liceo",
        ))

        # Líneas desde cada comuna al liceo
        for _, row in df_com_map.iterrows():
            fig_map.add_trace(go.Scattermapbox(
                lat=[row["lat"], LICEO_LAT],
                lon=[row["lng"], LICEO_LNG],
                mode="lines",
                line={"width": max(0.5, min(3, row["alumnos"]/50)), "color": "rgba(99,179,237,0.15)"},
                hoverinfo="skip",
                showlegend=False,
            ))

        fig_map.update_layout(
            mapbox={
                "style": "carto-darkmatter",
                "center": {"lat": -33.45, "lon": -70.70},
                "zoom": 10.5,
            },
            paper_bgcolor="#080c14",
            height=560,
            margin={"l": 0, "r": 0, "t": 0, "b": 0},
            legend={"font": {"size": 10, "color": "#e2e8f0"}, "bgcolor": "rgba(0,0,0,0)"},
            showlegend=True,
        )

        st.plotly_chart(fig_map, use_container_width=True, config={"displayModeBar": False})
        st.markdown(
            f'<div style="font-family:DM Mono,monospace;font-size:0.65rem;color:#4a5568;text-align:center">'
            f'{legend_text} · Tamaño = {"atrasos" if vista=="Nivel de alerta (atrasos)" else "alumnos"} · '
            f'Coordenadas por centroide de comuna</div>',
            unsafe_allow_html=True,
        )

    # ════════════════════════════════════════════════════════════════
    # TAB DISTANCIA
    # ════════════════════════════════════════════════════════════════
    with tab_distancia:
        st.markdown('<div class="section-title">Distribución por distancia al liceo</div>', unsafe_allow_html=True)

        # Rangos de distancia
        bins   = [0, 2, 5, 10, 20, 100]
        labels = ["0-2 km (muy cerca)", "2-5 km (cerca)", "5-10 km (media)", "10-20 km (lejos)", ">20 km (muy lejos)"]
        df_geo["rango_dist"] = pd.cut(df_geo["dist_km"], bins=bins, labels=labels, right=False)

        df_rango = (
            df_geo.groupby("rango_dist", as_index=False, observed=True)
            .agg(
                Alumnos   = ("nombre", "count"),
                Atrasos   = ("n_atrasos", "sum"),
                Dist_prom = ("dist_km", "mean"),
            )
        )
        df_rango["Dist_prom"]      = df_rango["Dist_prom"].round(1)
        df_rango["Prom Atr/Alumno"]= (df_rango["Atrasos"] / df_rango["Alumnos"]).round(2)
        df_rango["% Alumnos"]      = (df_rango["Alumnos"] / df_rango["Alumnos"].sum() * 100).round(1).astype(str) + "%"

        d1, d2 = st.columns(2)
        with d1:
            show_pretty_table(
                df_rango.rename(columns={"rango_dist": "Rango distancia", "Dist_prom": "Dist. prom (km)"}),
                max_rows=10, height=260,
            )

        with d2:
            colores_rango = ["#16a34a","#2563eb","#7c3aed","#d97706","#dc2626"]
            fig_rango = go.Figure(go.Bar(
                x=df_rango["rango_dist"].astype(str),
                y=df_rango["Alumnos"],
                marker_color=colores_rango[:len(df_rango)],
                text=df_rango["Alumnos"],
                textposition="outside",
                textfont={"size": 11, "color": "#e2e8f0"},
                hovertemplate="<b>%{x}</b><br>Alumnos: %{y}<extra></extra>",
            ))
            fig_rango.update_layout(
                paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                font={"color": "#e2e8f0"}, height=280,
                margin={"l": 10, "r": 10, "t": 10, "b": 10},
                xaxis={"gridcolor": "rgba(0,0,0,0)", "tickangle": -15},
                yaxis={"gridcolor": "#1a2035"},
                showlegend=False,
            )
            st.plotly_chart(fig_rango, use_container_width=True, config={"displayModeBar": False})

        # Scatter distancia vs atrasos
        if tiene_atrasos:
            st.markdown('<div class="section-title" style="margin-top:16px">Distancia vs atrasos por alumno</div>', unsafe_allow_html=True)

            df_scatter = df_geo[df_geo["dist_km"].notna()].copy()
            df_scatter["dist_km"]   = pd.to_numeric(df_scatter["dist_km"],   errors="coerce")
            df_scatter["n_atrasos"] = pd.to_numeric(df_scatter["n_atrasos"], errors="coerce").fillna(0)
            df_scatter = df_scatter[df_scatter["dist_km"].notna()]
            colores_sc = [_color_alerta(a) for a in df_scatter["alerta"]]

            fig_sc = go.Figure(go.Scatter(
                x=df_scatter["dist_km"],
                y=df_scatter["n_atrasos"],
                mode="markers",
                marker={
                    "size": 7,
                    "color": colores_sc,
                    "opacity": 0.7,
                    "line": {"width": 0},
                },
                customdata=df_scatter[["nombre","comuna_up","alerta","tiempo_est"]].values,
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "Comuna: %{customdata[1]}<br>"
                    "Distancia: %{x:.1f} km<br>"
                    "Atrasos: %{y}<br>"
                    "Alerta: %{customdata[2]}<br>"
                    "Tiempo est.: %{customdata[3]}<extra></extra>"
                ),
            ))
            # Línea de tendencia simple
            if len(df_scatter) > 10:
                import numpy as np
                _x = pd.to_numeric(df_scatter["dist_km"],  errors="coerce").dropna()
                _y = pd.to_numeric(df_scatter["n_atrasos"], errors="coerce").loc[_x.index]
                if len(_x) > 2:
                    z = np.polyfit(_x, _y, 1)
                    x_line = [float(_x.min()), float(_x.max())]
                    y_line = [z[0]*x + z[1] for x in x_line]
                    fig_sc.add_trace(go.Scatter(
                        x=x_line, y=y_line,
                    mode="lines",
                    line={"color": "rgba(246,173,85,0.6)", "dash": "dash", "width": 1.5},
                    name="Tendencia",
                    hoverinfo="skip",
                ))
            fig_sc.update_layout(
                paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                font={"color": "#e2e8f0"}, height=320,
                margin={"l": 10, "r": 10, "t": 10, "b": 10},
                xaxis={"gridcolor": "#1a2035", "title": "Distancia al liceo (km)"},
                yaxis={"gridcolor": "#1a2035", "title": "N° atrasos"},
                legend={"font": {"size": 10}, "bgcolor": "rgba(0,0,0,0)"},
                showlegend=True,
            )
            st.plotly_chart(fig_sc, use_container_width=True, config={"displayModeBar": False})

            corr = df_scatter[["dist_km","n_atrasos"]].corr().iloc[0,1]
            st.markdown(
                f'<div class="sigma-alert info">'
                f'Correlación distancia ↔ atrasos: <b>r = {corr:.2f}</b>. '
                f'{"Correlación positiva moderada — la distancia influye en los atrasos." if corr > 0.3 else "Correlación baja — la distancia no es el principal factor de atrasos."}'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ════════════════════════════════════════════════════════════════
    # TAB TABLA
    # ════════════════════════════════════════════════════════════════
    with tab_tabla:
        st.markdown('<div class="section-title">Detalle por alumno</div>', unsafe_allow_html=True)

        tf1, tf2, tf3 = st.columns(3)
        with tf1:
            comunas_opts = ["Todas"] + sorted(df_geo["comuna_up"].unique().tolist())
            fil_com = st.selectbox("Comuna", comunas_opts, key="geo_fil_com")
        with tf2:
            rangos_opts = ["Todos"] + labels
            fil_rango = st.selectbox("Distancia", rangos_opts, key="geo_fil_rango")
        with tf3:
            orden_opts = ["Más atrasos", "Más lejos", "Nombre"]
            fil_orden = st.selectbox("Ordenar por", orden_opts, key="geo_fil_orden")

        df_tab = df_geo.copy()
        if fil_com != "Todas":
            df_tab = df_tab[df_tab["comuna_up"] == fil_com]
        if fil_rango != "Todos":
            df_tab = df_tab[df_tab["rango_dist"].astype(str) == fil_rango]

        sort_map = {"Más atrasos": ("n_atrasos", False), "Más lejos": ("dist_km", False), "Nombre": ("nombre", True)}
        sc, sa = sort_map[fil_orden]
        if sc in df_tab.columns:
            df_tab = df_tab.sort_values(sc, ascending=sa)

        cols_show = [c for c in ["nombre","course_code","specialty","comuna_up","direccion",
                                  "dist_km","tiempo_est","geo_mode","n_atrasos","alerta"] if c in df_tab.columns]
        df_show = df_tab[cols_show].rename(columns={
            "nombre":      "Nombre",
            "course_code": "Curso",
            "specialty":   "Especialidad",
            "comuna_up":   "Comuna",
            "dist_km":     "Dist. (km)",
            "tiempo_est":  "Tiempo est.",
            "direccion":   "Dirección",
            "geo_mode":    "Precisión GPS",
            "n_atrasos":   "Atrasos",
            "alerta":      "Alerta",
        }).reset_index(drop=True)

        if "Alerta" in df_show.columns:
            df_show["Alerta"] = df_show["Alerta"].map({
                "CRITICO":"🔴 Crítico","ALTO":"🟡 Alto",
                "MEDIO":"🟠 Medio","BAJO":"🟢 Bajo","SIN ATRASOS":"⚪ Sin atrasos",
            }).fillna("—")

        st.markdown(
            f'<div class="record-count">Mostrando <span>{len(df_show):,}</span> alumnos</div>',
            unsafe_allow_html=True,
        )
        show_pretty_table(df_show, max_rows=300, height=500)

    # ════════════════════════════════════════════════════════════════
    # TAB PRÓXIMAMENTE
    # ════════════════════════════════════════════════════════════════
    with tab_futuro:
        st.markdown('<div class="section-title">Estado de fases</div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="sigma-alert success">
            <b>✅ Fase 1 — Mapa por centroide de comuna</b><br>
            Completada. Mapa interactivo con burbujas por comuna, distancia lineal al liceo,
            análisis de distancia vs atrasos.
        </div>
        <br>
        <div class="sigma-alert success">
            <b>✅ Fase 2 — Geocodificación exacta por dirección</b><br>
            Completada. 1.017 alumnos con coordenadas exactas vía Nominatim (OpenStreetMap).
            287 por centroide de comuna como fallback. Caché activo — solo procesa alumnos nuevos.
        </div>
        <br>
        <div class="sigma-alert info">
            <b>🔜 Fase 3 — Rutas en transporte público (Red Metropolitana)</b><br>
            Con HERE Maps API (gratuita hasta 250.000 requests/mes), SIGMA calculará:<br>
            • Tiempo real de viaje en micro/metro desde la dirección del alumno hasta el liceo<br>
            • Qué recorridos de Red tomar y dónde hacer combinaciones<br>
            • Hora de salida recomendada para llegar a las 8:00 hrs<br>
            • Alumnos en "riesgo de atraso estructural" por tiempo de viaje &gt; 45 min
        </div>
        <br>
        <div class="sigma-alert info">
            <b>🔜 Fase 4 — Mapa de calor dinámico</b><br>
            Superposición de densidad de alumnos con atrasos sobre el mapa de Santiago,
            identificando zonas geográficas de alta concentración de riesgo.
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="section-title" style="margin-top:16px">¿Cómo activar Fase 3?</div>', unsafe_allow_html=True)
        st.markdown("""
        <div style="font-family:DM Sans,sans-serif;font-size:0.88rem;color:#e2e8f0;line-height:1.7">
            <b>1.</b> Crear cuenta gratuita en <a href="https://developer.here.com" target="_blank"
               style="color:#63b3ed">developer.here.com</a> y copiar la API key<br>
            <b>2.</b> Ingresar la API key en la configuración de SIGMA<br>
            <b>3.</b> Presionar "Calcular rutas" — SIGMA procesará automáticamente los tiempos de viaje
        </div>
        """, unsafe_allow_html=True)