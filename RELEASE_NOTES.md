# v2.0.0 — el enjambre completo sobre proveedores guest, y un taller que comprueba

**Qué cambia:** VeniceMAGI pasa de un REPL de 3 000 líneas sobre un único
proveedor a la arquitectura completa de MAGI — enjambre dialéctico con
herramientas reales, GUI propia, supervisión y auditoría — **sin perder la
promesa que le da nombre**: cloud-first, sin cuenta y sin clave en el camino
principal.

## Lo concreto

### Multi-familia guest, sin key ni login

- **Dos sitios guest operados por navegador**: `venice` (chat + imagen) y
  `notrack` (chat). Ninguno pide cuenta. Se operan desde el Edge real de la
  máquina, que es lo único que resuelve la atestación de cliente de Venice
  (medido: Chromium headless → 403; Edge de la máquina → 200).
- **Reparto del enjambre rehecho**: `MELCHIOR=venice`, `BALTHASAR=notrack`,
  `CASPER=gemini`. Tres familias distintas, ninguna con clave. Melchior
  construye con el único guest que además pinta; Balthasar refuta con un modelo
  independiente —un refutador que comparte modelo con el proponente devuelve el
  eco de su propia tesis—; Casper sintetiza por HTTP, sin navegador de por
  medio, porque es quien te habla y su latencia se nota en cada respuesta.
- **Un sitio nuevo es una fila, no un refactor**: `vmagi/venice/sitios.py`
  declara URL, entrada de invitado, marcas de modal, marcas de cupo y
  capacidades. La puerta es la misma para todos y no sabe de ninguno.

### El taller de arte: dos autores separados y un crítico estricto

`/imagen` ya no llama a un modelo:

- El encargo se **trocea en promesas separables** antes de empezar. Los
  criterios medibles (existe, abre, proporción, no está en blanco) los decide
  una máquina, no un modelo.
- **Venice y notrack redactan su lectura y su prompt en paralelo, sin verse.**
  El paralelismo es la separación, no la velocidad: encadenarlos haría que el
  segundo viera por dónde tiró el primero.
- **Un crítico en una tercera familia** cuenta promesas cumplidas contra el
  contrato. Ante la duda, INCUMPLE.
- **La máquina manda sobre el modelo**: un criterio medible que salió falso
  queda incumplido aunque el crítico lo apruebe.
- **El reintento es dirigido**: la segunda pasada recibe la lista concreta de
  promesas incumplidas, no un «hazlo mejor».
- **Sin Pillow no se aprueba nada**: lo no medible sale como `no_verificable`,
  nunca como cumplido.

### Ritsuko, con salida de red propia

- Entra la quinta IA completa: audita a Naoko, **solo informa**, y su familia no
  se comparte con ninguna de las cinco auditadas — ahora `venice` y `notrack`
  están en `FAMILIAS_AUDITADAS`, así que tampoco puede caer ahí.
- **VPN/proxy propio** (`/vpn`, `RITSUKO_VPN`). Motivo: Venice y notrack
  racionan por IP y por día; una auditora que sale por la misma IP se queda muda
  justo cuando una tarea agota el cupo, que es cuando más falta hace.
- **Y no rota para evadir.** `rota_por()` rechaza cualquier motivo que contenga
  cuota, cupo, ración, 429, rate limit, límite, bloqueo, ban, captcha,
  atestación o 403, y deja el intento apuntado. No hay parámetro que lo
  desactive — un test lo comprueba inspeccionando la firma de la función.

### Fallos de la v1 que este release cierra

- **La caché LRU nunca se usó.** `venice.py` llamaba a `cache_guarda(clave, …)`
  con `clave` sin definir en ningún sitio y jamás consultaba la caché: cada chat
  correcto moría con `NameError` **después** de haber gastado la ración. La
  «caché para que repetir no gaste cupo» que el README anunciaba no existía.
- **Dos `data_dir()` distintos.** El REPL resolvía la ruta por su cuenta y el
  núcleo por la suya. Coincidían por casualidad en Windows y divergían en el
  resto: lo que grababa uno no lo leía el otro.
- **Un solo perfil de Edge** para todos los sitios: las cookies de uno tumbaban
  la sesión del otro, y la puerta reportaba «la sesión Guest caducó» sobre un
  sitio que estaba perfectamente.
- **Marcas de UI de Venice aplicadas a cualquier sitio**: seis constantes en un
  `@staticmethod` que en notrack no recortaban nada, así que su pie de página se
  colaba dentro de la respuesta.
- **`prefer` construido como `f"g4f-{familia}"`**, una cadena que solo existe si
  la familia la sirve g4f. Con los sitios guest —cuyo id es `venice-guest`— la
  preferencia se perdía en silencio y el nodo acababa en la familia que el orden
  general dejase arriba: exactamente el fallo de diversidad que el registro
  existe para impedir. Ahora `prefer` casa por id **o** por familia.
- **El contenedor virtual duplicaba las capacidades** y ya discrepaba del
  cliente. Ahora las lee de `sitios.py`, que es la única fuente.
- **Pedir imagen a un sitio que no pinta** fallaba a los 240 s con «la imagen no
  apareció en el plazo» — la respuesta correcta a la pregunta equivocada. Ahora
  se rechaza al instante, con el nombre del sitio y el motivo.
- **`MOTIVOS_PROHIBIDOS` listaba «bloqueo»** y dejaba pasar «la IP quedó
  bloqueada», que es como se escribe en un log de verdad. Ahora son raíces.
- **`racion` como función exportada tapaba al módulo `venice.racion`**: a partir
  de ese import, `racion.CACHE_MAX` moría con `AttributeError`. Ahora es
  `racion_de`.

### El README deja de prometer nombres que no existen

`patch_file`, `delete_file`, `run_python` y `shell` existen como alias reales de
`edit_file`, `delete_path`, `python_exec` y `run_command` — **misma
implementación y mismos permisos**: llamar `shell` no salta la aprobación clic a
clic. Y `hardware_info` (CPU/RAM/GPU/disco) es código nuevo, porque esa
capacidad no existía y el README la prometía. Lo que no se puede medir sale en
`no_verificado`, nunca inventado.

## Compatibilidad

- **Rutas**: los datos viven en `%LOCALAPPDATA%\VeniceMAGI\`. Las variables de
  entorno del núcleo pasan a `VENICEMAGI_ROOT`, `VENICEMAGI_DATA_DIR`,
  `VENICEMAGI_WORKSPACE` y `VENICEMAGI_DESKTOP`. `VENICE_MAGI_DIR` sigue
  funcionando como override del REPL.
- **Paquete**: `magi` → `vmagi`. Cualquier script propio que importara `magi.*`
  hay que reapuntarlo.
- **Requisito nuevo**: Microsoft Edge instalado. Sin él, el camino guest no
  arranca y el sistema **lo dice** en vez de fallar a medias.
- `cache_consulta` y `cache_guarda` siguen existiendo por compatibilidad, ahora
  delegando en `racion_de`.
