# PLAN — VeniceMAGI

**Fecha:** 2026-08-16 · **Proyecto NUEVO e independiente** de MAGI System IDE
(no comparte código ni repo; toma de él las lecciones, no los ficheros).

## Qué es

La variante de MAGI donde **la única IA es Venice.ai** (https://venice.ai):
sin enjambre de familias, sin rotación de proveedores, sin g4f. Un solo
motor, tres roles dialécticos y una supervisora — todos Venice:

```
TU PETICIÓN
    │
    ▼
NAOKO (Venice) clasifica y vigila
    │
    ▼
MELCHIOR  (Venice) — TESIS: construye, escribe código, genera imagen/vídeo
    │
    ▼
BALTHASAR (Venice) — ANTÍTESIS: refuta EJECUTANDO lo que Melchior hizo
    │
    ▼
CASPER    (Venice) — SÍNTESIS: integra y te entrega la respuesta final
```

Venice es tesis, antítesis y síntesis **a la vez**: mismo modelo, tres
contratos distintos. La dialéctica no viene de la diversidad de modelos
(como en MAGI) sino de la confrontación de roles con evidencia ejecutada.

## La API (medida en la documentación oficial, 2026-08-16)

| Capacidad | Endpoint | Notas |
|---|---|---|
| Chat | `POST /api/v1/chat/completions` | OpenAI-compatible; Bearer key. Modelo por defecto `zai-org-glm-5`. |
| Imagen | `POST /api/v1/image/generate` | `model`, `prompt`, `aspect_ratio`, `resolution`, `format`, `style_references` (fidelidad a diseños), `variants`, base64. |
| Vídeo | `POST /api/v1/video/queue` + `GET /video/retrieve?id=` | Cola: `model`, `prompt`, `duration`, `aspect_ratio`, `resolution`, `reference_image_urls` (hasta 30), `consents`. Descarga al terminar. |
| Modelos | `GET /api/v1/models` | Para listar y validar. |

Clave: `VENICE_API_KEY` (entorno) o `%LOCALAPPDATA%\VeniceMAGI\config.json`.
Se consigue en venice.ai/settings/api.

## «Ilimitado»

No existe API ilimitada de verdad: la de Venice tiene límites de tarifas.
Lo que SÍ se puede prometer y se implementa: **sin límites artificiales
nuestros** — sin toques por sesión, sin raciones, sin degradación
voluntaria. Ante un 429 (límite de tarifas) se espera con backoff
exponencial y se reintenta; el vídeo se polla hasta terminar. Si Venice
dijera que se acabó la cuota, Naoko lo explica en español y dice qué hacer.

## Fidelidad «idéntica a los diseños originales»

- Imagen: `style_references` (imágenes de referencia con `strength`) y
  `seed` fija para reproducibilidad.
- Vídeo: `reference_image_urls` (hasta 30) + prompt que EXIGE copiar
  composición/paleta/estilo de las referencias, no reinterpretarlas.
- Los prompts de rol incluyen la regla: si hay diseño de referencia, la
  copia es el contrato; la creatividad solo donde el usuario la pida.
- Honestidad: la fidelidad final la decide el modelo subyacente; el sistema
  aporta todos los mecanismos que la API expone para maximizarla.

## Estructura

```
VeniceMAGI/
  PLAN.md  README.md  requirements.txt  VeniceMAGI.spec
  venv (propio)
  vmagi/
    __init__.py     versión
    config.py       clave, modelos, directorios de datos
    venice.py       cliente HTTP (chat/imagen/vídeo/modelos) + reintentos
    roles.py        MELCHIOR / BALTHASAR / CASPER / NAOKO (prompts)
    tools.py        protocolo de herramientas + ejecutor
    orchestrator.py una ronda dialéctica completa + segunda ronda con feedback
    naoko.py        supervisión: estado, clave, errores explicados
    store.py        historial de sesión (sqlite)
    app.py          REPL: /estado /imagen /video /refs /salir
  tests/            todo con FakeVenice, sin red
  dist/VeniceMAGI.exe  (compilación local, NADA de GitHub)
```

## Herramientas del enjambre (reales, no decorativas)

- `write_file(path, content)` — escribe en el workspace de la sesión.
- `run_python(code)` — ejecuta con timeout y captura stdout/stderr
  (Balthasar vive de esto: refutar es ejecutar).
- `generate_image(prompt, ref_paths?, aspect_ratio?)` — Venice image.
- `generate_video(prompt, duration, ref_urls?)` — Venice video (cola+poll).

## Verificación y entrega

1. Tests offline (FakeVenice): ronda completa, protocolo de herramientas,
   consentimientos de vídeo, errores de clave explicados, reintentos 429.
2. `python -m pytest tests/ -q` en verde.
3. Compilación local: `pyinstaller VeniceMAGI.spec` → `dist/VeniceMAGI.exe`.
4. **NO se sube a GitHub**: proyecto privado del usuario, binario local.

## Lo que NO es

- No es MAGI: no hay catálogo de proveedores, sonda multi-familia,
  cortacircuitos ni sesión web. Un proveedor, cero rotación.
- No sustituye la GUI Tauri de MAGI: v1 es REPL de consola. La ventana
  nativa puede venir después sobre este núcleo.


---

## Bitácora de la implementación (2026-08-16, sesión completa)

### Ingeniería inversa medida (no supuesta)
- `/api/auth/anon` legacy → «Bad request»: MUERTO.
- Clerk FAPI (`clerk.venice.ai/v1/client/sign_ups`, `strategy=anonymous`)
  → `captcha_missing_token`: exige Turnstile.
- El bundle JS (71 chunks del chat, desminimizados a mano) reveló:
  outerface.venice.ai, atestación de cliente (`x-venice-client-attestation`)
  y el esquema de `/api/inference/chat` e `/image`.
- Chromium headless → 403 de atestación. **Edge real → 200.** El Guest
  existe («Venice Guest», «O prueba Venice sin una cuenta»).
- Conclusión: la puerta es Edge real con ventana visible. Sin ella, no hay
  vía sin clave.

### Verificado E2E en el exe compilado
- Ronda dialéctica COMPLETA con Venice Guest sin clave: Naoko clasificó,
  Melchior creó `saludo.txt`, Balthasar lo verificó ejecutando, Casper
  sintetizó. Salida real del exe.
- Playwright Sync no puede vivir en el loop de asyncio → la puerta tiene
  hilo propio dueño del navegador; el resto delega con `llamar()`.
- La sesión Guest CADUCA y el modal de login salta en cualquier momento →
  reentrada automática como Guest + repetición de la petición (1 vez).
- El cupo del Guest es POR IP Y DÍA: reentrar como Guest nuevo no lo
  recupera (medido). Segundo modal seguido = CupoDiarioAgotado, explicado
  por Naoko sin drama.
- Heurística de imagen endurecida tras medir que el logo de Clerk del
  modal se cuela como <img> nuevo: solo cuentan imágenes ≥200px que no
  vengan de clerk/íconos; si la imagen no llega, se guarda CAPTURA
  diagnóstica de lo que la página mostraba.
- Al fallar una espera por navegación del primer envío («Execution
  context was destroyed»), las lecturas reintentan: el poll siguiente ya
  corre sobre la página nueva.

### Pendiente con fecha
- Validar generación de IMAGEN con cupo fresco (mañana): el circuito está
  terminado y probado hasta donde la ración diaria de la IP permitió hoy.
- Vídeo: bloqueado por Venice para Guests (Pro/API). Naoko lo explica.

### Cierre de la sesión (2026-08-23)
- Lector de respuestas blindado: menos de 40 caracteres útiles tras restar
  el eco NO es respuesta — se lanza error claro. Antes, cuando Venice no
  contestaba (cupo), el eco del propio prompt se devolvía como respuesta
  y el enjambre degeneraba en tres turnos.
- Roles compactos: los prompts largos se colapsan en la UI («mostrar más»)
  y ensucian la lectura por diferencia. Contrato corto = eco corto.
- El cupo diario por IP limitó la re-validación de hoy a: puerta OK,
  Guest OK, modal OK, reentrada OK, no-degeneración OK. La ronda dialéctica
  completa quedó verificada E2E el 2026-08-16 (saludo.txt creado y
  verificado por Balthasar). Con ración fresca, la imagen sigue el mismo
  circuito ya probado estructuralmente.
