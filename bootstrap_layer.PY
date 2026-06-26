#!/usr/bin/env python3
"""
Crea UNA SOLA VEZ la hosted feature layer en ArcGIS Online con el esquema correcto.
Ejecutar en local (no en el cron). Requiere la librería `arcgis`.

    pip install -r requirements-bootstrap.txt
    export SUPABASE_URL=https://jckifxsdlnsvbztxydes.supabase.co/rest/v1/buildings
    export SUPABASE_KEY=sb_publishable_...
    export ARCGIS_USERNAME=tu_usuario
    export ARCGIS_PASSWORD=tu_password
    python bootstrap_layer.py

Al terminar imprime el ITEM ID y la LAYER URL. Copia la LAYER URL en el
secret AGOL_LAYER_URL del repositorio (debe terminar en /FeatureServer/0).

La capa se crea en WGS84 (wkid 4326), que es lo que espera sync.py.
"""

import os
import datetime
import requests
import pandas as pd
from arcgis.gis import GIS
from arcgis.features import GeoAccessor  # noqa: F401 (activa el accessor .spatial)

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
SELECT = "id,name,address,city,zone,lat,lng,damage_level,status,general_source,notes,created_at"

gis = GIS(
    os.environ.get("ARCGIS_URL", "https://www.arcgis.com"),
    os.environ["ARCGIS_USERNAME"],
    os.environ["ARCGIS_PASSWORD"],
)

headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
rows = requests.get(SUPABASE_URL, headers=headers, params={"select": SELECT}, timeout=60).json()

now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
recs = []
for b in rows:
    if not (b.get("lat") and b.get("lng")):
        continue
    recs.append({
        "rid": b["id"],
        "name": b.get("name"),
        "address": b.get("address"),
        "city": b.get("city"),
        "zone": b.get("zone"),
        "damage_level": b.get("damage_level"),
        "status": b.get("status"),
        "source": b.get("general_source"),
        "notes": b.get("notes"),
        "coord_src": "reportada",
        "geo_score": None,
        "created_at": b.get("created_at"),
        "synced_at": now,
        "lat": b["lat"],
        "lng": b["lng"],
    })

df = pd.DataFrame(recs)
sdf = pd.DataFrame.spatial.from_xy(df, "lng", "lat", sr=4326)

item = sdf.spatial.to_featurelayer(
    title="Terremoto Venezuela 2026 - Edificios afectados",
    tags="terremoto,venezuela,2026,daños,terremotovenezuela.com",
)

print("CREATED ITEM ID:", item.id)
print("LAYER URL     :", item.layers[0].url)
print("\nSiguiente: comparte el item según corresponda y crea una API key")
print("con privilegio de edición sobre este item (+ geocodificación).")
