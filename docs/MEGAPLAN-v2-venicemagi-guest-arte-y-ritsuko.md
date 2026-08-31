# MEGAPLAN v2 — VeniceMAGI: guest multi-familia, taller de arte y la red de Ritsuko

Estado: **aplicado** en v2.0.0.

Este documento existe para que quien venga a simplificar algo de lo de abajo
lea primero por qué existe. Cuarta regla del proyecto: el porqué va pegado al
arreglo.

---

## 0. El punto de partida

VeniceMAGI v1 eran 40 ficheros y ~3 000 líneas: un REPL sobre **un** proveedor
guest (Venice), con contenedor virtual, pipeline de medios y una GUI web
mínima. MAGI-System-IDE eran ~2 700 ficheros y 256 000 líneas: enjambre
dialéctico, 50 herramientas reales, GUI React, Naoko, Ritsuko, sonda de
proveedores, cortacircuitos y 1 472 tests.

El encargo era hacer VeniceMAGI **idéntico** a MAGI-System-IDE sin perder su
finalidad. Las dos mitades chocan en un punto concreto, y ese choque es lo que
este documento resuelve.

---

## 1. El choque: monocultivo contra diversidad de familias

MAGI-System-IDE ancla cada nodo a una **familia de modelo distinta**, y ese es
su argumento entero: si el crítico comparte sesgos con el proponente, el debate
popperiano no vale nada. Su Ritsuko lleva la idea al extremo — corre en una
familia que **no comparte con ninguna** de las cuatro que audita.

VeniceMAGI v1 era **monocultivo deliberado**: los cuatro roles eran el mismo
modelo de Venice, y la dialéctica vivía en los contratos, no en la diversidad.

No se pueden tener las dos. Y la elección no es de gusto:

- Con monocultivo, Balthasar refutando a Melchior es el mismo modelo
  contradiciéndose a sí mismo. Devuelve el eco de la tesis con otro tono.
- Con monocultivo, **Ritsuko es imposible**: un auditor que corre el modelo del
  auditado se cae con él, justo el día que hace falta.

### La decisión

Multi-familia, **pero todas guest y sin clave**. La promesa que VeniceMAGI hace
no es «un solo proveedor»: es «sin cuenta ni key obligatoria en el camino
principal». Eso se cumple con dos sitios guest operados por navegador (`venice`,
`notrack`) más las familias de g4f, que también son gratuitas y sin clave.

    MELCHIOR   venice     construye, y es el único guest que además pinta
    BALTHASAR  notrack    refuta con un modelo que no es el del proponente
    CASPER     gemini     sintetiza por HTTP: es quien te habla y su latencia
                          se nota en cada respuesta
    NAOKO      rota entre command / gpt / claude
    RITSUKO    razonamiento / grok / perplexity — ninguna auditada

`venice` y `notrack` entran en `FAMILIAS_AUDITADAS`. Si alguien las dejara
fuera, la cadena de Ritsuko podría caer en la familia del camino principal sin
que ningún test lo notara.

---

## 2. La puerta, generalizada

La v1 traía Venice hardcodeado en `sesion.py`: la URL, el texto del enlace de
invitado, las marcas del modal y las del cupo, esparcidas entre la puerta y el
cliente. Añadir un segundo sitio exigía tocar las dos.

`vmagi/venice/sitios.py` declara cada sitio como una fila. La puerta recibe un
`SitioGuest` y lo opera sin saber de ninguno en concreto.

Tres fallos que la generalización destapó, todos reales:

1. **Un solo perfil de Edge para todos.** Las cookies de un sitio tumbaban la
   sesión del otro, y la puerta reportaba «la sesión Guest caducó» sobre un
   sitio que estaba perfectamente. Ahora hay un perfil por sitio.
2. **Las marcas de UI de Venice en un `@staticmethod`.** Aplicadas a notrack no
   recortaban nada y su pie de página se colaba dentro de la respuesta.
3. **Imagen pedida a un sitio que no pinta.** Se intentaba igual, y el error
   salía 240 s más tarde como «la imagen no apareció en el plazo»: la respuesta
   correcta a la pregunta equivocada.

---

## 3. `prefer`, o cómo se pierde la diversidad en silencio

`cloud.py` construía el proveedor preferido como `f"g4f-{familia}"`. Es una
cadena que solo existe si esa familia la sirve g4f.

En cuanto entraron los sitios guest —cuyo id es `venice-guest`— pedir la familia
`venice` dejó de casar con nadie. La preferencia **no fallaba**: se perdía. El
nodo acababa en la familia que el orden general dejase arriba, que es
exactamente el fallo de diversidad que el registro existe para impedir, y sin
una sola línea de log.

`_candidates` casa ahora por **id o familia**. El eje que sostiene el debate
deja de depender de cómo se llame el backend que lo sirve.

---

## 4. El taller de arte

### El problema

Pedirle una imagen a un modelo y quedarse con lo que salga falla dos veces:

- **Un solo autor no tiene con quién contrastar.** Si entiende mal el encargo,
  el resultado es coherente consigo mismo y nada lo delata. Es el mismo problema
  que el enjambre resuelve para el código, y no había equivalente para el arte.
