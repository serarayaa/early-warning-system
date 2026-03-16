# ─────────────────────────────────────────────────────────────────────
# PARCHE para app.py — bloque _metrics en tab_reportes
# Busca y reemplaza el bloque de sexo_h / sexo_m
#
# El problema: df_current["sexo"] tiene "MASCULINO"/"FEMENINO",
# no "M"/"F". Los helpers _norm_sexo de sigma_reports.py ya lo
# manejan, pero el dict _metrics en app.py calculaba con == "M".
#
# INSTRUCCIÓN: En app.py busca estas 2 líneas (aprox. líneas 1340-1342):
#
#   "sexo_h":  int((df_current["sexo"].str.upper() == "M").sum()) if "sexo" in df_current.columns else 0,
#   "sexo_m":  int((df_current["sexo"].str.upper() == "F").sum()) if "sexo" in df_current.columns else 0,
#
# Y reemplázalas por:
#
#   "sexo_h":  int(df_current["sexo"].str.upper().str.strip().isin(["M","MASCULINO"]).sum()) if "sexo" in df_current.columns else 0,
#   "sexo_m":  int(df_current["sexo"].str.upper().str.strip().isin(["F","FEMENINO"]).sum()) if "sexo" in df_current.columns else 0,
#
# ─────────────────────────────────────────────────────────────────────
# Script automático: corre esto desde la raíz del proyecto
# python parche_metrics_app.py
# ─────────────────────────────────────────────────────────────────────

import re, pathlib, sys

app_path = pathlib.Path("app.py")
if not app_path.exists():
    print("ERROR: app.py no encontrado en el directorio actual")
    sys.exit(1)

content = app_path.read_text(encoding="utf-8")

OLD_H = '"sexo_h":         int((df_current["sexo"].str.upper() == "M").sum()) if "sexo" in df_current.columns else 0,'
NEW_H = '"sexo_h":         int(df_current["sexo"].str.upper().str.strip().isin(["M","MASCULINO"]).sum()) if "sexo" in df_current.columns else 0,'

OLD_M = '"sexo_m":         int((df_current["sexo"].str.upper() == "F").sum()) if "sexo" in df_current.columns else 0,'
NEW_M = '"sexo_m":         int(df_current["sexo"].str.upper().str.strip().isin(["F","FEMENINO"]).sum()) if "sexo" in df_current.columns else 0,'

found_h = OLD_H in content
found_m = OLD_M in content

if found_h:
    content = content.replace(OLD_H, NEW_H)
    print("✅ sexo_h parchado")
else:
    print("⚠️  sexo_h no encontrado — revisa manualmente")

if found_m:
    content = content.replace(OLD_M, NEW_M)
    print("✅ sexo_m parchado")
else:
    print("⚠️  sexo_m no encontrado — revisa manualmente")

if found_h or found_m:
    app_path.write_text(content, encoding="utf-8")
    print("✅ app.py guardado")