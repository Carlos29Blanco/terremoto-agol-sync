#!/usr/bin/env python3
"""
Agranda (una sola vez) la longitud de los campos de texto del Feature Layer,
para que los textos largos y "geocodificada" no rompan la inserción.

Ejecutar con el Python de ArcGIS Pro (dueño de la capa):

    "C:\\Program Files\\ArcGIS\\Pro\\bin\\Python\\envs\\arcgispro-py3\\python.exe" fix_fields.py

Usa la sesión activa de ArcGIS Pro (GIS('pro')). No necesita credenciales.
"""

import os
from arcgis.gis import GIS

ITEM_ID = "871b614c750844529bfa04a9f5727557"

# Longitudes objetivo (generosas) por campo de texto
NEW_LEN = {
    "name": 255, "address": 255, "city": 120, "zone": 120,
    "source": 255, "notes": 4000, "coord_src": 30,
    "created_at": 40, "status": 20, "damage_level": 20,
}

if os.environ.get("ARCGIS_USERNAME"):
    gis = GIS("https://www.arcgis.com", os.environ["ARCGIS_USERNAME"], os.environ["ARCGIS_PASSWORD"])
else:
    print("Usando la sesión activa de ArcGIS Pro (GIS('pro'))...")
    gis = GIS("pro")
print("Conectado como:", gis.users.me.username if gis.users.me else "(sesión Pro)")

item = gis.content.get(ITEM_ID)
flayer = item.layers[0]
existing = {f["name"]: f for f in flayer.properties.fields}

fields = []
for name, length in NEW_LEN.items():
    f = existing.get(name)
    if not f:
        print(f"  (campo no encontrado, se omite: {name})")
        continue
    fields.append({
        "name": name,
        "type": f["type"],
        "alias": f.get("alias", name),
        "length": length,
        "nullable": f.get("nullable", True),
    })

print("Actualizando longitudes:", [(f["name"], f["length"]) for f in fields])
res = flayer.manager.update_definition({"fields": fields})
print("Resultado:", res)
print("Listo. Ahora el cron de GitHub puede insertar sin que se caiga por longitud.")
