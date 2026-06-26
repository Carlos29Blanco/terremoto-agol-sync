# Sync terremotovenezuela.com → ArcGIS Online

Mantiene un **Feature Layer alojado en ArcGIS Online** sincronizado con los reportes de
edificios afectados de [terremotovenezuela.com](https://terremotovenezuela.com/)
(backend Supabase). A los reportes sin coordenadas intenta geocodificarlos con el
World Geocoding Service de Esri y marca su procedencia.

```
Supabase (tabla buildings)
        │  cada 20 min (GitHub Actions)
        ▼
   sync.py  ──► geocodifica faltantes (caché)  ──►  Feature Layer AGOL
                                                        │
                                                        ▼
                                          WebMap / WebScene (3D, swipe…)
```

## Estructura

| Archivo | Para qué |
|---|---|
| `sync.py` | Job recurrente. Solo depende de `requests`. |
| `bootstrap_layer.py` | Crea la capa **una vez** (local; usa `arcgis`). |
| `.github/workflows/sync.yml` | Cron de GitHub Actions cada 20 min. |
| `requirements.txt` | Dependencias del cron (`requests`). |
| `requirements-bootstrap.txt` | Dependencias del bootstrap (`arcgis`, `pandas`). |
| `geocode_cache.json` | Caché de direcciones geocodificadas (lo commitea el Action). |

## Puesta en marcha

### 1. Crear la capa (una sola vez, en tu equipo)

```bash
pip install -r requirements-bootstrap.txt
export SUPABASE_URL=https://jckifxsdlnsvbztxydes.supabase.co/rest/v1/buildings
export SUPABASE_KEY=sb_publishable_i7iEDrCVZcSt0k3RGFrY4g_WrtZBB4w
export ARCGIS_USERNAME=tu_usuario
export ARCGIS_PASSWORD=tu_password
python bootstrap_layer.py
```

Anota la **LAYER URL** que imprime (termina en `/FeatureServer/0`).

### 2. Crear credenciales de ArcGIS

Si tu organización ofrece **API keys**: crea una con privilegio **Geocoding (stored)** y
acceso de edición al item del paso 1 → usa el secret `ARCGIS_API_KEY`.

Si **no** ofrece API keys (p. ej. organizaciones de Respuesta a Desastres), usa
**OAuth 2.0 de aplicación**: Content → New item → Developer credentials →
*Credenciales de OAuth 2.0 (para autenticación de aplicaciones)*. Configura:

- **Privilegios**: Geocoding (stored).
- **Item access**: añade el Feature Layer del paso 1.
- Copia el **Client ID** y **Client Secret** → secrets `ARCGIS_CLIENT_ID` y `ARCGIS_CLIENT_SECRET`.

### 3. Configurar los Secrets del repositorio

`Settings → Secrets and variables → Actions → New repository secret`:

| Secret | Valor |
|---|---|
| `SUPABASE_URL` | `https://jckifxsdlnsvbztxydes.supabase.co/rest/v1/buildings` |
| `SUPABASE_KEY` | `sb_publishable_…` |
| `ARCGIS_CLIENT_ID` | Client ID de OAuth (o usa `ARCGIS_API_KEY` si tienes API key) |
| `ARCGIS_CLIENT_SECRET` | Client Secret de OAuth |
| `AGOL_LAYER_URL` | la LAYER URL del paso 1 |

### 4. Probar

Pestaña **Actions → Sync terremotovenezuela → AGOL → Run workflow**. Revisa el log:
debe decir `Sync OK: N reportes, M con coordenadas (K geocodificadas)`.

Luego corre solo cada 20 minutos.

## Campos de la capa

`rid` (id único de Supabase), `name`, `address`, `city`, `zone`, `damage_level`
(`total`/`severo`/`parcial`), `status`, `source`, `notes`, `coord_src`
(`reportada`/`geocodificada`), `geo_score`, `created_at`, `synced_at`.

> Usa `coord_src` para simbolizar distinto los puntos geocodificados (menos
> precisos) frente a los reportados con coordenadas exactas.

## Notas y decisiones

- **Estrategia de actualización:** `deleteFeatures(1=1)` + `addFeatures`. Simple y
  fiable para este volumen (cientos). Si la capa crece mucho o quieres conservar
  ObjectIDs, cambia a *upsert* por `rid`.
- **Créditos:** la geocodificación con `forStorage=true` consume créditos de ArcGIS.
  El caché evita re-geocodificar la misma dirección. Sube `GEOCODE_MIN_SCORE` para
  ser más estricto, o pon `GEOCODE=false` para desactivarlo.
- **Calidad:** muchas direcciones son vagas; las que no superen el umbral se quedan
  sin punto (igual que en la web). No se sobrescriben coordenadas ya reportadas.
- **Cron de GitHub Actions:** puede retrasarse y se **deshabilita tras 60 días sin
  actividad** en el repo. Para tiempos estrictos considera un cron externo o una
  Edge Function de Supabase.
- **Datos no oficiales:** son reportes ciudadanos/medios curados por terremotovenezuela.com.
  Mantén la atribución y revisa sus términos antes de republicar.
