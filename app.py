import re
from pathlib import Path
import pandas as pd
import streamlit as st

from ui.styles import inject_css

# Ajusta si usas PATHS
DATA_GOLD = Path("data/gold/enrollment")

st.set_page_config(
    page_title="Early Warning System – MVP Viewer",
    page_icon="📊",
    layout="wide",
)

inject_css(st)

st.title("📊 Early Warning System – MVP Viewer")
st.caption("Pipeline MVP: matrícula/enrollment → curated → gold")

# ---------- Helpers ----------
_MET_RE = re.compile(r"enrollment_metrics__(\d{8})\.parquet$", re.IGNORECASE)

@st.cache_data(show_spinner=False)
def list_available_dates() -> list[str]:
    if not DATA_GOLD.exists():
        return []
    dates = []
    for p in DATA_GOLD.glob("enrollment_metrics__*.parquet"):
        m = _MET_RE.match(p.name)
        if m:
            dates.append(m.group(1))
    return sorted(set(dates))

@st.cache_data(show_spinner=False)
def load_metrics(stamp: str) -> pd.DataFrame | None:
    p = DATA_GOLD / f"enrollment_metrics__{stamp}.parquet"
    return pd.read_parquet(p) if p.exists() else None

@st.cache_data(show_spinner=False)
def load_current(stamp: str) -> pd.DataFrame | None:
    p = DATA_GOLD / f"enrollment_current__{stamp}.parquet"
    return pd.read_parquet(p) if p.exists() else None

# ---------- Sidebar ----------
with st.sidebar:
    st.subheader("⚙️ Controles")
    available = list_available_dates()

    if not available:
        st.error("No se encontraron cortes en data/gold/enrollment.")
        st.stop()

    stamp = st.selectbox("Seleccionar fecha de corte", options=available, index=len(available)-1)
    st.markdown(f"<span class='ews-badge'>Corte: {stamp}</span>", unsafe_allow_html=True)

# ---------- Tabs ----------
tab_dash, tab_current, tab_demo, tab_trans, tab_anom = st.tabs(
    ["🏠 Dashboard", "👥 Current", "📌 Demografía", "🔁 Transferencias", "⚠️ Anomalías"]
)

# ---------- Dashboard ----------
with tab_dash:
    metrics = load_metrics(stamp)
    if metrics is None or metrics.empty:
        st.warning("No se encontró enrollment_metrics para esta fecha.")
    else:
        row = metrics.iloc[0].to_dict()

        a = int(row.get("matriculados_actuales", 0))
        b = int(row.get("retirados_reales", 0))
        c = int(row.get("transferencias_internas", 0))

        st.markdown("<div class='ews-card'>", unsafe_allow_html=True)
        st.subheader("Resumen general")

        col1, col2, col3 = st.columns(3)
        col1.metric("Matrícula actual", a)
        col2.metric("Retirados reales", b)
        col3.metric("Transferencias internas", c)

        st.markdown("<div class='ews-divider'></div>", unsafe_allow_html=True)
        st.caption("Tip: si ves diferencias entre snapshot y current, revisa `fecha_retiro` y la lógica de corte.")
        st.markdown("</div>", unsafe_allow_html=True)

# ---------- Current ----------
with tab_current:
    df = load_current(stamp)
    if df is None or df.empty:
        st.warning("No se encontró enrollment_current para esta fecha.")
    else:
        left, right = st.columns([1, 2])

        with left:
            st.markdown("<div class='ews-card'>", unsafe_allow_html=True)
            st.subheader("Filtros")
            q = st.text_input("Buscar (RUT o Nombre)", "")
            st.markdown("</div>", unsafe_allow_html=True)

        with right:
            st.markdown("<div class='ews-card'>", unsafe_allow_html=True)
            st.subheader("Listado")
            view = df.copy()
            if q.strip():
                qs = q.strip().upper()
                for col in ["rut_norm", "nombre", "rut"]:
                    if col not in view.columns:
                        view[col] = ""
                mask = (
                    view["rut_norm"].fillna("").astype(str).str.upper().str.contains(qs, na=False)
                    | view["rut"].fillna("").astype(str).str.upper().str.contains(qs, na=False)
                    | view["nombre"].fillna("").astype(str).str.upper().str.contains(qs, na=False)
                )
                view = view[mask]

            st.dataframe(view, use_container_width=True, height=520)
            st.markdown("</div>", unsafe_allow_html=True)

# ---------- Demografía / Transferencias / Anomalías ----------
with tab_demo:
    st.info("Aquí conectamos `enrollment_demographics__YYYYMMDD.parquet` y rankings. (Lo armamos al tiro después)")

with tab_trans:
    st.info("Aquí conectamos `enrollment_transfers_all__<stamp>.parquet` si existe.")

with tab_anom:
    st.info("Aquí conectamos `enrollment_age_anomalies__YYYYMMDD.parquet`.")