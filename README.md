# Early Warning System (EWS) – Data Engineering Pipeline Educativo

Pipeline de datos escolar para procesar snapshots de matrícula y generar capas analíticas (`staging`, `curated`, `gold`) listas para seguimiento operativo y consumo en BI.

---

## Problema que resuelve

En operación escolar, los cambios diarios de matrícula generan inconsistencias, duplicados y pérdida de trazabilidad.
Este pipeline permite controlar cambios por snapshot, identificar diferencias y mantener métricas confiables por fecha de corte.

---

## 1) Objetivo

Este repositorio automatiza el flujo:

1. Ingesta de archivos de matrícula (`csv/xlsx/xls`) como snapshots inmutables.
2. Estandarización de datos en `staging`.
3. Construcción de snapshot/diff en `curated`.
4. Generación de reportes `gold` (estado actual, demografía, histórico, transferencias, master con DESISTE).

Está orientado a operación diaria con foco en:

- trazabilidad por snapshot,
- detección de cambios,
- deduplicación por RUT,
- reglas de negocio explícitas para retiro y DESISTE.

---

## 2) Stack y requisitos

- Python 3.10+ (recomendado 3.11)
- Dependencias en `requirements.txt`:
  - `pandas`, `pyarrow`, `openpyxl`, `python-dateutil`, `pydantic`, `rich`, `pyyaml`, `pytest`

Instalación:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## 3) Estructura del proyecto

```text
main.py
src/
  config/
  ingestion/
  staging/
  curated/
  gold/
  utils/
data/
  raw/
  staging/
  curated/
  gold/
logs/
```

Capas de datos:

- `data/raw`: snapshots originales (sin transformar)
- `data/staging`: limpieza y normalización
- `data/curated`: snapshot consolidado + diff entre cortes
- `data/gold`: métricas y salidas finales para operación/BI

---

## 3.1) Vista visual simple

```text
               +---------------------+
               |  Archivo matrícula  |
               |   (.csv/.xlsx/.xls) |
               +----------+----------+
                          |
                          v
                +---------+---------+
                | ingest-matricula  |
                |   data/raw/...    |
                +---------+---------+
                          |
                          v
                +---------+---------+
                | build-stg-...     |
                | data/staging/...  |
                +---------+---------+
                          |
                          v
                +---------+---------+
                | build-curated-... |
                | data/curated/...  |
                +---------+---------+
                          |
                          v
                +---------+---------+
                | gold-* reports    |
                | data/gold/...     |
                +---------+---------+
                          |
                          v
                +---------+---------+
                | BI / Seguimiento  |
                +-------------------+
```

Atajo operacional:

```text
run-matricula = ingest -> staging -> curated -> gold (+ master con DESISTE, si aplica)
```

---

## 4) Configuración por variables de entorno

Por defecto, el proyecto usa carpetas dentro del repo. Puedes sobreescribir rutas:

- `EWS_DATA_DIR`: cambia carpeta base de `data/`
- `EWS_LOG_DIR`: cambia carpeta de `logs/`

Ejemplo (PowerShell):

```powershell
$env:EWS_DATA_DIR = "D:\ews_data"
$env:EWS_LOG_DIR  = "D:\ews_logs"
python main.py ping
```

---

## 5) Comandos CLI

Comando base:

```powershell
python main.py <comando> [opciones]
```

### 5.1 Salud / utilidades

- `ping`
  - Verifica entorno y muestra rutas efectivas.

### 5.2 Ingesta y preparación

- `ingest-matricula <file>`
  - Copia a `data/raw/matricula/matricula_snapshot_YYYYMMDD_HHMMSS.ext`
  - Mantiene `manifest.json` con hash SHA256 para evitar recargas duplicadas.

- `build-stg-matricula <snapshot>`
  - Construye parquet en `data/staging/matricula/` desde un snapshot raw.

- `build-stg-desiste <file>`
  - Construye parquet en `data/staging/desiste/`.

