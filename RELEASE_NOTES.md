# VeniceMAGI v2.0.0 — ventana propia, IDE sobre tu hardware, puerta aparcada

Fusión de dos líneas de trabajo: la GUI/IDE completa y el modo cloud-only
con pipeline HQ del repo. Todo lo de v1.2.x (cloud-only, backends,
health, notrack) sigue dentro; esto es lo nuevo:

## Ventana de aplicación

Se acabó la consola como única cara: **GUI propia** (pywebview) con el hilo
del enjambre en vivo, workspace con árbol de ficheros y editor, galería de
medios, panel de estado y cola visible. El REPL sigue con `--consola`.

## El navegador, fuera de la vista (sin cerrarlo)

La ventana de Edge es la puerta del Guest sin clave (headless = 403,
medido). v2 la **aparca off-screen**: navegador real, atestación intacta,
cero estorbo. Botón «mostrar puerta» en la GUI.

## Tu hardware, de verdad

`read_file` · `list_dir` · `patch_file` (quirúrgico) · `delete_file`
(papelera + journal) · `hardware_info` (CPU/RAM/GPU/disco) · `run_python`
con plazo · **`shell` solo con tu aprobación clic a clic** en la GUI.

## Vídeo de planos (honesto)

Venice reserva el vídeo AI a Pro: v2 genera los planos como imágenes y
**compone el mp4 en tu PC con ffmpeg** (fundidos incluidos). Planos, no
vídeo AI fluido — y así se llama.

## Ración diaria, visible y bien gastada

Contador de llamadas de hoy + caché LRU: repetir no gasta ración. El cupo
de Venice por IP/día se respeta (sin rotación de IP) y se explica.

---

# VeniceMAGI v1.2.2 - cloud-only guest y README reescrito

## Resumen

Esta release consolida el modo `cloud` por defecto con contenedor virtual local y documentacion completa reescrita para flujo gratuito sin key/login en el camino principal.

## Cambios relevantes

- Modo operativo por defecto: `cloud` (`CLOUD_ONLY_MODE=1`).
- Contenedor virtual local para orquestacion cloud guest.
- Comando `/modo cloud|hybrid` para control explicito.
- Panel MAGI y healthchecks alineados con cloud-only.
- README reescrito de punta a punta con arquitectura, comandos, red y release.

## Assets

- `VeniceMAGI-v1.2.2.zip` con `VeniceMAGI.exe`.
- `CHECKSUMS.txt` con hashes SHA256.

## Instalacion

1. Descarga `VeniceMAGI-v1.2.2.zip` en Releases.
2. Verifica hash:
   `certutil -hashfile VeniceMAGI-v1.2.2.zip SHA256`
3. Compara contra `CHECKSUMS.txt`.
4. Descomprime y ejecuta `VeniceMAGI.exe`.

Requisito: Microsoft Edge en Windows.
