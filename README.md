# SIGMA / EWS Escolar

Sistema de procesamiento y monitoreo escolar con dos frentes integrados:

1. Pipeline de datos (CLI) para matricula y desiste.
2. Aplicacion Streamlit SIGMA para operacion diaria de matricula, asistencia y atrasos.

El proyecto construye capas data/raw, data/staging, data/curated y data/gold para seguimiento operativo, auditoria de cambios por corte y consumo analitico.

---

## Estado actual del proyecto (actualizado)

Esta documentacion refleja el estado real del repositorio al 2026-03-16. Frente a versiones anteriores, hoy el proyecto incluye:

- UI Streamlit productiva en app.py con modulo Matricula y modulo Asistencia.
- Pipeline de Asistencia (procesamiento a data/gold/asistencia) con KPIs y visualizaciones.
- Pipeline de Atrasos (procesamiento a data/gold/atrasos) con KPIs de recurrencia y riesgo.
- Validacion de esquema y mapeo de columnas (matricula, desiste, asistencia) antes de procesar uploads en UI.
- Comparacion automatica entre cortes de matricula (NEW, REMOVED, UPDATED, TRANSFER_INTERNAL).
- Regla PRE_RETIRO / POST_RETIRO para desiste centralizada en configuracion.
- Fingerprint de entrada en run-matricula para skip inteligente y recalculo selectivo de MASTER.
- Dependencias de visualizacion y reporteria (streamlit, plotly, matplotlib, reportlab, etc.) activas en requirements.

---

## 1) Objetivo funcional

Resolver la operacion diaria de datos escolares con trazabilidad de snapshots y calculo consistente de indicadores.

Flujo de Matricula (CLI):

1. Ingesta de archivo fuente (csv/xlsx/xls) como snapshot inmutable.
2. Estandarizacion en staging.
3. Construccion de snapshot curado y diff entre cortes.
4. Generacion de productos gold (current, demographics, history, status, master).

Flujo de Asistencia (UI):

1. Carga CSV desde Syscol.
2. Validacion de estructura.
3. Calculo de asistencia por alumno, curso y serie diaria hasta ultimo dia habil.
4. Persistencia en data/gold/asistencia.

Flujo de Atrasos (UI):

1. Carga CSV de atrasos desde Syscol.
2. Validacion de estructura y limpieza de columnas clave.
3. Calculo de indicadores por evento, alumno, curso y serie diaria.
4. Persistencia en data/gold/atrasos.

---

## 2) Stack y requisitos

- Python 3.10+ (recomendado 3.11).
- Dependencias principales (requirements.txt):
  - pandas, numpy, pyarrow, openpyxl, python-dateutil, pydantic, pyyaml, rich, pytest.
  - streamlit, plotly.
  - matplotlib, seaborn, scikit-learn.
  - reportlab.

Instalacion en Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## 3) Estructura del proyecto

```text
app.py                       # UI Streamlit principal (SIGMA)
main.py                      # Entry point CLI
requirements.txt

src/
  cli/
    args.py                  # Definicion de comandos CLI
    handlers.py              # Dispatcher de comandos
    pipeline.py              # run-matricula (orquestador)
  ingestion/
    ingest_matricula.py
  staging/
    build_stg_matricula.py
    build_stg_desiste.py
    build_stg_asistencia.py
  curated/
    build_curated_enrollment.py
  gold/
    enrollment_current.py
    enrollment_status.py
    enrollment_demographics.py
    enrollment_history.py
    enrollment_master.py
  comparison/
    compare_enrollment.py
  validation/
    schema_registry.py
    schema_validator.py
    column_mapper.py
  config/
    settings.py
    logging.yaml
  utils/
    transforms.py
    logging_utils.py

ui/
  matricula_page.py
  asistencia_page.py
  enrollment_data.py
  enrollment_processing.py
  schema_feedback.py
  styles.py

data/
  raw/
  staging/
  curated/
  gold/

tests/
  test_transforms.py
```

---

## 4) Modos de ejecucion

### 4.1 UI SIGMA (recomendado para operacion)

```powershell
streamlit run app.py
```

Incluye:

- Modulo Matricula.
- Modulo Asistencia.
- Modulo Atrasos.
- Modulos futuros marcados como Pronto.

### 4.2 CLI del pipeline

```powershell
python main.py <comando> [opciones]
```

CLI orientado a automatizacion y ejecucion batch.

---

## 5) Comandos CLI disponibles

### 5.1 Utilidades

- ping
  - Verifica entorno y muestra rutas efectivas.

### 5.2 Ingesta / Staging / Curated

- ingest-matricula <file>
  - Guarda snapshot en data/raw/matricula y actualiza manifest.json.
- build-stg-matricula <snapshot>
  - Genera parquet de staging desde snapshot raw.
