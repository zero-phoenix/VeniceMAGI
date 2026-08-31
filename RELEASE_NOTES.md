# v2.1.0 — el CI verde, una sola salida de red y el anonimato como código

**Qué cambia:** la v2.0.0 no llegó a compilarse. Este release arregla las dos
causas —una que colgaba el CI sin dejar diagnóstico y otra que ni siquiera
llegaba a ejecutarse— y sustituye el principio de no-evasión por **anonimato
absoluto**, implementado en las tres capas que salen a la red.

**Descarga:** en Assets, `VeniceMAGI-v2.1.0.zip`. Dentro hay **un solo fichero**,
`VeniceMAGI.exe`: onefile, con su propio Python 3.10 dentro, sin instalador y
sin dependencias que instalar.

---

## Lo que rompía el build, y ya no

### 1. El CI se colgaba 124 s y moría con un `Timeout` sin diagnóstico

`test_rpc_handlers_arrancan.py` invoca **todos** los handlers RPC para
comprobar que ninguno revienta al importar. Por una cadena de tres llamadas que
nadie había mirado entera, uno de ellos acababa en `GuestWebProvider.complete()`
con `probe=True` — y eso, en un runner de Windows sin escritorio, intentaba
**abrir un Microsoft Edge real** y esperar a que cargase venice.ai.

No fallaba: se quedaba quieto hasta que saltaba el plazo global de pytest. Un
fallo que cuelga es peor que uno que revienta, porque no deja nada que leer.

Tres frenos, porque uno solo se olvida:

- **Una sonda no abre un navegador. Nunca.** `complete()` con `req.probe`
  rechaza al instante. El trabajo de una sonda es medir salud barato; abrir un
  navegador cuesta decenas de segundos y gasta ración del día para no aprender
  nada que `available()` no responda ya mirando el disco.
- **`VENICEMAGI_SIN_PUERTA=1`**, interruptor de proceso: `edge_disponible()`
  dice que no y `abrir()` se niega, sin tocar el disco. Y si el cortafuegos de
  navegador de §I.3 está instalado, la puerta tampoco es una excepción a esa
  decisión.
- **El guardián de entorno de los tests** cubre ahora `vmagi/venice/puerta.py`.
  Ya existía para `sesion_web` —cinco veces un test pasó en local y falló en el
  CI por preguntarle a la máquina— y la puerta se quedó fuera al portarla.

### 2. Lint: 28 errores de ruff que ni dejaban llegar al build

`E741` (la variable `l`, que se confunde con `1` y con `I`), `I001` (orden de
imports), `F401` (imports sin usar), `UP037` (anotaciones entrecomilladas) y
`F841`. Todos en el código nuevo del port. Arreglados de raíz, no silenciados.

---

## Anonimato absoluto

Sale el principio «sin evasión de cuotas» y entra **anonimato absoluto en todo
sentido**, que no es una postura sino una lista de frenos concretos:

- **Una sola salida de red, para todo.** Había **tres puertas** que no se
  conocían entre sí: `/proxy` para la ventana de Edge, `NOTRACK_PROXY` para el
  HTTP y `/vpn` para Ritsuko. Eso es **tráfico partido**: media aplicación por
  la VPN y la otra media por tu línea, las dos rutas se correlacionan, y la VPN
  deja de servir para lo único que sirve. Ahora `ritsuko_red` gobierna las tres
  capas —HTTP, navegador y **variables de entorno de los subprocesos**, que se
  olvidan siempre y son por donde se escapa `git`.
- **Modo estricto** (`/vpn estricto on`): sin salida configurada, el sistema
  **no sale**. La diferencia entre «uso VPN» y «uso VPN salvo cuando falle»,
  que para el anonimato es la diferencia entre servir y no servir.
- **`/vpn purgar`**: borra perfiles de navegador, caché y logs. El anonimato
  hacia fuera no sirve si el sitio te reconoce por el perfil — un perfil
  persistente guarda cookies entre sesiones aunque cambies de IP.
- **Credenciales enmascaradas** en cualquier informe: `//usuario:***@host`.
- **Errores útiles**: rechazar una salida mal escrita incluye ejemplos que
  funcionan (Tor en `socks5://127.0.0.1:9050`, gratis y sin cuenta).

---

## Ritsuko: más ojos, no más manos

Las funciones nuevas son **todas de lectura**. Sigue sin escribir código, sin
cancelar tareas y sin tocar el reparto: un auditor con permiso para arreglar
acaba revisándose a sí mismo a la segunda vez que arregla algo.

- **`anonimato()`** — enumera las **fugas reales** con nombre y sitio: sin
  salida configurada, modo estricto apagado, perfiles persistentes que te
  identifican entre sesiones. Devuelve la lista, no un «ok»: un informe de
  privacidad que solo sabe decir que sí es un informe que nadie ha mirado.
- **`inventario_proveedores()`** — quién atiende hoy cada capacidad, con la
  fecha de su última medida, y por qué la puerta no puede abrirse si no puede.
- **`racion_del_dia()`** — cuánto cupo va gastado, por sitio.
- **Gobierna la salida de red del sistema entero.** Es la única pieza cuyo
  trabajo es mirar el conjunto, y la salida de red es una propiedad del
  conjunto. Ponerla en el enjambre habría dado tres puertas otra vez.

---

## Vídeo: «Seedance 2.5+» pasa a significar eso

La comprobación era `"seedance-2.5" not in model and "seedance-3" not in
model`: dos cadenas literales para expresar una **comparación de versiones**.
Rechazaba `seedance-2.6` y `seedance-4` —las versiones más nuevas, justo las
que la regla quiere permitir— porque su texto no contiene ninguna de las dos.

Ahora se extrae la versión y se compara. Una regla sobre versiones escrita con
`in` no es una regla sobre versiones: es una lista de dos nombres que envejece
sola.

---

## Compatibilidad

- **Sin cambios de interfaz.** `/proxy` y `/notrack` siguen existiendo;
  `NOTRACK_PROXY` sigue valiendo como fuente de la salida única, así que una
  configuración que ya funcionaba sigue funcionando.
- **Nuevo**: `RITSUKO_VPN`, `RITSUKO_VPN_ESTRICTA`, `VENICEMAGI_SIN_PUERTA`.
- **Requisito**: Microsoft Edge, para el camino guest.
