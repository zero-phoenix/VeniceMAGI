# VeniceMAGI

VeniceMAGI es una variante MAGI con operacion cloud-first gratuita: usa proveedores guest sin key/login en el camino principal y mantiene una arquitectura de contenedor virtual local para orquestar capacidades.

## v2.0.0 — ventana propia e IDE sobre tu hardware

- **GUI de aplicación** (pywebview): hilo del enjambre en vivo (Melchior,
  Balthasar, Casper, Naoko), workspace con árbol y editor, galería de
  medios, estado y cola de trabajo. `VeniceMAGI.exe` abre la ventana;
  `--consola` mantiene el REPL.
- **Puerta de Edge aparcada** fuera de pantalla por defecto (toggle en la
  GUI): el navegador real sigue resolviendo la atestación, sin estorbar.
- **IDE real**: `read_file`, `list_dir`, `patch_file` quirúrgico,
  `delete_file` a papelera con journal, `hardware_info` (CPU/RAM/GPU/disco),
  `run_python` con plazo y **`shell` solo con tu aprobación clic a clic**.
- **Vídeo de planos**: planos como imágenes Venice + mp4 compuesto EN TU PC
  con ffmpeg (honesto: planos con fundidos, no vídeo AI fluido).
- **Ración visible**: contador de llamadas de hoy y caché LRU para que
  repetir no gaste cupo.

## Principios del sistema

- Sin cuenta ni key obligatoria en modo `cloud`.
- Sin evasion de cuotas (no rotacion automatica de IP/VPN).
- Transparencia: si el proveedor guest limita, se informa.
- Trazabilidad: cada render guarda metadata reproducible.

## Arquitectura actual

```
Usuario
  └─ REPL MAGI (/magi, /salud, /imagen, /video, ...)
      └─ CloudModelContainer (virtual local, sin inferencia local)
          └─ Proveedor guest cloud permitido (actual: Venice Guest)
```

Roles MAGI:

```
NAOKO      clasifica
MELCHIOR   construye
BALTHASAR  refuta ejecutando
CASPER     sintetiza
```

## Modos operativos

### 1) `cloud` (por defecto)
- `CLOUD_ONLY_MODE=1`
- Chat e imagen via proveedor guest cloud.
- Sin modelos locales de inferencia.
- Sin key/login en el camino principal.
- Video depende de capacidad guest disponible.

### 2) `hybrid` (opcional)
- Permite backends locales de imagen (`automatic1111`/`comfyui`) y rutas adicionales.
- Se activa con `/modo hybrid`.

## Comandos principales

```
/magi
/salud
/modo cloud|hybrid
/imagen [--ar 16:9] [--seed N] [--quality draft|standard|ultra] [--backend automatic1111|comfyui] PROMPT
/video [--duration 10s] PROMPT
/backend [automatic1111|comfyui]
/quality [draft|standard|ultra]
/notrack show|off|URL|required on|required off
/proxy URL|off
/sesion
/historial [n]
/galeria [n]
/ayuda
/salir
```

## Configuracion de entorno

```
set CLOUD_ONLY_MODE=1
set NOTRACK_PROXY=http://127.0.0.1:8080
set NOTRACK_REQUIRED=1

:: solo para hybrid
set IMAGE_BACKEND=automatic1111
set AUTOMATIC1111_URL=http://127.0.0.1:7860
set COMFYUI_URL=http://127.0.0.1:8188
set COMFYUI_WORKFLOW=C:\ruta\workflow.json
set SDXL_CHECKPOINT=Realism Engine SDXL
set LORAS_JSON=[{"name":"mi-lora","weight":0.8}]
set IMAGE_QUALITY=ultra
set SEEDANCE_MODEL=seedance-2.5-text-to-video
```

## Artefactos y reproducibilidad

- Workspace: `%LOCALAPPDATA%\VeniceMAGI\workspace`
- Media: `%LOCALAPPDATA%\VeniceMAGI\media`
- Historial: `%LOCALAPPDATA%\VeniceMAGI\historial.db`
- Metadata por render: `archivo.ext.json` junto al artefacto

## Politica de red

- `/proxy`: controla solo la ventana Guest.
- `/notrack`: aplica proxy HTTP compatible a trafico del sistema.
- Cambios de `/proxy` y `/notrack` reinician sesion para aplicar rutas.

## Releases (exe comprimido)

Cada tag `v*.*.*` publica en GitHub Release:

1. `VeniceMAGI-<tag>.zip` (incluye `VeniceMAGI.exe`)
2. `CHECKSUMS.txt` (SHA256)
3. Notas de release en [RELEASE_NOTES.md](C:/Users/D/github-private-review/VeniceMAGI/RELEASE_NOTES.md)

Flujo recomendado:

1. Descargar zip desde Assets.
2. Verificar SHA256 con `CHECKSUMS.txt`.
3. Descomprimir y ejecutar `VeniceMAGI.exe`.

## Desarrollo

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m pytest tests/ -q
.venv\Scripts\pyinstaller VeniceMAGI.spec --noconfirm
```