- build-stg-desiste <file>
  - Genera parquet de staging para desiste.
- build-curated-enrollment
  - Requiere al menos 2 parquets en staging/matricula.
  - Genera snapshot curado + diff.

### 5.3 Gold de matricula

- gold-enrollment-status [--no-excel]
- gold-enrollment-current --snapshot-date YYYY-MM-DD [--excel]
- gold-enrollment-demographics --snapshot-date YYYY-MM-DD [--excel] [--top-n 10]
- gold-enrollment-history --snapshot-date YYYY-MM-DD [--excel]
- gold-enrollment-master [--snapshot-date YYYY-MM-DD] [--excel]

### 5.4 Pipeline end-to-end

- run-matricula <file> [--snapshot-date YYYY-MM-DD] [--excel] [--top-n N] [--force]
  [--desiste-file ... | --desiste-folder ... | --desiste-auto]

Ejemplo:

```powershell
python main.py run-matricula "C:\ruta\matricula-2026-03-16.csv" --snapshot-date 2026-03-16 --excel --desiste-auto
```

Comportamiento clave de run-matricula:

- Calcula fingerprint SHA256 + size del archivo fuente.
- Si no hay cambios y no se usa --force, omite pasos pesados.
- Si se solicita desiste, puede recalcular MASTER incluso cuando matricula no cambio.
- Guarda estado en data/.state/run_matricula_last_snapshot.txt.

---

## 6) Flujo de datos por capas

```text
Fuente Matricula (csv/xlsx/xls)
  -> data/raw/matricula (snapshot + manifest)
  -> data/staging/matricula/*.parquet
  -> data/curated/enrollment/snapshot + diff
  -> data/gold/enrollment/*

Fuente Desiste (csv/xlsx/xls)
  -> data/staging/desiste/*.parquet
  -> data/gold/enrollment/enrollment_master*

Fuente Asistencia (csv Syscol)
  -> procesamiento en UI (build_stg_asistencia.run)
  -> data/gold/asistencia/*.csv

Fuente Atrasos (csv Syscol)
  -> procesamiento en UI (build_stg_atrasos.run)
  -> data/gold/atrasos/*.csv
```

---

## 7) Artefactos generados

### 7.1 Raw

- data/raw/matricula/matricula_snapshot_YYYYMMDD_HHMMSS.ext
- data/raw/matricula/manifest.json

### 7.2 Staging

- data/staging/matricula/matricula_snapshot_YYYYMMDD_HHMMSS.parquet
- data/staging/desiste/desiste_snapshot__<archivo>.parquet

### 7.3 Curated

- data/curated/enrollment/enrollment_snapshot__matricula_snapshot_*.parquet
- data/curated/enrollment/enrollment_diff__<prev>__to__<curr>.parquet

### 7.4 Gold Matricula

- enrollment_current__YYYYMMDD.parquet
- enrollment_metrics__YYYYMMDD.parquet
- enrollment_demographics__YYYYMMDD.parquet
- enrollment_by_comuna__YYYYMMDD.parquet
- enrollment_by_nacionalidad__YYYYMMDD.parquet
- enrollment_by_course__YYYYMMDD.parquet
- enrollment_by_specialty__YYYYMMDD.parquet
- enrollment_demographics_history.parquet
- enrollment_age_anomalies__YYYYMMDD.parquet
- enrollment_age_anomalies__YYYYMMDD.txt
- enrollment_transfers_pre__<stamp>.parquet
- enrollment_transfers_post__<stamp>.parquet
- enrollment_transfers_all__<stamp>.parquet
- enrollment_master__YYYYMMDD.parquet
- enrollment_master_metrics__YYYYMMDD.parquet

Si se habilita export Excel en comandos gold, se generan equivalentes xlsx.

### 7.5 Gold Asistencia

- data/gold/asistencia/asistencia_alumnos.csv
- data/gold/asistencia/asistencia_cursos.csv
- data/gold/asistencia/asistencia_serie.csv
- data/gold/asistencia/asistencia_meta.csv

### 7.6 Gold Atrasos

- data/gold/atrasos/atrasos_eventos.csv
- data/gold/atrasos/atrasos_alumnos.csv
- data/gold/atrasos/atrasos_cursos.csv
- data/gold/atrasos/atrasos_serie.csv
- data/gold/atrasos/atrasos_meta.csv

---

## 8) Reglas de negocio relevantes

### 8.1 Dedupe por RUT

Se selecciona un registro representativo por rut_norm en etapas clave para evitar inflar indicadores.

### 8.2 Estado al corte

La clasificacion de estado usa fecha_retiro vs snapshot_date para determinar:

- MATRICULADO
- RETIRADO
- transferencias internas (cuando coexisten condiciones activo/retiro en un mismo RUT)

