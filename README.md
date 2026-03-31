# SIGMA — Sistema Integrado de Gestión y Monitoreo Académico

Sistema de alerta temprana (EWS) y monitoreo operativo para el **Liceo Politécnico Particular Andes** (RBD 24482, Renca). Construido en Python + Streamlit, procesa datos exportados desde Syscol y los convierte en indicadores accionables para dirección y equipos docentes.

---

## Estado actual (marzo 2026)

| Módulo | Estado |
|--------|--------|
| 🏠 Dashboard ejecutivo | ✅ Operativo |
| ⚡ Matrícula | ✅ Operativo |
| 📅 Asistencia | ✅ Operativo |
| ⏰ Atrasos | ✅ Operativo |
| 📋 Observaciones | ✅ Operativo |
| 📊 Histórico 2022-2026 | ✅ Operativo |
| 🗺️ Geolocalización | ✅ Operativo (78% precisión) |
| 📝 Notas | ✅ Operativo (esperando datos Syscol) |
| 🧠 DIA / Socioemocional | 🔜 Pronto |

---

## Stack

- **Python** 3.10+ (recomendado 3.11)
- **Streamlit** — UI principal
- **Pandas / NumPy** — procesamiento de datos
- **Plotly** — visualizaciones interactivas
- **Matplotlib** — gráficos para PDF
- **ReportLab** — generación de reportes PDF
- **OpenPyXL** — lectura/escritura de Excel
- **Nominatim (OpenStreetMap)** — geocodificación de direcciones

---

## Instalación

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

---

## Estructura del proyecto

```text
app.py                          # UI Streamlit principal — sidebar y router de módulos

src/
  staging/
    build_stg_matricula.py      # Pipeline matrícula (CSV Syscol → staging parquet)
    build_stg_asistencia.py     # Pipeline asistencia (CSV Syscol → gold)
    build_stg_atrasos.py        # Pipeline atrasos (CSV Syscol → gold)
    build_stg_observaciones.py  # Pipeline observaciones (CSV Syscol → gold)
    build_stg_notas.py          # Pipeline notas (XLS Syscol + Excel ejes → gold)
    build_historico.py          # Pipeline histórico 2022-2025 (ZIP Syscol → gold)
    build_stg_desiste.py        # Pipeline desistimiento
    geocode_matricula.py        # Geocodificación de direcciones con Nominatim
  gold/
    enrollment_current.py       # Gold matrícula corte actual
    enrollment_demographics.py  # Gold demografía
    enrollment_status.py        # Gold estado por alumno
  utils/
    transforms.py               # Normalización RUT, fechas, textos

ui/
  matricula_page.py             # Módulo Matrícula (7 tabs)
  asistencia_page.py            # Módulo Asistencia
  atrasos_page.py               # Módulo Atrasos
  observaciones_page.py         # Módulo Observaciones
  historico_page.py             # Módulo Histórico 2022-2026 (6 tabs)
  notas_page.py                 # Módulo Notas (5 tabs)
  dashboard_page.py             # Dashboard ejecutivo
  geo_page.py                   # Módulo Geolocalización
  executive_pdf.py              # Generador de PDFs (matrícula, asistencia, atrasos, ejecutivo)
  enrollment_data.py            # Carga y caché de datos de matrícula
  enrollment_processing.py      # Procesamiento de uploads de matrícula

data/
  raw/
    matricula/                  # Snapshots CSV inmutables de Syscol
    notas/                      # Excel de ejes de evaluación
  staging/
    matricula/                  # Parquets de staging
  curated/
    enrollment/                 # Snapshots curados + diffs entre cortes
  gold/
    enrollment/                 # Gold matrícula (parquets por corte)
    asistencia/                 # Gold asistencia (CSVs)
    atrasos/                    # Gold atrasos (CSVs)
    observaciones/              # Gold observaciones (CSVs)
    historico/                  # Gold histórico 2022-2026 (CSVs)
    geocoding/                  # Cache geocodificación + parquet geocoded
    notas/                      # Gold notas (CSVs + acumulado)
```

---

## Módulos operativos

### 🏠 Dashboard ejecutivo