- `build-curated-enrollment`
  - Requiere al menos 2 parquets en `data/staging/matricula/`.
  - Genera snapshot curado + diff de cambios.

### 5.3 Reportes GOLD

- `gold-enrollment-status [--no-excel]`
  - Reporte de diff y transferencias PRE/POST.

- `gold-enrollment-current --snapshot-date YYYY-MM-DD [--excel]`
  - Estado real al corte (matriculados, retirados reales, transferencias internas).

- `gold-enrollment-demographics --snapshot-date YYYY-MM-DD [--excel] [--top-n 10]`
  - KPIs demográficos y rankings.

- `gold-enrollment-history --snapshot-date YYYY-MM-DD [--excel]`
  - Actualiza histórico demográfico y detecta anomalías de edad/nacimiento.

- `gold-enrollment-master [--snapshot-date YYYY-MM-DD] [--excel]`
  - Consolidado master matrícula + DESISTE con regla de calendario.

### 5.4 Pipeline end-to-end

- `run-matricula <file> [--snapshot-date YYYY-MM-DD] [--excel] [--top-n N] [--force] [--desiste-file ... | --desiste-folder ... | --desiste-auto]`

Ejemplo recomendado de operación diaria:

```powershell
python main.py run-matricula "C:\Repositorio DATOS SYSCOL\Reporte Matrícula\RAW\matricula-2026-03-04.csv" --snapshot-date 2026-03-04 --excel --desiste-auto
```

Comportamiento clave de `run-matricula`:

- Detecta cambios reales por fingerprint (SHA256 + tamaño).
- Si no hubo cambios en matrícula:
  - salta pasos pesados (`ingest/staging/curated/gold`),
  - pero **sí puede recalcular MASTER** si se pidió DESISTE.
- `--force` obliga recálculo completo.

---

## 6) Artefactos de salida

### 6.1 Raw

- `data/raw/matricula/matricula_snapshot_YYYYMMDD_HHMMSS.<ext>`
- `data/raw/matricula/manifest.json`

### 6.2 Staging

- `data/staging/matricula/matricula_snapshot_YYYYMMDD_HHMMSS.parquet`
- `data/staging/desiste/desiste_snapshot__<archivo>.parquet`

### 6.3 Curated

- `data/curated/enrollment/enrollment_snapshot__matricula_snapshot_*.parquet`
- `data/curated/enrollment/enrollment_diff__<prev>__to__<curr>.parquet`

### 6.4 Gold (principales)

- Current:
  - `enrollment_current__YYYYMMDD.parquet`
  - `enrollment_metrics__YYYYMMDD.parquet`
- Demographics:
  - `enrollment_demographics__YYYYMMDD.parquet`
  - `enrollment_by_comuna__YYYYMMDD.parquet`
  - `enrollment_by_nacionalidad__YYYYMMDD.parquet`
  - `enrollment_by_course__YYYYMMDD.parquet`
  - `enrollment_by_specialty__YYYYMMDD.parquet`
- Status/transferencias:
  - `enrollment_transfers_pre__<stamp>.parquet`
  - `enrollment_transfers_post__<stamp>.parquet`
  - `enrollment_transfers_all__<stamp>.parquet`
  - `enrollment_status_latest.xlsx` (si aplica)
- History/anomalías:
  - `enrollment_demographics_history.parquet`
  - `enrollment_age_anomalies__YYYYMMDD.parquet`
  - `enrollment_age_anomalies__YYYYMMDD.txt`
- Master:
  - `enrollment_master__YYYYMMDD.parquet`
  - `enrollment_master_metrics__YYYYMMDD.parquet`

---

## 7) Reglas de negocio relevantes

### 7.1 Dedupe por RUT

En varias etapas se deduplica por RUT para evitar inflar indicadores por duplicados de Syscol.

### 7.2 Estado al corte

Se usa `fecha_retiro` comparada con `snapshot_date` para clasificar:

- `MATRICULADO` (activo al corte)
- `RETIRADO`
- `transferencia interna` (cuando un mismo RUT aparece activo y retirado según reglas)

