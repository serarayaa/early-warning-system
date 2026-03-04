import streamlit as st
from pathlib import Path
import pandas as pd

# =========================
# Configuración base
# =========================

st.set_page_config(page_title="EWS Dashboard", layout="wide")

BASE_DIR = Path(__file__).resolve().parent
GOLD_DIR = BASE_DIR / "data" / "gold" / "enrollment"

st.title("📊 Early Warning System – MVP Viewer")

# =========================
# Utilidades
# =========================

def get_available_dates():
    files = sorted(GOLD_DIR.glob("enrollment_current__*.parquet"))
    dates = [f.stem.split("__")[1] for f in files]
    return sorted(dates, reverse=True)


def load_parquet(prefix, date):
    file_path = GOLD_DIR / f"{prefix}__{date}.parquet"
    if file_path.exists():
        return pd.read_parquet(file_path)
    return None


# =========================
# Selector de fecha
# =========================

available_dates = get_available_dates()

if not available_dates:
    st.error("No se encontraron archivos en data/gold/enrollment/")
    st.stop()

selected_date = st.selectbox("Seleccionar fecha de corte", available_dates)

# =========================
# Tabs principales
# =========================

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["🏠 Dashboard", "👥 Current", "📈 Demografía", "🔁 Transferencias", "⚠️ Anomalías"]
)

# =========================
# TAB 1 — Dashboard
# =========================

with tab1:
    st.subheader("Resumen general")

    metrics = load_parquet("enrollment_metrics", selected_date)

    def pick_value(df: pd.DataFrame, candidates: list[str], default=0):
        if df is None or df.empty:
            return default
        cols = {c.lower(): c for c in df.columns}
        for cand in candidates:
            key = cand.lower()
            if key in cols:
                v = df[cols[key]].iloc[0]
                try:
                    return int(v)
                except Exception:
                    try:
                        return float(v)
                    except Exception:
                        return v
        return default

    if metrics is not None:
        with st.expander("🔎 Ver columnas disponibles en enrollment_metrics"):
            st.write(list(metrics.columns))
            st.dataframe(metrics, use_container_width=True)

        matricula = pick_value(metrics, ["matriculados_actuales", "matriculados", "matricula_actual", "matricula"])
        retirados = pick_value(metrics, ["retirados_reales", "retirados", "retirados_syscol"])
        transfers = pick_value(metrics, ["transferencias_internas", "transferencias", "is_transfer_internal"])

        col1, col2, col3 = st.columns(3)
        col1.metric("Matrícula actual", matricula)
        col2.metric("Retirados reales", retirados)
        col3.metric("Transferencias internas", transfers)
    else:
        st.warning("No se encontró enrollment_metrics para esta fecha.")

# =========================
# TAB 2 — Current
# =========================

with tab2:
    df_current = load_parquet("enrollment_current", selected_date)
    if df_current is not None:
        st.dataframe(df_current, use_container_width=True)
    else:
        st.warning("No se encontró enrollment_current para esta fecha.")

# =========================
# TAB 3 — Demografía
# =========================

with tab3:
    df_demo = load_parquet("enrollment_demographics", selected_date)
    if df_demo is not None:
        st.dataframe(df_demo, use_container_width=True)
    else:
        st.warning("No se encontró enrollment_demographics.")

# =========================
# TAB 4 — Transferencias
# =========================

with tab4:
    transfers = sorted(GOLD_DIR.glob(f"enrollment_transfers_all__{selected_date}*.parquet"))
    if transfers:
        df_transfers = pd.read_parquet(transfers[0])
        st.dataframe(df_transfers, use_container_width=True)
    else:
        st.info("No hay transferencias registradas.")

# =========================
# TAB 5 — Anomalías
# =========================

with tab5:
    df_anom = load_parquet("enrollment_age_anomalies", selected_date)
    if df_anom is not None:
        st.dataframe(df_anom, use_container_width=True)
    else:
        st.info("No se encontraron anomalías para esta fecha.")