### 8.3 Regla PRE_RETIRO / POST_RETIRO para DESISTE

Configurada por EWS_CUTOFF_DESISTE (default 2026-03-16):

- PRE_RETIRO: snapshot_date <= cutoff, desiste se reporta como universo aparte.
- POST_RETIRO: snapshot_date > cutoff, desiste se ignora en MASTER.

### 8.4 Asistencia y umbrales

En asistencia se usan umbrales operativos:

- Alerta legal: < 85%
- Critico: < 75%
- Tendencia de baja segun comportamiento de ultimos 3 dias

---

## 9) Validacion de esquema (UI)

Antes de procesar archivos en la UI:

- Se valida estructura minima requerida.
- Se mapean aliases de columnas a nombres canonicos.
- Se muestra feedback visual de columnas detectadas/faltantes.

Esquemas definidos:

- Matricula
- Desiste
- Asistencia

Ubicacion: src/validation/schema_registry.py.

---

## 10) Configuracion por variables de entorno

### 10.1 Rutas

- EWS_DATA_DIR
- EWS_LOG_DIR

### 10.2 Reglas de negocio (opcionales)

- EWS_ATTENDANCE_RISK_PCT
- EWS_FAIL_GRADE_THRESHOLD
- EWS_MAX_FAILED_SUBJECTS
- EWS_CUTOFF_DESISTE
- EWS_AGE_MIN
- EWS_AGE_MAX
- EWS_AGE_DIFF_THRESHOLD

Ejemplo (PowerShell):

```powershell
$env:EWS_DATA_DIR = "D:\ews_data"
$env:EWS_LOG_DIR = "D:\ews_logs"
$env:EWS_CUTOFF_DESISTE = "2026-03-16"
python main.py ping
```

---

## 11) Ejecucion operativa recomendada

### 11.1 Matricula diaria (CLI)

```powershell
python main.py run-matricula "C:\ruta\matricula.csv" --snapshot-date YYYY-MM-DD --excel --desiste-auto
```

### 11.2 Operacion interactiva (UI)

```powershell
streamlit run app.py
```

En UI:

1. Seleccionar corte disponible.
2. Subir matricula (y desiste si corresponde por calendario).
3. Revisar tabs de dashboard, especialidades, desistimientos, demografia.
4. Cambiar a modulo Asistencia para carga y monitoreo diario.

---

## 12) Testing

Pruebas disponibles actualmente:

- tests/test_transforms.py

Ejecucion:

```powershell
pytest -q
```

Cobertura actual enfocada en utilidades de transformacion (normalizacion RUT, parseo de fechas, seleccion por RUT).

---

## 13) Scripts auxiliares incluidos

- sigma_charts.py
  - Graficos interactivos (plotly).
- sigma_pdf_charts.py
  - Graficos para export PDF (matplotlib).
- sigma_reports.py
  - Generacion de reportes PDF/Excel ejecutivos.
- parche_metrics_app.py
  - Script de parche puntual historico sobre app.py.

Estos scripts estan en el repo como soporte de reporteria/evolucion y pueden no estar acoplados al flujo principal actual de app.py.

---

## 14) Troubleshooting rapido

- Extension no soportada
  - Usar csv/xlsx/xls en matricula/desiste, csv en asistencia UI.

- Se requieren al menos 2 parquet en staging para curated
  - Cargar al menos dos snapshots de matricula antes de build-curated-enrollment.

- No aparece informacion en UI
  - Verificar existencia de archivos en data/gold/enrollment, data/gold/asistencia o data/gold/atrasos.

- Error de lectura CSV
  - El pipeline intenta multiples encodings (utf-8, latin1, cp1252), revisar export origen si persiste.

- MASTER no se recalcula con desiste
  - Confirmar uso de --desiste-file o --desiste-auto con staging/folder disponible.

---

## 15) Comandos de referencia

```powershell
python main.py ping
python main.py ingest-matricula "C:\ruta\matricula.csv"
python main.py build-stg-matricula "matricula_snapshot_20260316_123134.csv"
python main.py build-curated-enrollment
python main.py gold-enrollment-current --snapshot-date 2026-03-16 --excel
python main.py gold-enrollment-demographics --snapshot-date 2026-03-16 --excel --top-n 10
python main.py gold-enrollment-history --snapshot-date 2026-03-16 --excel
python main.py gold-enrollment-status
python main.py build-stg-desiste "C:\ruta\desiste_2026-03-16.csv"
python main.py gold-enrollment-master --snapshot-date 2026-03-16 --excel
python main.py run-matricula "C:\ruta\matricula-2026-03-16.csv" --snapshot-date 2026-03-16 --excel --desiste-auto
streamlit run app.py
```

---

## Licencia

MIT License
