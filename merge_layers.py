#!/usr/bin/env python3
"""
Copia las entidades de una capa de entidades (ORIGEN) a otra (DESTINO) en ArcGIS Online.

- Reproyecta la geometría al sistema de coordenadas de la capa DESTINO.
- Copia solo los campos que existen en AMBAS capas (omite OBJECTID, GlobalID y
  campos de editor tracking).
- Recorta los textos al tamaño del campo destino (evita fallos por longitud).
- Evita duplicados comparando el campo DEDUP_FIELD (por defecto 'rid').

Ejecutar con el Python de ArcGIS Pro (dueño de las capas):

    "C:\\Program Files\\ArcGIS\\Pro\\bin\\Python\\envs\\arcgispro-py3\\python.exe" merge_layers.py

Usa la sesión activa de ArcGIS Pro (GIS('pro')); si defines ARCGIS_USERNAME /
ARCGIS_PASSWORD, los usa en su lugar.
"""

import os
from arcgis.gis import GIS
from arcgis.features import FeatureLayer

SRC_URL = "https://services8.arcgis.com/F4wmVgGRtJMzSu8M/ArcGIS/rest/services/TerremotoVenezuela2026_Edificiosafectados1/FeatureServer/0"
DST_URL = "https://services8.arcgis.com/F4wmVgGRtJMzSu8M/ArcGIS/rest/services/TerremotoVenezuela2026_Edificiosafectados/FeatureServer/0"

DEDUP_FIELD = "rid"   # campo para no duplicar; pon None para copiar todo sin comparar
CHUNK = 500

# ---- Conexión ----
if os.environ.get("ARCGIS_USERNAME"):
    gis = GIS("https://www.arcgis.com", os.environ["ARCGIS_USERNAME"], os.environ["ARCGIS_PASSWORD"])
else:
    print("Usando la sesión activa de ArcGIS Pro (GIS('pro'))...")
    gis = GIS("pro")
print("Conectado como:", gis.users.me.username if gis.users.me else "(sesión Pro)")

src = FeatureLayer(SRC_URL, gis)
dst = FeatureLayer(DST_URL, gis)

# ---- Esquemas ----
dst_fields = {f["name"]: f for f in dst.properties.fields}
src_fields = {f["name"]: f for f in src.properties.fields}

# Campos del sistema / editor que NO se copian
SKIP_TYPES = {"esriFieldTypeOID", "esriFieldTypeGlobalID"}
editor_info = dst.properties.get("editFieldsInfo") or {}
skip_names = {v for v in editor_info.values() if isinstance(v, str)}

copy_fields = []
for name, f in dst_fields.items():
    if name not in src_fields:
        continue
    if f["type"] in SKIP_TYPES:
        continue
    if name in skip_names:
        continue
    copy_fields.append(name)
print("Campos a copiar:", copy_fields)

# SR destino
dst_sr = dst.properties.extent["spatialReference"]
dst_wkid = dst_sr.get("latestWkid") or dst_sr.get("wkid")
print("SR destino (wkid):", dst_wkid)

# ---- rids ya existentes en destino (para no duplicar) ----
existing = set()
if DEDUP_FIELD and DEDUP_FIELD in dst_fields:
    oid = dst.query(where="1=1", out_fields=DEDUP_FIELD, return_geometry=False, return_all_records=True)
    existing = {ft.attributes.get(DEDUP_FIELD) for ft in oid.features if ft.attributes.get(DEDUP_FIELD) is not None}
    print(f"En destino ya hay {len(existing)} valores de {DEDUP_FIELD}")

# ---- Leer origen (geometría reproyectada al SR destino) ----
src_set = src.query(where="1=1", out_fields="*", return_geometry=True,
                    out_sr=dst_wkid, return_all_records=True)
print(f"Entidades en origen: {len(src_set.features)}")

def trunc(name, value):
    if value is None:
        return None
    f = dst_fields[name]
    if f["type"] == "esriFieldTypeString" and f.get("length"):
        return str(value)[: f["length"]]
    return value

adds = []
ya_estan = 0
for ft in src_set.features:
    if DEDUP_FIELD and ft.attributes.get(DEDUP_FIELD) in existing:
        ya_estan += 1
        continue
    attrs = {n: trunc(n, ft.attributes.get(n)) for n in copy_fields}
    adds.append({"attributes": attrs, "geometry": ft.geometry})

print(f"A insertar: {len(adds)} (ya estaban: {ya_estan})")

# ---- Insertar por lotes ----
added, errors = 0, []
for i in range(0, len(adds), CHUNK):
    res = dst.edit_features(adds=adds[i:i + CHUNK], rollback_on_failure=False)
    for r in res.get("addResults", []):
        if r.get("success"):
            added += 1
        elif len(errors) < 5:
            errors.append(r.get("error"))

if errors:
    print("Ejemplos de error al insertar:", errors)
print(f"Listo: {added} entidades copiadas al destino.")
