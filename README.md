# VeniceMAGI

La variante de MAGI donde **la única IA es [Venice](https://venice.ai)** —
**sin cuenta, sin clave, sin login**: el modo Guest de la web, manejado por
el enjambre.

```
TU PETICIÓN → NAOKO clasifica (Venice)
            → MELCHIOR construye (Venice): ficheros, código, imagen
            → BALTHASAR refuta EJECUTANDO lo construido (Venice)
            → CASPER sintetiza y entrega (Venice)
```

Venice es tesis, antítesis y síntesis a la vez: mismo motor, tres contratos
que se confrontan con evidencia ejecutada.

## Cómo funciona (y por qué la ventana de Edge)

Verificado endpoint a endpoint el 2026-08-16: la API oficial exige clave,
el flujo anónimo legacy está muerto y el FAPI de Clerk pide Turnstile. La
única vía sin credenciales es la que usa tu navegador: **el Guest de la
web**. Y outerface solo atiende al Guest desde un navegador REAL (con
Chromium headless responde 403 por la atestación de cliente).

Por eso VeniceMAGI abre una **ventana de Edge** (el Edge de tu máquina,
perfil propio, nunca tu perfil personal): es literalmente Venice Guest en
tu pantalla, operado por el enjambre. Ahí se escriben los prompts y se
recogen las respuestas e imágenes.

## Lo que puede y lo que no — dicho claro

| Capacidad | Estado |
|---|---|
| Chat (todo el enjambre) | ✅ Guest, verificado E2E |
| Crear ficheros y ejecutar código | ✅ local, sin Venice |
| **Imagen** | ✅ pipeline HQ por backend `automatic1111` o `comfyui` |
| **Vídeo** | ✅ solo Seedance 2.5+ (requiere `VENICE_API_KEY`) |
| Cupo | El Guest tiene ración **diaria por IP**. Agotada, Venice pide login: el sistema lo dice y no se esquiva |

«Sin raciones nuestras» significa que VeniceMAGI no añade ningún límite
encima de los de Venice; los de Venice se respetan y se explican.

## Tu propia VPN o proxy (opcional)

Si usas una VPN o un proxy en tu máquina, puedes enrutar por él **solo la
ventana del Guest**:

```
/proxy socks5://127.0.0.1:9050     # o http://host:puerto
/proxy off                          # volver a tu red normal
```

Es tu red y tu privacidad, y ahí se queda: VeniceMAGI no instala VPNs, no
rota IPs y no reconecta al agotarse el cupo — la ración diaria del servicio
gratuito se respeta y se explica. Eludirla con rotación de IP te expone a
que Venice bloquee el rango entero de tu proveedor.

Además, para tráfico HTTP compatible, VeniceMAGI puede enrutar por
**notrack.ai** con:

```
set NOTRACK_PROXY=http://127.0.0.1:8080
set NOTRACK_REQUIRED=1
```

## Uso

```
VeniceMAGI.exe
crea un script que ordene una carpeta por extensiones     → ronda completa
/imagen --ar 16:9 --seed 42 --quality ultra una catedral gótica al amanecer
/modo cloud
/video --duration 10s vuelo cinemático sobre venecia
/modo hybrid
/backend automatic1111
/quality ultra
/notrack http://127.0.0.1:8080
/notrack required on
/sesion                                                   → renueva el Guest
/magi  /salud  /estado  /historial  /galeria  /refs  /ayuda  /salir
```

Variables clave para imagen/vídeo:

```
set CLOUD_ONLY_MODE=1                        # por defecto: solo cloud guest
set IMAGE_BACKEND=automatic1111              # solo si usas /modo hybrid
set AUTOMATIC1111_URL=http://127.0.0.1:7860
set COMFYUI_URL=http://127.0.0.1:8188
set COMFYUI_WORKFLOW=C:\ruta\workflow.json
set SDXL_CHECKPOINT=Realism Engine SDXL
set LORAS_JSON=[{"name":"mi-lora","weight":0.8}]
set IMAGE_QUALITY=ultra                      # draft|standard|ultra
set SEEDANCE_MODEL=seedance-2.5-text-to-video # solo si usas /modo hybrid
```

Cada render guarda metadata reproducible en sidecar `*.json` junto al artefacto.
Al cambiar `/notrack` el sistema cierra la puerta actual y aplica la nueva ruta en la siguiente sesión.
En `cloud-only` no se usan modelos locales ni claves API: el contenedor virtual enruta a proveedores guest permitidos.

## Release (descarga del exe comprimido)

En cada tag `v*.*.*`, GitHub Actions:
1. Ejecuta tests.
2. Compila `VeniceMAGI.exe`.
3. Crea `VeniceMAGI-<tag>.zip` (con el exe dentro).
4. Publica `CHECKSUMS.txt`.

Descarga el zip en Releases y descomprímelo para usar el exe.

- Artefactos: `%LOCALAPPDATA%\VeniceMAGI\workspace` y `...\media`.
- Requisito: **Microsoft Edge** instalado (estándar en Windows).
- Si la sesión Guest caduca a mitad de operación, el sistema reentra solo
  y repite tu petición.

## Desarrollo

```
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m pytest tests/ -q        # tests offline
.venv\Scripts\pyinstaller VeniceMAGI.spec --noconfirm
```

Proyecto independiente de MAGI System IDE. Local y privado: nada de GitHub.