Vista consolidada del establecimiento con:
- 6 KPIs con semáforo automático (matrícula, asistencia, alertas, atrasos, observaciones, riesgo total)
- Serie temporal de asistencia y observaciones
- Tabla de riesgo consolidado por alumno (descargable)
- Resumen por especialidad
- Botón **"Generar Reporte Ejecutivo PDF"** — 3 páginas con todos los módulos

### ⚡ Matrícula

- Carga CSV de matrícula desde Syscol (formato latin-1, separador `;`)
- Detección automática de alumnos **retirados** por fecha de retiro o estado
- Tabla de retirados en Dashboard y Nómina
- 7 tabs: Dashboard · Nómina · Especialidades · Demografía · Anomalías · Calidad de datos · Reportes
- Reportes PDF: Ejecutivo (indicadores + tablas) + Visual (gráficos)
- Checkbox **"Forzar reproceso"** para regenerar cuando el archivo tiene el mismo nombre

### 📅 Asistencia

- Carga CSV de asistencia diaria de Syscol
- **Acumulación automática** — deduplica por `fecha + rut_alumno`; puedes subir días sueltos o la semana completa sin duplicar
- Umbrales operativos: Legal < 85%, Crítico < 75%
- Tendencia de últimos 3 días por alumno
- Serie diaria, semáforo por curso, alertas individuales
- Reporte PDF descargable

### ⏰ Atrasos

- Carga CSV de atrasos de Syscol
- **Acumulación automática** — deduplica por `id_atraso` (ID único de Syscol)
- Análisis por alumno, curso, bloque horario y período del día
- Pico horario consistente detectado: 08:10–08:20
- Alertas por recurrencia: Bajo (1-2), Medio (3-5), Alto (6+)
- Reporte PDF descargable

### 📋 Observaciones

- Carga CSV de observaciones de Syscol
- **Acumulación automática** — deduplica por `id_obs`
- Tipos: NEG (negativa), POS (positiva), OBS (neutra)
- Análisis por alumno, curso, docente y serie diaria

### 📊 Histórico 2022-2026

- Carga ZIP con carpetas por año (formato Syscol `SYSCOL_años_anteriores.zip`)
- 6 tabs: Matrícula · Atrasos · Asistencia · Observaciones · Desglose personalizado · Cargar datos
- Tendencias detectadas:
  - Matrícula: 1.427 (2022) → 1.353 (2025), caída -5.2%
  - Atrasos: pico 2024 con +118% respecto a 2023
  - Asistencia anual estable: 89-90%

### 🗺️ Geolocalización

- Geocodificación de direcciones con Nominatim (OpenStreetMap)
- 1.017 exactas + 287 centroide (78% precisión en la última corrida)
- Caché en `data/gold/geocoding/geocode_cache.json`
- Visualización de distribución geográfica de alumnos

### 📝 Notas

- **Paso 1**: Carga Excel de ejes de evaluación (tabla maestra de ponderaciones)
- **Paso 2**: Carga ZIP con archivos XLS de Syscol (un archivo por eje × curso)
- Parseo automático del nombre de archivo: `{CURSO}-{COD_ASIG}-{N}per_{ID}.xls`
- Cálculo de promedio ponderado por asignatura redistribuyendo entre ejes disponibles
- **Acumulación automática** — deduplica por `nombre + curso + asignatura + semestre`
- 5 tabs: Configuración · Notas por alumno · Por curso · Riesgo académico · Cargar datos

---

## Flujo operativo semanal recomendado

```
Cada viernes:
  1. Bajar desde Syscol: asistencia semana + atrasos semana + observaciones semana
  2. Subir cada CSV en su módulo correspondiente en SIGMA
  3. Revisar Dashboard → tabla de riesgo consolidado
  4. Generar Reporte Ejecutivo PDF para dirección

Cada 2 semanas (cuando haya notas):
  1. Bajar ZIP de notas de Syscol
  2. Subir en módulo Notas → SIGMA calcula promedios ponderados
  3. Revisar tab Riesgo Académico

Cuando haya nueva matrícula:
  1. Subir CSV de matrícula con "Forzar reproceso" marcado
  2. Verificar alumnos retirados en Dashboard
```

---

## Acumulación y deduplicación de datos