- **Nadie cuenta las promesas.** «Salió una imagen» se confunde con «salió LA
  imagen». Un encargo de cuatro promesas se entrega con dos cumplidas y nadie
  las cuenta.

### El mecanismo

1. **Contrato antes que prompt.** El encargo se trocea en promesas separables.
   Las medibles (existe, abre, proporción, entropía) las decide una máquina.
2. **Dos autores en paralelo, sin verse.** El paralelismo *es* la separación:
   encadenarlos haría que el segundo viera por dónde tiró el primero.
3. **Crítico en una tercera familia**, con sesgo invertido: donde el autor
   quiere entregar, el crítico quiere encontrar el fallo. Ante la duda,
   INCUMPLE.
4. **La máquina manda sobre el modelo.** Un criterio medible que salió falso
   queda incumplido aunque el crítico lo apruebe.
5. **Reintento dirigido**, con la lista concreta de incumplidas.

### Lo que el taller no finge

**notrack.ai no genera imágenes.** Es un chat. Entra como autor de pleno derecho
—redacta su lectura y su prompt, en paralelo y sin ver al otro— y el pincel lo
pone Venice, o el backend local en `hybrid`. Decirlo así es la quinta regla:
«notrack pintó esto» sería falso.

**Los modelos guest no tienen visión.** No pueden mirar el PNG. El crítico
separa lo que mide una máquina de lo que juzga leyendo, y declara lo que **no ha
podido verificar** en vez de aprobarlo por omisión. Sin Pillow no se aprueba
nada: ese es literalmente el fallo del que salió la quinta regla —el observador
devolvía «correcto» sobre una captura que nunca llegó a abrir.

---

## 5. La salida de red de Ritsuko

### Por qué

Ritsuko usa una familia que no comparte con nadie. Eso es medio argumento. El
otro medio es la red: Venice y notrack racionan **por IP y por día**. Con salida
común, la tarea que agota el cupo deja muda a la auditora en el mismo instante
— y ese instante es justo cuando hace falta un veredicto independiente.

No es teórico. La auditoría del 20-ago encontró a Naoko declarando «deriva del
modelo» en dos familias enteras justo después de una tarea que había agotado la
cuota de esos mismos proveedores. Estaba midiendo su propia interferencia y
llamándola avería.

### La línea, y cómo se hace cumplir

El manifiesto dice «sin evasión de cuotas (no rotación automática de IP/VPN)».
Una salida separada es compatible; **rotarla cuando el proveedor dice "hoy no"
no lo es** — eso es burlar la ración de quien nos da el servicio gratis.

La diferencia no se deja a la buena voluntad de quien llame:

1. La salida se **configura a mano** (`RITSUKO_VPN`, `config.json`, `/vpn`).
2. `rota_por(motivo)` **rechaza** los motivos de evasión y apunta el intento.
   No hay parámetro que lo desactive, y un test lo comprueba inspeccionando la
   firma de la función.
3. La salida es **de Ritsuko**: no se aplica al enjambre, ni a la puerta, ni al
   tráfico general. Aplicarla a todos convertiría una medida de independencia
   en una de evasión.

Y una lección de la primera versión de `MOTIVOS_PROHIBIDOS`: listaba «bloqueo» y
dejaba pasar «la IP quedó bloqueada», que es como se escribe en un log de
verdad. Una lista de prohibiciones que solo caza la forma de diccionario no
prohíbe nada. Ahora son raíces.

**No hay listas de proxies públicos gratuitos embebidas**, y es deliberado: son
inestables, a menudo hostiles, y una lista que rota sola es la rotación
automática por la puerta de atrás.

---

## 6. El README deja de prometer nombres que no existen

El manifiesto enumera `read_file`, `list_dir`, `patch_file`, `delete_file`,
`hardware_info`, `run_python` y `shell`. El núcleo portado traía equivalentes
con otros nombres y no traía `hardware_info` en absoluto.

Un README que promete un nombre inexistente es una promesa incumplida aunque la
capacidad esté: quien lea el documento y escriba `patch_file` recibe
«herramienta desconocida», y concluye con razón que el documento miente.

`core/tools/manifiesto.py` instala los alias apuntando a la misma
implementación —si `edit_file` mejora, `patch_file` mejora con él— **con los
mismos permisos**: llamar `shell` no salta la aprobación clic a clic. Y
`hardware_info` es código nuevo, que declara en `no_verificado` lo que no puede
medir en vez de inventárselo.

---

## 7. Lo que queda pendiente

- **Vídeo guest.** Ningún proveedor guest declara vídeo. El contenedor lo dice
  con el motivo en vez de intentarlo; `/video` en `cloud` es honesto y limitado.
- **Visión para el crítico.** Mientras ningún guest acepte imágenes de entrada,
  las promesas visuales del contrato seguirán saliendo como `no_verificable`.
  Es la respuesta correcta hoy, no la deseable.
- **Medir notrack.** Su latencia y su ración no están medidas todavía; el
  catálogo lleva la fecha de verificación para que se note cuándo envejece.
