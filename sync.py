#!/usr/bin/env python3
"""
Sync terremotovenezuela.com (Supabase) -> Feature Layer alojado en ArcGIS Online.

- Lee la tabla `buildings` de Supabase (clave publishable, lectura pública).
- A los registros sin coordenadas intenta geocodificarlos con el World Geocoding
  Service de Esri (con caché en disco para no repetir ni gastar créditos).
- Reemplaza el contenido del Feature Layer (deleteFeatures + addFeatures).

Pensado para correr en GitHub Actions. Solo depende de `requests`.

Variables de entorno (GitHub Secrets):
  SUPABASE_URL        p.ej. https://jckifxsdlnsvbztxydes.supabase.co/rest/v1/buildings
  SUPABASE_KEY        clave publishable de Supabase (sb_publishable_...)
  ARCGIS_API_KEY      API key de ArcGIS con permisos de edición sobre la capa y de geocodificación
  AGOL_LAYER_URL      URL REST de la capa, terminando en /FeatureServer/0
  GEOCODE             "true" (def.) | "false"
  GEOCODE_MIN_SCORE   umbral de aceptación del geocoder (def. 85)
"""

import os
import sys
import json
import time
import datetime
import requests

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
LAYER_URL    = os.environ["AGOL_LAYER_URL"].rstrip("/")
DO_GEOCODE   = os.environ.get("GEOCODE", "true").lower() == "true"
MIN_SCORE    = float(os.environ.get("GEOCODE_MIN_SCORE", "85"))
PORTAL       = os.environ.get("ARCGIS_PORTAL", "https://www.arcgis.com")

# Autenticación. Dos modos:
#   - ARCGIS_API_KEY                            -> se usa tal cual como token
#   - ARCGIS_CLIENT_ID + ARCGIS_CLIENT_SECRET  -> OAuth 2.0 (client credentials)
TOKEN = None  # se resuelve en get_token()

CACHE_FILE  = "geocode_cache.json"
GEOCODE_URL = "https://geocode-api.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"

SELECT = "id,name,address,city,zone,lat,lng,damage_level,status,general_source,notes,created_at"


def get_token():
    if os.environ.get("ARCGIS_API_KEY"):
        return os.environ["ARCGIS_API_KEY"]
    cid = os.environ["ARCGIS_CLIENT_ID"]
    secret = os.environ["ARCGIS_CLIENT_SECRET"]
    r = requests.post(f"{PORTAL}/sharing/rest/oauth2/token", data={
        "client_id": cid, "client_secret": secret,
        "grant_type": "client_credentials", "expiration": 1440, "f": "json",
    }, timeout=30)
    d = r.json()
    if "access_token" not in d:
        raise RuntimeError(f"No se pudo obtener token OAuth: {d}")
    return d["access_token"]


def fetch_supabase():
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    params  = {"select": SELECT}
    r = requests.get(SUPABASE_URL, headers=headers, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def geocode_one(address, city):
    q = ", ".join(x for x in [address, city, "Venezuela"] if x)
    if not q.strip():
        return None
    params = {
        "f": "json", "singleLine": q, "maxLocations": 1,
        "countryCode": "VEN", "outFields": "Score,Match_addr",
        "forStorage": "true",          # almacenamos el resultado -> consume créditos
        "token": TOKEN,
    }
    try:
        r = requests.get(GEOCODE_URL, params=params, timeout=30)
        d = r.json()
        cands = d.get("candidates") or []
        if cands:
            c = cands[0]
            return {
                "lng": c["location"]["x"],
                "lat": c["location"]["y"],
                "score": c.get("score", 0),
                "match": c.get("attributes", {}).get("Match_addr"),
            }
    except Exception as e:
        print("  geocode error:", e, file=sys.stderr)
    return None


def load_cache():
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(c):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False)


def post(endpoint, data):
    data = dict(data, f="json", token=TOKEN)
    r = requests.post(f"{LAYER_URL}/{endpoint}", data=data, timeout=120)
    r.raise_for_status()
    out = r.json()
    if "error" in out:
        raise RuntimeError(out["error"])
    return out


def main():
    global TOKEN
    TOKEN = get_token()
    rows = fetch_supabase()
    print(f"Supabase: {len(rows)} reportes")

    for b in rows:
        b["_src"] = "reportada" if (b.get("lat") and b.get("lng")) else None
        b["_score"] = None

    geocoded = 0
    if DO_GEOCODE:
        cache = load_cache()
        for b in rows:
            if b.get("lat") and b.get("lng"):
                continue
            key = f"{b.get('address') or ''}|{b.get('city') or ''}"
            if key.strip("|") == "":
                continue
            if key not in cache:
                cache[key] = geocode_one(b.get("address"), b.get("city"))
                time.sleep(0.1)
            hit = cache[key]
            if hit and hit.get("score", 0) >= MIN_SCORE:
                b["lat"], b["lng"] = hit["lat"], hit["lng"]
                b["_src"], b["_score"] = "geocodificada", hit["score"]
                geocoded += 1
        save_cache(cache)
    print(f"Geocodificados nuevos/aceptados: {geocoded}")

    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    adds = []
    for b in rows:
        if not (b.get("lat") and b.get("lng")):
            continue
        adds.append({
            "attributes": {
                "rid": b["id"],
                "name": (b.get("name") or "")[:255],
                "address": (b.get("address") or "")[:255],
                "city": (b.get("city") or "")[:120],
                "zone": (b.get("zone") or "")[:120],
                "damage_level": b.get("damage_level"),
                "status": b.get("status"),
                "source": (b.get("general_source") or "")[:255],
                "notes": (b.get("notes") or "")[:1000],
                "coord_src": b.get("_src"),
                "geo_score": b.get("_score"),
                "created_at": b.get("created_at"),
                "synced_at": now,
            },
            # La capa debe estar en WGS84 (wkid 4326). Ver bootstrap_layer.py.
            "geometry": {"x": b["lng"], "y": b["lat"], "spatialReference": {"wkid": 4326}},
        })

    deleted = post("deleteFeatures", {"where": "1=1"})
    print(f"Borrados: {len(deleted.get('deleteResults', []))}")

    added = 0
    for i in range(0, len(adds), 500):
        chunk = adds[i:i + 500]
        res = post("addFeatures", {"features": json.dumps(chunk)})
        added += sum(1 for x in res.get("addResults", []) if x.get("success"))

    print(f"Sync OK: {len(rows)} reportes, {added} con coordenadas ({geocoded} geocodificadas).")


if __name__ == "__main__":
    main()
