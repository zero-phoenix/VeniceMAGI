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
