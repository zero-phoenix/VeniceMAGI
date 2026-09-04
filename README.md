# VeniceMAGI

Un IDE con un **enjambre de inteligencias que debaten antes de actuar**
(tesis → antítesis → síntesis), **herramientas reales sobre tu máquina** para
ejecutar lo que deciden, y **anonimato absoluto** en todo el recorrido.

Operación **cloud-first gratuita**: proveedores guest **sin cuenta y sin clave**
en el camino principal, orquestados por un contenedor virtual local.

**[⬇ Descargar para Windows](https://github.com/zero-phoenix/VeniceMAGI/releases/latest)** — un `.zip` con **un único `VeniceMAGI.exe`** dentro. Se descomprime y se ejecuta. Sin instalador, sin Python, sin dependencias.

---

## Los principios del sistema

* **Sin cuenta ni key obligatoria** en modo `cloud`.
* **Anonimato absoluto, en todo sentido.**
* **Transparencia**: si el proveedor guest limita, se informa.
* **Trazabilidad**: cada render guarda metadata reproducible.

Los cuatro son código, no intenciones. `tests/test_venice_guest.py` comprueba
que ningún sitio del camino principal pida credenciales;
`tests/test_ritsuko_vpn.py` comprueba que la salida de red sea **una sola** y
que el modo estricto signifique lo que dice.

### Qué significa exactamente «anonimato absoluto»

No es una postura. Es una lista de cosas concretas que el programa hace y deja
de hacer, cada una con su freno en el código:

1. **Sin cuenta y sin clave.** El camino principal son sitios guest. No hay
   login que filtre quién eres.
2. **Una sola salida de red, para TODO.** Si configuras una VPN o un proxy,
   sale por ahí el tráfico del enjambre, el de la ventana de Edge, el de las
   descargas y el de los subprocesos.
3. **Nada de tráfico partido.** Media aplicación por la VPN y la otra media por
   la línea de casa correlaciona las dos rutas y anula la VPN. Con
   `/vpn estricto on` no se sale por ninguna otra parte: si la salida no está,
   el sistema **no sale**, en vez de caer a tu línea sin avisar.
4. **Sin telemetría.** El programa no manda nada a nadie sobre su uso. Lo que
   se mide se queda en `%LOCALAPPDATA%\VeniceMAGI`.
5. **Sin huella entre sesiones.** `/vpn purgar` borra los perfiles de navegador
   (donde el sitio guarda cookies que te reconocen aunque cambies de IP), la
   caché y los logs.
6. **Credenciales fuera de los informes.** Un proxy con usuario y contraseña se
   enmascara antes de escribirse en ningún fichero.

```
/vpn socks5://127.0.0.1:9050    :: Tor, gratis y sin cuenta
/vpn estricto on                :: sin salida, no se sale
/vpn purgar                     :: borra la huella local
/vpn estado                     :: qué salida hay y qué alcance tiene
```

---

## v2.2.0 — subagentes, percepción, memoria y un automodelo que se puede tumbar

* **Subagentes por familia.** Cuando el encargo tiene partes separables, cada
  nodo abre un frente por parte **en su propia familia y todos a la vez**.
  Medido en el proyecto de origen: tres esperas independientes tardan 1,50 s en
  serie y **0,51 s en abanico**.
* **Opciones de modelo ampliadas.** `/modelos` enumera todo lo que hay sin
  cuenta —guest y g4f, con su capacidad y la fecha de su última medida— y deja
  **fijar la familia de cada nodo en caliente**, sin recompilar ni reiniciar.
* **Percepción.** Oídos (loopback WASAPI: ¿suena? ¿sale entero?) y vista
  (qué hay en pantalla, en qué idioma, qué botón pide).
* **Índice local FTS5.** Buscar en la bitácora, la memoria, los docs y el
  código **sin gastar red ni ración**. Un dato que ya está escrito y se le
  vuelve a preguntar a la nube es cupo tirado.
* **Memoria persistente entre proyectos**: mandos por consola y descartes con
  campo `rescatable`. Un enfoque que pierde deja conocimiento igual que uno que
  gana, y suele dejar más.
* **Automodelo falsable.** Lo que el sistema cree de sí mismo, con la prueba
  que puede tumbarlo — y hoy VeniceMAGI ya declara **cinco afirmaciones
  refutadas** y **cuatro sin comprobar**. Ver `docs/AUTOMODELO.json`.

### Lo de antes, que sigue

* **GUI de aplicación (pywebview)** con hilo del enjambre en vivo, workspace,
  galería y cola de trabajo. `VeniceMAGI.exe` abre la ventana; `--consola`
  mantiene el REPL.
* **Puerta de Edge aparcada fuera de pantalla** por defecto: el navegador real
  sigue resolviendo la atestación, sin estorbar.
* **IDE real**: `read_file`, `list_dir`, `patch_file` quirúrgico, `delete_file`
  a papelera con journal, `hardware_info`, `run_python` con plazo y `shell`
  solo con tu aprobación clic a clic.
* **Taller de arte**: Venice y notrack.ai crean **por separado**, y un tercer
  modelo más estricto comprueba que lo entregado sea lo que pediste.
* **Ración visible**: contador de llamadas de hoy y caché LRU.
* **Vídeo generativo, solo Seedance 2.5+.**

---

## Arquitectura

```
Usuario
  └─ GUI (ventana propia)  ·  REPL (--consola)
      └─ CloudModelContainer (virtual local, sin inferencia local)
          ├─ Venice Guest    (chat + imagen)   ── puerta de Edge propia
          ├─ notrack.ai      (chat)            ── puerta de Edge propia
          └─ Familias g4f    (gemini, command, gpt, claude, razonamiento,
                              grok, perplexity, llama, mistral, deepseek, hf)
                            │
                            └─ TODO sale por la MISMA salida de red (/vpn)
```

El contenedor es virtual y local: no ejecuta inferencia, **decide quién atiende
cada capacidad**. Un proveedor que no hace vídeo figura con `video=False`, y
pedírselo devuelve el motivo al instante en vez de esperar cuatro minutos para
contestar «no apareció en el plazo».

### Los cinco roles

```
NAOKO      clasifica y supervisa       rota entre command / gpt / claude
MELCHIOR   construye        TESIS      venice      + subagentes
BALTHASAR  refuta ejecutando ANTÍTESIS notrack
CASPER     sintetiza        SÍNTESIS   gemini      + subagentes
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
  │  │  │                     ▲                          │
  └──┴──┴─ subagentes         │                          │
     (su familia, a la vez)   │                          │
     ▲                        │                          │
     └── BITÁCORA + ÍNDICE FTS5 + AUTOMODELO + R9 ───────┘
                                                         │
                                                         ▼
                                              RESPUESTA DEFINITIVA (en español)

RITSUKO  ──audita a NAOKO, gobierna la red y firma el anonimato──▶  informes
```

**Cada nodo va anclado a una familia distinta**, y eso no es decoración: si
Melchior propone con el mismo modelo con el que Balthasar refuta, no hay
refutación, hay eco. `/modelos` te deja cambiarlo, y **se niega** a poner dos
nodos en la misma familia — porque el sistema seguiría respondiendo, peor, sin
dar un solo error.

---

## Subagentes: un nodo, varios frentes

Un nodo es un solo hilo de pensamiento. Cuando el encargo tiene tres partes
separables, las aborda en fila y las últimas salen peor porque llegan con el
contexto gastado. Y mientras tanto los ocho núcleos están parados: el enjambre
espera respuestas de **red**, no de CPU.

`subagentes.py` abre un frente por parte, todos a la vez:

* **En su propia familia**, no repartidos entre varias. Si los subagentes de
  Melchior salieran por la familia de Balthasar, la tesis llegaría contaminada
  con el sesgo de quien tiene que refutarla. La diversidad está *entre* nodos;
  dentro de un nodo, la coherencia vale más.
* **El troceo es determinista** y no lo decide un modelo — cuesta una llamada
  de la ración averiguar cómo gastar la ración, y con un troceo que cambia
  entre corridas idénticas la compuerta de la fase no se puede medir.
* **Lo que no se cubrió, se dice.** Un texto fundido sin costuras esconde
  justo el frente que falló.
* **Balthasar no abre subagentes**, a propósito: su turno ya es redundante por
  diseño (varios ejes de refutación en paralelo), y abrirle un abanico encima
  sería pagar dos veces la misma redundancia.

**Compuerta:** el abanico deja medido su ahorro (`ms_abanico` contra
`ms_si_fuera_en_serie`). Si no sale positivo de forma sostenida, el mecanismo
se retira y se dice.

---

## `/modelos`: qué hay sin cuenta, y quién usa qué

```
/modelos                     inventario completo + reparto actual
/modelos CASPER command      fija la familia de un nodo, en caliente
/modelos CASPER auto         la suelta y vuelve a mandar el catálogo
```

Naoko y Ritsuko **no se pueden tocar desde aquí**: Naoko rota a propósito según
la petición, y Ritsuko tiene prohibidas las familias que audita. Ofrecer un
mando que rompe una garantía es peor que no ofrecerlo.

---

## El taller de arte: dos autores, un crítico

Pedirle una imagen a un modelo y quedarse con lo que salga tiene dos fallos que
no se ven hasta que se miran juntos. Un solo autor no tiene con quién
contrastar. Y nadie comprueba que lo entregado sea lo pedido — «salió una
imagen» se confunde con «salió LA imagen».

1. **El encargo se vuelve contrato.** «Un dragón rojo, de noche, sobre una
   montaña nevada» son cuatro promesas separables, no un tema.
2. **Dos autores, en paralelo y sin verse.** Venice y notrack.ai reciben el
   mismo encargo y cada uno redacta su propia lectura y su propio prompt.
3. **Un crítico más estricto, en una tercera familia.** Cuenta promesas
   cumplidas contra el contrato. Ante la duda, INCUMPLE.
4. **Reintento dirigido**, con la lista concreta de promesas incumplidas.

**Lo que el taller no finge.** notrack.ai **no genera imágenes**: es un chat.
Entra como autor de pleno derecho y el pincel lo pone Venice. Y los modelos
guest **no tienen visión**: el crítico separa lo que **mide una máquina** de lo
que juzga leyendo, y declara lo que **no ha podido verificar** en vez de
aprobarlo por omisión. Cuando la máquina y el modelo discrepan, **manda la
máquina**.

---

## Ritsuko: quien revisa a la revisora

Naoko corrige a los tres nodos. Nadie corregía a Naoko — y eso no es teórico:
la auditoría del 20 de agosto la encontró declarando «deriva del modelo» en dos
familias enteras justo después de una tarea que había agotado la cuota de esos
mismos proveedores. Estaba midiendo su propia interferencia y llamándola avería.

* **Solo mira.** No escribe código, no cancela tareas, no toca el reparto.
* **Familia propia**, que no comparte con ninguna de las cinco que audita —
  `venice` y `notrack` incluidas.
* **Gobierna la salida de red** del sistema entero.
* **Audita el anonimato** (`anonimato()`): enumera las fugas reales.
* **Inventaría proveedores y ración**.
* **Informes descargables** en `%LOCALAPPDATA%\VeniceMAGI\informes-ritsuko`.

---

## Lo que el sistema sabe que NO sabe hacer

`docs/AUTOMODELO.json` — cada afirmación con la prueba que la tumbaría. Hoy:

| Estado | Afirmación |
|---|---|
| **refutada** | Una sonda mide la salud de un sitio guest *(exige abrir navegador: colgó el CI 124 s)* |
| **refutada** | El crítico del taller puede juzgar lo que se ve en la imagen |
| **refutada** | El vídeo generativo funciona en modo cloud |
| **refutada** | El prompt llega entero al proveedor guest *(se corta en 7000 caracteres)* |
| **sin comprobar** | El chat guest de Venice / de notrack.ai responde de verdad |
| **sin comprobar** | El taller de arte entrega de extremo a extremo |
| sostenida | Se compila un único exe onefile y se publica en Release |
| sostenida | La salida de red del sistema es una sola para todas las capas |

**«Sin comprobar» no es «no funciona».** Es que nadie lo ha puesto a prueba
todavía, y decirlo es más útil que inventar un veredicto.

---

## Modos operativos

**`cloud`** (por defecto) — `CLOUD_ONLY_MODE=1`. Chat e imagen vía proveedor
guest. Sin modelos locales. Sin key/login en el camino principal. Vídeo
generativo solo con Seedance 2.5+.

**`hybrid`** (opcional) — backends locales de imagen (`automatic1111`,
`comfyui`). Se activa con `/modo hybrid`.

---

## Comandos

```
/magi                          /salud
/modelos [NODO FAMILIA|auto]   /modo cloud|hybrid
/imagen [--ar 16:9] [--seed N] [--quality draft|standard|ultra] PROMPT
/video [--duration 10s] PROMPT            (solo Seedance 2.5+)
/vpn URL|off|estado|estricto on|off|purgar
/notrack show|off|URL          /proxy URL|off
/backend [automatic1111|comfyui]          /quality [draft|standard|ultra]
/sesion   /historial [n]   /galeria [n]   /ayuda   /salir
```

## Configuración de entorno

```
set CLOUD_ONLY_MODE=1
set RITSUKO_VPN=socks5://127.0.0.1:9050
set RITSUKO_VPN_ESTRICTA=1
set VENICEMAGI_SIN_PUERTA=1          :: no abre la ventana de Edge (CI, tests)

:: solo para hybrid
set IMAGE_BACKEND=automatic1111
set AUTOMATIC1111_URL=http://127.0.0.1:7860
set COMFYUI_URL=http://127.0.0.1:8188
set SDXL_CHECKPOINT=Realism Engine SDXL
set LORAS_JSON=[{"name":"mi-lora","weight":0.8}]
set SEEDANCE_MODEL=seedance-2.5-text-to-video
```

---

## Qué sabe hacer

El enjambre tiene **68 herramientas** reales sobre tu máquina, repartidas por
rol y acotadas por dominio antes de entrar al prompt.

* **Ingeniería de software**: crear, modificar y ejecutar código, empaquetar a
  `.exe` portable.
* **Ingeniería inversa y emuladores**: desensamblado (Capstone), emulación
  (Unicorn), entropía de Shannon por regiones.
* **Percepción**: oír si un artefacto suena y clasificar qué hay en pantalla.
* **Memoria**: búsqueda FTS5 local sobre bitácora, docs y código.
* **Rondas de optimización verificadas**: bitácora acumulativa inyectada al
  prompt, corridas con capturas (imagen + movimiento + sonido), dos contadores
  de FPS distinguibles.
* **Fábrica de artefactos que se mira a sí misma**: especificar → generar →
  ejecutar/renderizar → **observar** → criticar → iterar.
* **Mundo real**: macro, geopolítica y finanzas con fuentes gratuitas y sin
  clave (FRED, BCE, Banco Mundial, SEC EDGAR).

---

## Reversibilidad y parada

* **Deshacer.** Antes de tocar un fichero se copia. `undo` lo devuelve, por
  operación o por tarea entera. `delete_file` va a papelera con journal.
* **Parar.** `PARAR ESTA` cancela una conversación; `PARAR TODO` es la parada
  de emergencia, con informe de lo que paró **de verdad**.

La misma copia alimenta el **panel de aprobación**: qué ficheros toca el
cambio, el diff real, las órdenes que se ejecutarán y si los tests pasaron.

## Artefactos

* Workspace: `%LOCALAPPDATA%\VeniceMAGI\workspace`
* Media: `%LOCALAPPDATA%\VeniceMAGI\media`
* Historial: `%LOCALAPPDATA%\VeniceMAGI\historial.db`
* Metadata por render: `archivo.ext.json` junto al artefacto — con el contrato,
  las dos lecturas de los autores, lo que midió la máquina y el veredicto.

---

## Instalación

### Binario para Windows (recomendado)

1. Abre **[Releases](https://github.com/zero-phoenix/VeniceMAGI/releases/latest)**
   y descarga **`VeniceMAGI-<versión>.zip`** de **Assets**.
2. Verifica (opcional): `certutil -hashfile VeniceMAGI-<versión>.zip SHA256`
   contra **`CHECKSUMS.txt`**.
3. Descomprime donde quieras. Dentro hay **un solo fichero**: `VeniceMAGI.exe`.
4. Ejecútalo.

SmartScreen avisará porque el binario no está firmado: *Más información →
Ejecutar de todas formas*. Va en `.zip` a propósito: Windows y muchos
navegadores bloquean un `.exe` descargado suelto. Lo compila **GitHub
Actions** desde el tag, tras pasar la suite completa.

El `.exe` es **onefile y lleva su propio Python 3.10 dentro**. **Hace falta
Microsoft Edge** para el camino guest: es lo único que resuelve la atestación
de cliente de Venice (medido: Chromium headless recibe 403; el Edge real, 200).

### Desde el código

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt -r requirements-dev.txt
.venv\Scripts\python -m pytest tests/ -q
.venv\Scripts\pyinstaller VeniceMAGI.spec --noconfirm
```

Opcionales, detectados si están: `capstone` y `unicorn` (ingeniería inversa),
`pygame` y `pillow` (**sin Pillow el taller de arte no aprueba nada**, lo
declara como no verificado), `ffmpeg` (vídeo y **medidor de estilo**),
`opencv-python-headless` (**escala de plano**), ComfyUI en `127.0.0.1:8188`.
Sin ellos el sistema funciona y **avisa de lo que no puede hacer**.

### El cascarón local

Lo único que corre en tu tarjeta, y es a propósito lo más pequeño posible. No
genera: **percibe**. Hace lo que ningún proveedor guest puede hacer, porque
ninguno acepta imágenes de entrada.

```
opencv-python-headless          escala de plano                 pip install
face_detection_yunet (230 KB)   detector                        opencv_zoo
face_recognition_sface (37 MB)  continuidad de personaje        opencv_zoo
```

Los dos modelos van en `%LOCALAPPDATA%\VeniceMAGI\modelos`. `cascaron_estado`
dice cuáles faltan, cuánto pesan y de dónde salen. **No se descargan solos**:
bajar ficheros sin que nadie lo haya pedido rompería la promesa de una sola
salida de red.

Sin ellos, la escala de plano sale como **SIN MEDIR** — que no es lo mismo que
«plano general», y confundir las dos cosas aprobaría un corte de primeros
planos contra una biblia de planos generales sin que nadie hubiera mirado una
sola imagen.

---

## Cómo está construido esto

Cada regla nació de un fallo real:

1. **Todo cambio se conecta o se borra.** Nunca se añade sin conectar.
2. **Un test sobre una pieza aislada no prueba que el sistema la use.**
3. **Cada capacidad tiene que poder invocarse desde la interfaz**, y con el
   nombre que el README promete.
4. **Arrancar encuentra fallos que leer no encuentra.**
5. **«No he podido comprobarlo» no es «está bien».** Sin Pillow, el observador
   devolvía «correcto» sobre una captura que nunca llegó a abrir.
6. **El binario publicado no es el mismo programa que el de desarrollo.**
7. **Arreglar algo no es lo mismo que arreglarlo donde importa.**
8. **Lo que abre un navegador no se sondea.** Una sonda que lanza un Edge real
   cuesta segundos, gasta ración y —medido— cuelga el CI 124 s hasta morir con
   un `Timeout` sin diagnóstico.
9. **Los trinquetes bajan, no suben.** Cuando el conteo de huérfanos supera el
   techo, se conecta, se adelgaza o se borra. Nunca se sube el número.
10. **Se escribe con Python, `newline='\n'` y sin BOM.** PowerShell mete BOM y
    ya rompió un módulo con un `SyntaxError` que no señalaba a ninguna línea.

**Más de 1700 tests en Python · sin tests verdes no hay release.**

Y esa regla no depende del CI. Lo mismo que ejecuta GitHub Actions se ejecuta
aquí, con los mismos comandos:

```
python scripts/verificar.py            # lo de cada push
python scripts/verificar.py --todo     # + los que compilan un .exe
```

O pieza a pieza, si quieres ver dónde falla:

```
python -m ruff check vmagi/ tests/    # ruff 0.16.5, fijado en requirements-dev
python scripts/huerfanos.py --conteo  # techo 88
python -m pytest tests/ -q            # la compuerta entera
```
