"""
SIGMA — Geocodificación de direcciones de alumnos
src/staging/geocode_matricula.py

Usa Nominatim (OpenStreetMap) — gratuito, sin API key.
Limit: 1 request/segundo (respetado automáticamente).

Estrategia en cascada:
  1. Dirección completa limpia + comuna + RM
  2. Solo calle + número + comuna (sin depto/block)
  3. Solo nombre de calle + comuna (sin número)
  4. Centroide de comuna (fallback siempre disponible)
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

import pandas as pd

log = logging.getLogger("sigma.geocode")

# ── Coordenadas de fallback por comuna ────────────────────────────────
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
    "RENCA":             (-33.4024, -70.7215),
    "SANTIAGO":          (-33.4569, -70.6483),
    "TILTIL":            (-33.0934, -70.9234),
}


def _clean_address(direccion: str, comuna: str) -> list[str]:
    """
    Genera lista de queries en cascada (más específico → menos específico).
    Nominatim prueba en orden hasta encontrar resultado.
    """
    d = str(direccion).strip()
    d = re.sub(r'\s+', ' ', d).replace('#', ' ').replace(',', ' ')
    d = re.sub(r'\s+', ' ', d).strip()
    com = str(comuna).strip().title()
    region = "Región Metropolitana, Chile"

    # Extraer base: CALLE + NÚMERO (descartar depto/block/villa)
    keywords = r'(BLOCK|BLK|DEPTO|DPTO|DEP\s*\d|TORRE|VILLA|COND|POBLACION|POB\s|CONJUNTO)'
    base = re.split(keywords, d.upper(), maxsplit=1)[0].strip()
    if not base:
        return []  # dirección vacía — usar fallback centroide

    # Extraer solo calle (sin número)
    calle_match = re.match(r'^((?:AV(?:ENIDA)?\.?\s+)?[A-ZÁÉÍÓÚÑ\s]+)', base)
    parts = base.split()
    solo_calle = calle_match.group(1).strip() if calle_match else (parts[0] if parts else base)

    return [
        f"{base}, {com}, {region}",        # 1. base + comuna
        f"{base}, Santiago, {region}",      # 2. base + Santiago (más amplio)
        f"{solo_calle}, {com}, {region}",   # 3. solo calle + comuna
        f"{com}, {region}",                 # 4. centroide comuna vía Nominatim
    ]


def _nominatim_query(query: str, session) -> tuple[float, float] | None:
    """Un request a Nominatim. Retorna (lat, lng) o None."""
    import urllib.parse
    url = (
        "https://nominatim.openstreetmap.org/search"
        f"?q={urllib.parse.quote(query)}"
        "&format=json&limit=1&countrycodes=cl"
    )
    try:
        resp = session.get(url, timeout=10)
        data = resp.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None


def geocode_dataframe(
    df: pd.DataFrame,
    cache_path: Path | None = None,
    delay: float = 1.1,
    col_dir: str = "direccion",
    col_com: str = "comuna",
    col_rut: str = "rut_norm",
) -> pd.DataFrame:
    """
    Geocodifica un DataFrame con columnas de dirección y comuna.
    
    Retorna DataFrame con columnas añadidas:
      - geo_lat, geo_lng   : coordenadas resultantes
      - geo_source         : 'nominatim_exact' | 'nominatim_fallback' | 'centroide_comuna'
      - geo_query          : query que funcionó
      - geo_dist_km        : distancia lineal al liceo
    
    Usa caché JSON para no repetir queries entre sesiones.
    """
    try:
        import requests
    except ImportError:
        raise ImportError("Instala requests: pip install requests")

    # ── Caché ─────────────────────────────────────────────────────────
    cache: dict = {}
    if cache_path and cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            log.info(f"Caché cargado: {len(cache)} entradas")
        except Exception:
            cache = {}

    LICEO_LAT = -33.4024
    LICEO_LNG = -70.7215

    def _haversine(lat1, lng1, lat2, lng2):
        import math
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
        return round(R * 2 * math.asin(math.sqrt(a)), 2)

    session = requests.Session()
    session.headers.update({"User-Agent": "SIGMA-EWS-Escolar/2.0 (sistema educacional)"})

    lats, lngs, sources, queries, dists = [], [], [], [], []
    n_new = 0

    for idx, row in df.iterrows():
        direccion = str(row.get(col_dir, "")).strip()
        comuna    = str(row.get(col_com, "")).strip().upper()
        rut       = str(row.get(col_rut, idx))

        # Clave de caché
        cache_key = f"{direccion}|{comuna}"

        if cache_key in cache:
            entry = cache[cache_key]
            lat, lng = entry["lat"], entry["lng"]
            source  = entry["source"]
            query   = entry["query"]
        else:
            lat = lng = None
            source = query = ""

            # Intentar geocodificar si hay dirección válida
            if len(direccion) > 5:
                cascade = _clean_address(direccion, comuna.title())
                for i, q in enumerate(cascade[:3]):  # solo los 3 primeros via Nominatim
                    if not q.strip():
                        continue
                    result = _nominatim_query(q, session)
                    time.sleep(delay)
                    n_new += 1
                    if result:
                        lat, lng = result
                        source = "nominatim_exact" if i == 0 else "nominatim_fallback"
                        query  = q
                        break

            # Fallback: centroide de comuna
            if lat is None:
                coords = COORD_COMUNAS.get(comuna)
                if coords:
                    lat, lng = coords
                    source = "centroide_comuna"
                    query  = f"centroide:{comuna}"

            # Guardar en caché
            if lat is not None:
                cache[cache_key] = {"lat": lat, "lng": lng, "source": source, "query": query}

        dist = _haversine(lat, lng, LICEO_LAT, LICEO_LNG) if lat is not None else None
        lats.append(lat)
        lngs.append(lng)
        sources.append(source)
        queries.append(query)
        dists.append(dist)

        if (idx + 1) % 50 == 0:
            log.info(f"  Geocodificados: {idx+1}/{len(df)} ({n_new} nuevos requests)")
            # Guardar caché periódicamente
            if cache_path:
                cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    # Guardar caché final
    if cache_path:
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info(f"Caché guardado: {len(cache)} entradas → {cache_path}")

    result_df = df.copy()
    result_df["geo_lat"]     = lats
    result_df["geo_lng"]     = lngs
    result_df["geo_source"]  = sources
    result_df["geo_query"]   = queries
    result_df["geo_dist_km"] = dists

    log.info(f"Geocodificación completa: {n_new} requests, "
             f"{sum(1 for s in sources if 'nominatim' in s)} exactos, "
             f"{sum(1 for s in sources if s == 'centroide_comuna')} por centroide")

    return result_df


def run(
    df_matricula: pd.DataFrame,
    gold_dir: Path | str = "data/gold/geocoding",
    force: bool = False,
) -> pd.DataFrame:
    """
    Punto de entrada principal.
    Lee el parquet de matrícula, geocodifica y guarda resultado.
    """
    gold_dir = Path(gold_dir)
    gold_dir.mkdir(parents=True, exist_ok=True)

    cache_path  = gold_dir / "geocode_cache.json"
    output_path = gold_dir / "alumnos_geocoded.parquet"

    if output_path.exists() and not force:
        log.info(f"Cargando geocodificación existente: {output_path}")
        return pd.read_parquet(output_path)

    log.info(f"Iniciando geocodificación de {len(df_matricula)} alumnos...")
    df_geo = geocode_dataframe(df_matricula, cache_path=cache_path)
    df_geo.to_parquet(output_path, index=False)

    # Resumen en CSV legible
    resumen = df_geo.groupby("geo_source", as_index=False).agg(
        alumnos=("rut_norm" if "rut_norm" in df_geo.columns else df_geo.columns[0], "count")
    )
    resumen.to_csv(gold_dir / "geocode_resumen.csv", index=False, encoding="utf-8-sig")

    log.info(f"Geocodificación guardada: {output_path}")
    return df_geo