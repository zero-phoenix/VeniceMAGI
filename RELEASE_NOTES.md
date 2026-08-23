# VeniceMAGI — Release Windows

## Qué incluye esta release

- `VeniceMAGI-<tag>.zip` con `VeniceMAGI.exe` dentro.
- `CHECKSUMS.txt` con SHA256 de zip y exe.
- Pipeline verificado en CI: tests + compilación + validación de contenido del zip.

## Cambios principales

- Interfaz unificada estilo MAGI (`/magi`, `/salud`, `/galeria`).
- Generación de imagen HQ por `automatic1111` o `comfyui` con control de `--ar`, `--seed`, `--quality`, `--backend`.
- Vídeo solo con Seedance 2.5+ (`/video --duration 10s ...`).
- Integración runtime de notrack (`/notrack`) y preferencias persistentes (`/backend`, `/quality`).
- Modo `cloud-only` por defecto con contenedor virtual local (`/modo cloud|hybrid`).
- Metadata reproducible por render (`*.json`) e índice persistente en SQLite.

## Descarga e instalación

1. Descarga `VeniceMAGI-<tag>.zip` desde Assets.
2. Verifica checksum:
   `certutil -hashfile VeniceMAGI-<tag>.zip SHA256`
3. Compara con `CHECKSUMS.txt`.
4. Descomprime y ejecuta `VeniceMAGI.exe`.

Requisito: Microsoft Edge en Windows.
