# v2.2.0 — subagentes, percepción, memoria local y un automodelo que se puede tumbar

**Qué cambia:** VeniceMAGI se sincroniza con el MAGI del que salió (estaba
portado de v5.12.0, el upstream iba por v5.16.0) y estrena dos mecanismos
propios: **subagentes por familia** y **mando de modelos en caliente**.

**Descarga:** en Assets, `VeniceMAGI-v2.2.0.zip`. Dentro hay **un solo
fichero**, `VeniceMAGI.exe`: onefile, con su propio Python 3.10 dentro.

---

## Subagentes por familia

Un nodo es un solo hilo de pensamiento. Cuando el encargo tiene tres partes
separables, las aborda en fila y las últimas salen peor porque llegan con el
contexto ya gastado. Y mientras tanto los ocho núcleos están parados: el
enjambre espera respuestas de **red**, no de CPU. Medido en el proyecto de
origen: tres esperas independientes tardan **1,50 s en serie y 0,51 s en
abanico**.

Ahora cada nodo abre un frente por parte, todos a la vez, y lo que vuelve entra
como evidencia en su propia llamada.

- **En su propia familia**, no repartidos entre varias. Repartirlos parecería
  dar más diversidad y sería un error de los que no dan error: si los
  subagentes de Melchior salieran por la familia de Balthasar, la tesis
  llegaría contaminada con el sesgo de quien tiene que refutarla, y la
  refutación encontraría menos porque parte de lo mismo.
- **El troceo es determinista y no lo decide un modelo.** Cuesta una llamada de
  la ración averiguar cómo gastar la ración — y con un troceo que cambia entre
  corridas idénticas, la compuerta de la fase («tarda menos con la misma
  calidad») deja de poder medirse.
- **Nunca se pierde una promesa del encargo**: lo que pasa del máximo de cuatro
  frentes se pega al último en vez de tirarse.
- **Lo que no se cubrió, se dice.** Un texto fundido sin costuras esconde justo
  el frente que falló.
- **Un frente caído no se lleva a los demás**, que ya han gastado ración.
- **Balthasar no abre subagentes**, a propósito: su turno ya es redundante por
  diseño (varios ejes de refutación en paralelo), y abrirle un abanico encima
  sería pagar dos veces la misma redundancia.
- **Un abanico roto no tumba el turno.** Una optimización que puede dejarte sin
  respuesta no es una optimización.

El abanico deja medido su ahorro (`ms_abanico` contra `ms_si_fuera_en_serie`).
Esa es su compuerta: si no sale positivo de forma sostenida, se retira.

---

## `/modelos`: las opciones de modelo, ampliadas

El reparto vivía en un JSON y solo sabía decir qué familia le tocaba a cada
nodo. Cambiarlo exigía editar el fichero y reiniciar; y la lista de lo
disponible estaba repartida entre `sitios.py`, el catálogo y las constantes de
g4f, sin que nadie la juntara.

```
/modelos                     inventario completo + reparto actual
/modelos CASPER command      fija la familia de un nodo, en caliente
/modelos CASPER auto         la suelta y vuelve a mandar el catálogo
```

- **Enumera las 13 familias** disponibles sin cuenta —2 guest operadas por
  navegador y 11 de g4f— con su capacidad, sus candidatos vivos y la fecha de
  su última medida.
- **Se niega a poner dos nodos en la misma familia.** No se hacen eco: se dice
  por qué. El sistema seguiría respondiendo, peor, sin dar un solo error — que
  es exactamente la clase de fallo contra la que existe el registro.
- **Naoko y Ritsuko no se tocan desde aquí**: Naoko rota a propósito según la
  petición y Ritsuko tiene prohibidas las familias que audita. Ofrecer un mando
  que rompe una garantía es peor que no ofrecerlo.
- **Los agentes leen el reparto efectivo**, no el catálogo a secas. Leerlo a
  secas reproduciría el fallo de v5.0.28 una capa más arriba: el usuario
  cambiaría la familia, la interfaz diría que cambió, y los agentes seguirían
  llamando a la de antes.

---

## Sincronización con MAGI v5.16.0

VeniceMAGI se portó de v5.12.0. Entre medias el upstream construyó cuatro
subsistemas que aquí faltaban, y que encajan directamente con lo que el
proyecto ya promete:

- **Percepción** — oídos (loopback WASAPI: ¿suena? ¿sale entero?) y vista (qué
  hay en pantalla, en qué idioma, qué botón pide). Es la mitad que le faltaba
  al taller de arte, que hoy declara «no verificable» todo lo visual.
- **Índice local FTS5** — buscar en la bitácora, la memoria, los docs y el
  código sin gastar red **ni ración**. En VeniceMAGI esto vale doble: una
  consulta de más no cuesta latencia, cuesta una llamada del cupo diario que
  Venice raciona por IP.
- **Memoria persistente entre proyectos** — mandos por consola (16 consolas) y
  descartes con campo `rescatable`. Un enfoque que pierde deja conocimiento
  igual que uno que gana, y suele dejar más.
- **Mapa de interfaz** — qué topics de la GUI están conectados al núcleo.

---

## Automodelo: lo que VeniceMAGI sabe que no sabe

`docs/AUTOMODELO.json` llega **sembrado con lo de VeniceMAGI**, no con lo del
proyecto de origen. Cada afirmación trae la prueba que la tumbaría y la
evidencia de la última vez que la realidad dijo algo:

- **Refutadas (5):** que una sonda pueda medir un sitio guest *(exige abrir
  navegador: colgó el CI 124 s)*; que el crítico del taller pueda juzgar lo que
  se ve; que el vídeo generativo funcione en modo cloud; que el prompt llegue
  entero al proveedor *(se corta en 7000 caracteres sin avisar)*.
- **Sin comprobar (4):** que el chat guest de Venice responda; que el de
  notrack.ai responda; que el taller entregue de extremo a extremo; que la
  percepción funcione contra un artefacto real.

«Sin comprobar» **no es** «no funciona»: es que nadie lo ha puesto a prueba, y
decirlo es más útil que inventar un veredicto.

---

## Trinquetes: bajan, no suben

El conteo de huérfanos llegó a 89 con un techo de 88. La respuesta no fue subir
el techo: `familias_validas` pasa a `_familias_validas` porque la usa
`fijar_familia` y nadie más. 88, y `vmagi/venice` vuelve a su techo de 6.

Y un BOM más: escribir con PowerShell dejó un fichero con marca de orden de
bytes y `test_wiring` murió con un `SyntaxError` sin línea. Se escribe con
Python, `newline='\n'`.

---

## Compatibilidad

- **Sin cambios de interfaz.** Todos los comandos anteriores siguen igual.
- **Nuevo**: `/modelos`, y `familias_por_nodo` en `config.json`.
- **1719 tests en verde**, ruff limpio con la versión fijada.