Todos los pipelines de eventos acumulan datos entre cargas sucesivas y eliminan duplicados automáticamente:

| Módulo | Clave de deduplicación |
|--------|----------------------|
| Asistencia | `fecha + rut_alumno` |
| Atrasos | `id_atraso` (ID único Syscol) |
| Observaciones | `id_obs` (ID único Syscol) |
| Notas | `nombre + curso + cod_asig + term_id` |
| Matrícula | Snapshot completo — usar "Forzar reproceso" para actualizar |

Esto permite subir días sueltos durante la semana y la semana completa el viernes sin duplicar registros.

---

## Módulo de Notas — Estructura de ejes de evaluación

El sistema usa una **tabla maestra de ejes** (Excel) que define:

```
academic_year | level | specialty | term_id | cod_asignatura | asignatura | cod_eje | eje_evaluacion | ponderacion_eje
```

- `term_id`: S1 (1° semestre), S2 (2° semestre), EXT (4° medio — semestre extendido)
- `ponderacion_eje`: peso % del eje en la nota final de la asignatura (deben sumar 100%)
- Los archivos XLS de Syscol deben nombrarse: `{CURSO}-{COD_ASIG}-{N}per_{ID}.xls`
  - Ejemplo: `1EMA-LENG-1per_234122.xls`, `3EMB-MAT-2per_99999.xls`
  - 4° medio siempre usa `1per` (el sistema lo mapea a `EXT` internamente)

---

## Reportes PDF disponibles

| Reporte | Módulo | Páginas | Contenido |
|---------|--------|---------|-----------|
| Ejecutivo Matrícula | ⚡ Matrícula | 1 | KPIs + tablas de distribución |
| Visual Matrícula | ⚡ Matrícula | 2-3 | Gráficos de género, especialidad, cursos |
| Asistencia | 📅 Asistencia | 2-3 | KPIs + cursos críticos + alumnos bajo 75% |
| Atrasos | ⏰ Atrasos | 2-3 | KPIs + top alumnos + distribución horaria |
| Ejecutivo Consolidado | 🏠 Dashboard | 3 | Todos los módulos + semáforo general |

---

## Umbrales operativos

```python
# Asistencia
UMBRAL_LEGAL   = 85.0  # < 85% → alerta legal
UMBRAL_CRITICO = 75.0  # < 75% → crítico

# Atrasos
UMBRAL_MEDIO = 3   # >= 3 atrasos → alerta media
UMBRAL_ALTO  = 6   # >= 6 atrasos → alerta alta

# Observaciones negativas
UMBRAL_ALTO    = 3   # >= 3 obs. negativas → alto
UMBRAL_CRITICO = 5   # >= 5 obs. negativas → crítico

# Notas
NOTA_APRUEBA = 4.0
NOTA_EN_RIESGO = 4.5  # aprobado pero cerca del límite
```

---

## Troubleshooting

| Error | Causa | Solución |
|-------|-------|----------|
| `WindowsPath + str` | Concatenación de Path con string | Usar `Path / (str + str)` |
| `[WinError 32]` archivo en uso | openpyxl no cierra el workbook | `wb.close()` explícito, el temp se limpia al reiniciar |
| Datos no se actualizan | `__pycache__` con versión vieja | Eliminar `src/staging/__pycache__/` y reiniciar |
| Parquet basura `20261231` | Fecha por defecto en pipeline | Filtrado automático en `list_enrollment_dates()` |
| Asistencia/Atrasos vacíos tras subir ZIP histórico | Pipeline viejo en caché | Eliminar `__pycache__` y volver a subir ZIP |
| `UnboundLocalError: _load_csv` | Nombre de función local colisiona con módulo | Renombrar la función interna |

---

## Variables de entorno (opcionales)

```powershell
$env:EWS_DATA_DIR            = "D:\ews_data"
$env:EWS_LOG_DIR             = "D:\ews_logs"
$env:EWS_CUTOFF_DESISTE      = "2026-03-16"
$env:EWS_ATTENDANCE_RISK_PCT = "85"
$env:EWS_FAIL_GRADE_THRESHOLD = "4.0"
```

---

## Licencia

MIT License — Liceo Politécnico Particular Andes, Renca, 2026