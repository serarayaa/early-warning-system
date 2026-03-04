# 🎓 Early Warning System Escolar

Sistema de análisis de datos educativos orientado a la detección temprana de riesgo académico y deserción escolar.

## 🎯 Objetivo

Construir un pipeline profesional de datos que:

- Ingesta archivos de Syscol (Matrícula, Asistencia, Notas)
- Normaliza y estructura la información
- Genera indicadores de riesgo académico
- Permite integración con Power BI
- Incorpora modelo predictivo de Machine Learning

---

## 🏗️ Arquitectura

El proyecto sigue una arquitectura tipo Data Lake:

data/
- raw/        → Archivos originales (snapshots)
- staging/    → Datos limpios y normalizados
- curated/    → Modelo estructurado
- gold/       → Tablas finales para BI y ML

src/
- ingestion/  → Lectura de archivos
- staging/    → Transformaciones
- curated/    → Modelo intermedio
- gold/       → Marts analíticos

---

## 🚀 Setup del entorno

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt