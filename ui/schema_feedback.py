# ui/schema_feedback.py

import streamlit as st


def mostrar_validacion_esquema(resultado: dict):
    if resultado is None:
        return

    nombre = resultado.get("nombre_esquema", "Archivo")
    es_valido = resultado.get("es_valido", False)
    detectadas = resultado.get("total_detectadas", 0)
    total = resultado.get("total_obligatorias", 0)
    faltantes = resultado.get("obligatorias_faltantes", [])
    nuevas = resultado.get("columnas_no_reconocidas", [])
    mapeo = resultado.get("mapeo_original_a_canonico", {})

    if es_valido:
        st.markdown(
            f"""
            <div class="sigma-alert success">
                ✅ <b>Archivo válido para {nombre}</b><br>
                Columnas obligatorias detectadas: <b>{detectadas}/{total}</b>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div class="sigma-alert danger">
                ❌ <b>Archivo incompleto para {nombre}</b><br>
                Columnas obligatorias detectadas: <b>{detectadas}/{total}</b>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if faltantes:
        st.markdown("**Columnas obligatorias faltantes**")
        st.write(faltantes)

    if nuevas:
        st.markdown("**Columnas nuevas o no reconocidas**")
        st.write(nuevas)

    if mapeo:
        filas = [{"Columna original": k, "Campo reconocido": v} for k, v in mapeo.items()]
        st.markdown("**Columnas reconocidas automáticamente**")
        st.dataframe(filas, use_container_width=True, hide_index=True)