# VeniceMAGI

Una variante MAGI con **operación cloud-first gratuita**: usa proveedores guest
**sin key y sin login** en el camino principal, y mantiene una **arquitectura de
contenedor virtual local** para orquestar capacidades.

Un enjambre de tres inteligencias que aplican el método dialéctico
(tesis → antítesis → síntesis), **herramientas reales sobre tu máquina** para
ejecutar lo que deciden, una supervisora que los corrige y una auditora que la
revisa a ella. Y una regla que lo atraviesa todo: **una afirmación sin evidencia
verificada no es una afirmación**.

**[⬇ Descargar la última versión para Windows](https://github.com/zero-phoenix/VeniceMAGI/releases/latest)** — un `.zip`, se descomprime y se ejecuta. Sin instalador.

---

## v2.0.0 — ventana propia e IDE sobre tu hardware

* **GUI de aplicación (pywebview)**: hilo del enjambre en vivo (Melchior,
  Balthasar, Casper, Naoko), workspace con árbol y editor, galería de medios,
  estado y cola de trabajo. `VeniceMAGI.exe` abre la ventana; `--consola`
  mantiene el REPL.
* **Puerta de Edge aparcada fuera de pantalla** por defecto (toggle en la GUI):
  el navegador real sigue resolviendo la atestación, sin estorbar.
* **IDE real**: `read_file`, `list_dir`, `patch_file` quirúrgico, `delete_file` a
  papelera con journal, `hardware_info` (CPU/RAM/GPU/disco), `run_python` con
  plazo y `shell` solo con tu aprobación clic a clic.
* **Vídeo de planos**: planos como imágenes Venice + mp4 compuesto EN TU PC con
  ffmpeg (honesto: planos con fundidos, no vídeo AI fluido).
* **Ración visible**: contador de llamadas de hoy y caché LRU para que repetir
  no gaste cupo.
* **Taller de arte**: Venice y notrack.ai crean por separado, y un tercer modelo
  más estricto comprueba que lo entregado es lo que pediste.
* **Ritsuko**: la quinta IA, que supervisa a la supervisora, con su propia
  salida de red.

---

## Principios del sistema

* **Sin cuenta ni key obligatoria** en modo `cloud`.
* **Sin evasión de cuotas**: no hay rotación automática de IP ni de VPN.
* **Transparencia**: si el proveedor guest limita, se informa.
* **Trazabilidad**: cada render guarda metadata reproducible.

Los cuatro son código, no intenciones. `tests/test_venice_guest.py` comprueba
que ningún sitio del camino principal pida credenciales;
`tests/test_ritsuko_vpn.py` comprueba que la salida de red **se niegue** a
cambiar cuando el motivo huele a cuota, límite o bloqueo.

---

## Arquitectura actual

```
Usuario
  └─ REPL MAGI / GUI  (/magi, /salud, /imagen, /video, /vpn, ...)
      └─ CloudModelContainer (virtual local, sin inferencia local)
          ├─ Venice Guest    (chat + imagen)   ── puerta de Edge propia
          ├─ notrack.ai      (chat)            ── puerta de Edge propia
          └─ Familias g4f    (gemini, command, gpt, ...) — sin clave, por HTTP
```

El contenedor es virtual y local: no ejecuta inferencia, **decide quién atiende
cada capacidad**. Un proveedor que no hace vídeo figura con `video=False`, y
pedírselo devuelve el motivo al instante en vez de esperar cuatro minutos para
contestar «no apareció en el plazo».

### Los cinco roles

```
NAOKO      clasifica y supervisa       rota entre command / gpt / claude
MELCHIOR   construye        TESIS      venice
BALTHASAR  refuta ejecutando ANTÍTESIS notrack
CASPER     sintetiza        SÍNTESIS   gemini
RITSUKO    audita a Naoko              razonamiento / grok / perplexity
```

```
TU PETICIÓN
    │
    ▼
NAOKO elige el estilo
    │
    ▼
MELCHIOR  ──TESIS────▶  BALTHASAR  ──ANTÍTESIS────▶  CASPER
(construye)            (refuta con evidencia)       (SÍNTESIS al usuario)
     ▲                        ▲                          │
     └──── BITÁCORA + PROTOCOLO R9 + HERRAMIENTAS ───────┘
                                                         │
                                                         ▼
                                              RESPUESTA DEFINITIVA (en español)

RITSUKO  ──audita a NAOKO y su relación con los tres──▶  informes y megaplanes
(no toca nada: solo informa, en su propia pestaña, por su propia salida de red)
```

**Cada nodo va anclado a una familia distinta**, y eso no es decoración: si
Melchior propone con el mismo modelo con el que Balthasar refuta, no hay
refutación, hay eco. La interfaz muestra siempre la familia que **de verdad**
respondió.

---

## El taller de arte: dos autores, un crítico

Pedirle una imagen a un modelo y quedarse con lo que salga tiene dos fallos que
no se ven hasta que se miran juntos. Un solo autor no tiene con quién
contrastar: si entiende mal el encargo, el resultado es coherente consigo mismo
y nada lo delata. Y nadie comprueba que lo entregado sea lo pedido — «salió una
imagen» se confunde con «salió LA imagen».

`/imagen` no llama a un modelo. Abre un taller:

1. **El encargo se vuelve contrato.** «Un dragón rojo, de noche, sobre una
   montaña nevada» son cuatro promesas separables, no un tema. Se enumeran al
   empezar y se cuentan al final.
2. **Dos autores, en paralelo y sin verse.** Venice y notrack.ai reciben el
   mismo encargo y cada uno redacta su propia lectura y su propio prompt. Que
   sean familias distintas es lo que hace que la discrepancia signifique algo.
3. **Un crítico más estricto, en una tercera familia.** No crea nada. Cuenta
   promesas cumplidas contra el contrato, y su sesgo por diseño es el contrario
   del de un autor: donde el autor quiere entregar, el crítico quiere encontrar
   el fallo. Ante la duda, INCUMPLE.
4. **Reintento dirigido.** Un veredicto negativo no manda «hazlo mejor»: manda
   la lista concreta de promesas incumplidas.

**Lo que el taller no finge.** notrack.ai **no genera imágenes**: es un chat.
Entra como autor de pleno derecho —redacta su lectura y su prompt, en paralelo y
sin ver al otro— y el pincel lo pone Venice, o el backend local en `hybrid`.
Y los modelos guest **no tienen visión**: no pueden mirar el PNG. Por eso el
crítico separa lo que **mide una máquina** (existe, abre, dimensiones,
proporción, entropía) de lo que juzga leyendo, y declara explícitamente lo que
**no ha podido verificar** en vez de aprobarlo por omisión.

Y cuando la máquina y el modelo discrepan, **manda la máquina**: un criterio
medible que salió falso queda incumplido aunque el crítico lo apruebe. El sesgo
de complacencia existe; aquí hay un número que lo desmiente.

---

## Ritsuko: quien revisa a la revisora

Naoko corrige a los tres nodos: detecta deriva, reordena el reparto, aplica
mejoras. Nadie corregía a Naoko — y eso no es teórico. La auditoría del 20 de
agosto la encontró declarando «deriva del modelo» en dos familias enteras justo
después de una tarea que había agotado la cuota de esos mismos proveedores.
Estaba midiendo su propia interferencia y llamándola avería.

* **Solo informa.** No escribe código, no cancela tareas, no toca el reparto. Un
  auditor con permiso para aplicar cambios acaba revisándose a sí mismo.
* **Familia propia.** Corre en una familia que **no comparte con ninguna** de
  las cinco que audita — `venice` y `notrack` incluidas. Un auditor que se cae
  cuando se cae el auditado no sirve justo el día que hace falta.
* **Salida de red propia** (`/vpn`). Ver abajo.
* **Informes descargables** con la evidencia que los sostiene, en
  `%LOCALAPPDATA%\VeniceMAGI\informes-ritsuko`.
* Habla español o inglés, nunca otro idioma.

### La VPN de Ritsuko, y la línea que no cruza

Ritsuko puede salir a la red por su propia puerta: VPN gratuita, Tor o un proxy
HTTP/SOCKS. El motivo es el mismo por el que usa otra familia de modelo: Venice
y notrack racionan **por IP y por día**, así que una auditora que sale por la
misma IP que el enjambre se queda muda en el instante exacto en que una tarea
agota el cupo — que es justo cuando hace falta un veredicto independiente.

Y aquí está la línea. Una salida separada es compatible con «sin evasión de
cuotas»; **rotarla cuando el proveedor dice «hoy no» no lo es**. Eso sería
burlar la ración de quien nos da el servicio gratis.

La diferencia no se deja a la buena voluntad de quien llame:

1. La salida se **configura a mano** (`RITSUKO_VPN`, `config.json` o `/vpn`). El
   sistema nunca la elige ni la descubre solo.
2. `rota_por(motivo)` **rechaza** cualquier motivo que contenga cuota, cupo,
   ración, `429`, *rate limit*, límite, bloqueo, ban, captcha, atestación o
   `403` — y deja el intento apuntado en un registro que el informe publica.
   No hay parámetro que lo desactive, y un test lo comprueba inspeccionando la
   firma.
3. La salida es **de Ritsuko**: no se aplica al enjambre, ni a la puerta de
   Edge, ni al tráfico general. Aplicarla a todos convertiría una medida de
   independencia en una de evasión.

```
set RITSUKO_VPN=socks5://127.0.0.1:9050     :: Tor, gratis
set RITSUKO_VPN=http://127.0.0.1:8080       :: tu proxy
```

No hay listas de proxies públicos gratuitos embebidas, y es deliberado: son
inestables, a menudo hostiles, y una lista que rota sola es la rotación
automática por la puerta de atrás.

---

## Modos operativos

### 1) `cloud` (por defecto)

* `CLOUD_ONLY_MODE=1`
* Chat e imagen vía proveedor guest cloud.
* Sin modelos locales de inferencia.
* Sin key/login en el camino principal.
* Vídeo depende de la capacidad guest disponible — hoy, ninguna la declara, y
  se dice.

### 2) `hybrid` (opcional)

* Permite backends locales de imagen (`automatic1111` / `comfyui`) y rutas
  adicionales.
* Se activa con `/modo hybrid`.

---

## Comandos principales

```
/magi
/salud
/modo cloud|hybrid
/imagen [--ar 16:9] [--seed N] [--quality draft|standard|ultra] [--backend automatic1111|comfyui] PROMPT
/video [--duration 10s] PROMPT
/backend [automatic1111|comfyui]
/quality [draft|standard|ultra]
/vpn URL|off|estado
/notrack show|off|URL|required on|required off
/proxy URL|off
/sesion
/historial [n]
/galeria [n]
/ayuda
/salir
```

---

## Configuración de entorno

```
set CLOUD_ONLY_MODE=1
set NOTRACK_PROXY=http://127.0.0.1:8080
set NOTRACK_REQUIRED=1
set RITSUKO_VPN=socks5://127.0.0.1:9050

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

---

## Qué sabe hacer

Más allá de debatir, el enjambre tiene **56 herramientas** reales sobre tu
máquina, repartidas por rol y acotadas por dominio antes de entrar al prompt.

* **Ingeniería de software**: crear, modificar y ejecutar código, construir
  proyectos, empaquetar a `.exe` portable.
* **Ingeniería inversa y emuladores**: desensamblado (Capstone), emulación
  (Unicorn), entropía de Shannon por regiones.
* **Rondas de optimización verificadas**: bitácora acumulativa inyectada al
  prompt, protocolo de corrida con capturas (imagen + movimiento), dos
  contadores de FPS distinguibles y un harness que lanza el emulador sin manos.
* **Fábrica de artefactos que se mira a sí misma**: especificar → generar →
  ejecutar/renderizar → **observar** → criticar → iterar.
* **Vídeo programático**: animática Ken Burns, manga → vídeo en vertical, con
  detección de fotogramas en negro o congelados.
* **Mundo real**: macro, geopolítica y finanzas con fuentes gratuitas y sin
  clave (FRED, BCE, Banco Mundial, SEC EDGAR). Un dato no se construye sin
  fuente y fecha.

---

## Reversibilidad y parada

El acceso sin restricciones a tu máquina se sostiene sobre dos salidas:

* **Deshacer.** Antes de tocar un fichero se copia. `undo` lo devuelve, por
  operación o por tarea entera. `delete_file` va a papelera con journal.
* **Parar.** `PARAR ESTA` cancela una conversación; `PARAR TODO` es la parada de
  emergencia. `SIGTERM` primero, `SIGKILL` solo si no atienden, con informe de
  lo que paró **de verdad**.

La misma copia que da la reversibilidad alimenta el **panel de aprobación**: qué
ficheros toca el cambio, su contenido antes y después con un diff real, las
órdenes que se ejecutarán y si los tests pasaron.

---

## Artefactos y reproducibilidad

* Workspace: `%LOCALAPPDATA%\VeniceMAGI\workspace`
* Media: `%LOCALAPPDATA%\VeniceMAGI\media`
* Historial: `%LOCALAPPDATA%\VeniceMAGI\historial.db`
* Informes de Ritsuko: `%LOCALAPPDATA%\VeniceMAGI\informes-ritsuko`
* Metadata por render: `archivo.ext.json` junto al artefacto — con el contrato,
  las dos lecturas de los autores, el prompt usado, lo que midió la máquina y el
  veredicto del crítico.

## Política de red

* `/proxy`: controla solo la ventana Guest.
* `/notrack`: aplica proxy HTTP compatible a tráfico del sistema.
* `/vpn`: la salida propia de Ritsuko, y solo la suya.
* Cambios de `/proxy` y `/notrack` reinician sesión para aplicar rutas.

---

## Instalación

### Binario para Windows (recomendado)

1. En **Assets**, descarga **`VeniceMAGI-<tag>.zip`**.
2. Verifica la descarga (opcional):
   `certutil -hashfile VeniceMAGI-<tag>.zip SHA256` contra **`CHECKSUMS.txt`**.
3. Descomprímelo donde quieras — no hay instalador ni carpetas obligatorias.
4. Ejecuta **`VeniceMAGI.exe`**.

Windows SmartScreen avisará porque el binario no está firmado: *Más información
→ Ejecutar de todas formas*.

Va en `.zip` a propósito: Windows y muchos navegadores bloquean o marcan un
`.exe` descargado suelto. Lo compila **GitHub Actions** desde el tag, tras pasar
la suite completa de tests; no hay ninguna subida manual de por medio.

**Hace falta Microsoft Edge instalado**: la puerta usa el Edge real de la
máquina, porque es lo único que resuelve la atestación de cliente de Venice
(medido: Chromium headless recibe 403; el Edge de la máquina recibe 200).

### Desarrollo

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m pytest tests/ -q
.venv\Scripts\pyinstaller VeniceMAGI.spec --noconfirm
```

Opcionales, detectados si están: `capstone` y `unicorn` (ingeniería inversa),
`pygame` y `pillow` (observar juegos e imágenes — **sin Pillow el taller de arte
no aprueba nada**, lo declara como no verificado), `ffmpeg` (vídeo), ComfyUI en
`127.0.0.1:8188` (dibujo). Sin ellos el sistema funciona y **avisa de lo que no
puede hacer**, en vez de fingir.

---

## Releases

Cada tag `v*.*.*` publica en GitHub Release:

1. `VeniceMAGI-<tag>.zip` (incluye `VeniceMAGI.exe`)
2. `CHECKSUMS.txt` (SHA256)
3. Notas de release en `RELEASE_NOTES.md`

---

## Cómo está construido esto

Cada regla nació de un fallo real:

1. **Todo cambio se conecta o se borra.** Nunca se añade sin conectar.
2. **Un test sobre una pieza aislada no prueba que el sistema la use.**
3. **Cada capacidad del backend tiene que poder invocarse desde la interfaz.**
   Y con el nombre que el README promete: si la documentación dice `patch_file`,
   `patch_file` existe.
4. **Arrancar encuentra fallos que leer no encuentra.**
5. **«No he podido comprobarlo» no es «está bien».** Sin Pillow, el observador
   de imágenes devolvía «correcto» sobre una captura que nunca llegó a abrir.
6. **El binario publicado no es el mismo programa que el de desarrollo.**
7. **Arreglar algo no es lo mismo que arreglarlo donde importa.**

**Más de 1550 tests en Python · sin tests verdes no hay release.**

Lo mismo que ejecuta GitHub Actions se ejecuta aquí, con los mismos comandos:

```
python scripts/verificar.py            # lo de cada push
python scripts/verificar.py --todo     # + los que compilan un .exe
```