### 7.3 Regla PRE/POST para DESISTE

En `gold-enrollment-master`:

- **PRE_RETIRO** (`snapshot_date <= 2026-03-17`): DESISTE se considera universo aparte.
- **POST_RETIRO** (`snapshot_date >= 2026-03-18`): DESISTE se ignora para el master.

---

## 8) Flujo operativo sugerido (diario)

1. Ejecutar pipeline completo de matrícula:

```powershell
python main.py run-matricula "<ruta_matricula>" --snapshot-date YYYY-MM-DD --excel --desiste-auto
```

2. Revisar outputs en `data/gold/enrollment/`.
3. Si solo cambió DESISTE, volver a correr `run-matricula` con opciones DESISTE (sin `--force`), y el sistema intentará recalcular `master` aunque matrícula no haya cambiado.

---

## 9) Troubleshooting rápido

- **"Extensión no soportada"**
  - Usa `csv`, `xlsx` o `xls`.

- **"Se requieren al menos 2 parquet en staging"**
  - Ejecuta al menos dos cargas de matrícula para generar diff curated.

- **"No existe snapshot en data/raw/matricula"**
  - Verifica nombre exacto pasado a `build-stg-matricula`.

- **Errores de lectura CSV (encoding/parser)**
  - El sistema intenta `utf-8`, `latin1`, `cp1252`; si falla, revisar archivo origen.

- **No se genera MASTER con DESISTE**
  - Confirmar `--desiste-file`, o `--desiste-auto` + staging desiste existente, o `--desiste-folder` válido.

---

## 10) Comandos de referencia (copy/paste)

```powershell
python main.py ping
python main.py ingest-matricula "C:\ruta\matricula.csv"
python main.py build-stg-matricula "matricula_snapshot_20260304_082243.csv"
python main.py build-curated-enrollment
python main.py gold-enrollment-current --snapshot-date 2026-03-04 --excel
python main.py gold-enrollment-demographics --snapshot-date 2026-03-04 --excel --top-n 10
python main.py gold-enrollment-history --snapshot-date 2026-03-04 --excel
python main.py gold-enrollment-status
python main.py build-stg-desiste "C:\ruta\desiste_2026-03-03.csv"
python main.py gold-enrollment-master --snapshot-date 2026-03-04 --excel
python main.py run-matricula "C:\ruta\matricula-2026-03-04.csv" --snapshot-date 2026-03-04 --excel --desiste-auto
```

---

## 11) Notas

- El proyecto prioriza trazabilidad por archivo/snapshot y reproducibilidad operativa.
- Los reportes `gold` están diseñados para consumo directo en BI y validación de control de matrícula.
- Logs y configuración de logging se encuentran en `src/config/logging.yaml` y `logs/`.

---

## 12) ROADMAP

### Corto plazo (1–2 semanas)

- [ ] Agregar validaciones de esquema de entrada por tipo de archivo (matrícula/desiste).
- [ ] Incluir chequeo de calidad automático post-run (nulos críticos, duplicados, outliers básicos).
- [ ] Publicar `gold` diario en carpeta de intercambio para BI (contrato de entrega estable).

### Mediano plazo (1–2 meses)

- [ ] Versionar reglas de negocio (ej. PRE/POST retiro) en configuración central.
- [ ] Añadir pruebas automáticas para funciones críticas (`staging`, `curated diff`, `master`).
- [ ] Generar dashboard de observabilidad de pipeline (duración, conteos, errores, freshness).

### Largo plazo (trimestre)

- [ ] Orquestar ejecución programada (scheduler) con alertas por falla.
- [ ] Incorporar features de riesgo académico complementarias (asistencia/notas) en capa `gold`.
- [ ] Definir capa semántica final para consumo analítico y/o modelo predictivo.

### Criterios de éxito del roadmap

- Menor tiempo operativo diario (ejecución + validación).
- Menos incidentes por calidad de datos.
- Mayor trazabilidad y reproducibilidad de resultados por fecha de corte.

---

## License

MIT License
