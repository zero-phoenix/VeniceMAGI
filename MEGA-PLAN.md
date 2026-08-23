# MEGA PLAN — VeniceMAGI v2: de REPL a IDE con ventana propia

**Fecha:** 2026-08-23 · **Base:** v1.1.0 (commit `4b682dc`), 15 tests verdes,
ronda dialéctica real comprobada E2E con el Guest de Venice.

Lo que sigue está escrito contra lo MEDIDO, no contra lo deseado. Donde hay
una promesa que no se puede cumplir, se dice — y se ofrece la alternativa
honesta más cercana.

---

## Parte 0 · Lo que la captura del usuario dice, tal cual

1. **«No tiene interfaz propia como el MAGI original»** — cierto: v1 es un
   REPL de consola. El PLAN de v1 ya lo admitía («la ventana nativa puede
   venir después»). Es la hora.
2. **«No funciona como una IDE»** — cierto: no hay workspace visible, ni
   editor, ni árbol de ficheros, ni galería de artefactos. Las herramientas
   existen (write_file/run_python) pero son invisibles.
3. **«Encima abre un navegador»** — cierto y deliberado: la ventana de Edge
   ES la puerta sin clave (medido: headless → 403, Edge real → 200). No se
   puede eliminar; sí se puede **aparcar** (Parte 2).
4. **«Debe funcionar ilimitadamente»** — lo que existe de verdad: sin
   límites NUESTROS, tu VPN propia integrada (`/proxy`), y una ración
   diaria de Venice por IP que no se puede prometer eludir sin arriesgar
   el bloqueo (Parte 5, dicha entera).
5. **«Trabajar con los recursos de hardware de mi computadora»** — las
   herramientas ya ejecutan en tu máquina; v2 las hace de verdad útiles y
   visibles (Parte 3).

---

## Parte 1 · Ventana propia: la GUI (el corazón de v2)

**El patrón ya probado en MAGI v5**: núcleo Python + frontend web servido
en local + ventana nativa `pywebview`. Sin Electron, sin Tauri nuevo: el
mismo hueso que ya funciona en este equipo.

- `vmagi/gui_server.py` — HTTP local (127.0.0.1, puerto libre) que sirve
  el frontend y habla por WebSocket con el núcleo (bus de eventos: lo
  mismo que hace MAGI con su bus).
- `vmagi/web/` — frontend (HTML+JS, Monaco editor por CDN local empaquetado):
  - **Panel Enjambre**: hilo de conversación con las intervenciones de
    MELCHIOR / BALTHASAR / CASPER / NAOKO distinguibles, la síntesis
    destacada, y el estado de la ronda en vivo.
  - **Panel Workspace**: árbol de ficheros real del workspace, editor con
    pestañas y diffs, botón ejecutar.
  - **Panel Medios**: galería de imágenes/vídeos generados con su prompt y
    su semilla (reproducibilidad).
  - **Panel Estado**: puerta (Guest, proxy, cupo con la fecha de la última
    ración), modelos, historial.
- `run.py` abre la ventana nativa con la GUI; el REPL queda como modo
  de respaldo (`--consola`).
- La ventana de Edge (puerta) sigue existiendo: la GUI la gestiona
  (Parte 2).

**Se comprueba con:** test de que el servidor responde, de que el bus
emite los eventos que la GUI pinta, y un test E2E headless del frontend
(sin red: estado inyectado).

**Puede salir mal:** pywebview en Windows arrastra pythonnet/clr-loader
( ya visto en MAGI: el lock es de Windows). Se asume y se documenta.

## Parte 2 · La puerta discreta: el Edge fuera de la vista

No se puede cerrar la ventana (headless = 403 por atestación, medido
dos veces). Pero un navegador REAL no deja de ser real por estar aparcado:

- **Modo aparcado** (por defecto en v2): la ventana de Edge se lanza con
  `--window-position=-32000,-32000` (fuera de pantalla). El navegador
  funciona, la atestación se resuelve igual, y no estorba.
- **Botón «mostrar puerta»** en la GUI (por si hay que resolver algo a
  mano, un captcha ocasional o verificar visualmente).
- **Modo visible** opcional para quien quiera ver el trabajo.
- Riesgo honesto: si Venice endureciera la atestación exigiendo ventana
  visible, el modo aparcado fallaría — se detecta (403 en la primera
  petición) y la GUI avisa con «abre la puerta en modo visible».

## Parte 3 · IDE de verdad: el hardware de tu máquina, visible

Las herramientas de v1 ampliadas al contrato de una IDE:

- **Ficheros**: `read_file`, `list_dir`, `patch_file` (diff quirúrgico,
  no reescrituras), `delete_file` con papelera (journal de deshacer —
  lección nº1 de MAGI).
- **Ejecución**: `run_python` con watchdog y límite de memoria; `shell`
  (comandos del sistema) **solo con aprobación explícita en la GUI** —
  botón aprobar/rechazar, nunca silencioso.
- **Hardware**: `hardware_info` (CPU, RAM, GPU por `psutil`/WMI) para que
  el enjambre sepa qué puede pedirle a TU máquina (¿compila aquí?, ¿ffmpeg?,
  ¿tienes GPU para difusión local futura?).
- **Medios locales**: `ffmpeg_disponible`, `edit_image` (PIL: recortar,
  escalar, componer) — el trabajo pesado ocurre en tu PC, no en la nube.
- Todo auditable en el panel: cada herramienta con su entrada, su salida
  y su coste (tiempo real de tu CPU).

## Parte 4 · Medios: lo máximo que el Guest da, y lo que se compone local

- **Imagen**: igual que v1 (Guest sí genera) + galería, semilla fija y
  **variantes por referencia** (usa la imagen generada como style_reference
  de la siguiente: consistencia visual de personaje/escena).
- **Vídeo HONESTO**: Venice reserva el vídeo AI a Pro. Lo que sí se puede
  construir HOY con tu hardware:
  1. El enjambre descompone la escena en N planos (prompt por plano).
  2. Genera N imágenes Venice (misma semilla de estilo / referencias).
  3. **Compone el mp4 en TU PC** (ffmpeg o PIL+imageio): duración por
     plano, fundidos, texto opcional.
  - Es un vídeo de planos (motion graphics), NO vídeo AI fluido. Se llama
    `video_planos` y la GUI lo dice así, sin disfrazarlo.
- **Audio**: TTS del Guest sin medir → fase de medición antes de prometer
  nada (lección de las cookies de Claude: medir antes de construir).

## Parte 5 · «Ilimitado»: el capítulo que no miente

- **Lo que hay**: cero límites autoimpuestos; reintentos con backoff;
  tu VPN propia por `/proxy` (tu red, tu decisión); reentrada Guest.
- **Lo que no habrá**: rotación de IP ni reconexión al agotar cuota —
  el test guardián ya vigila que no entre en el paquete. Eludir la ración
  acabaría con el rango de tu VPN bloqueado.
- **Lo que se añade para exprimir la ración de cada día**:
  - **Caché LRU de respuestas** (la traducción/duplicados no gastan ración).
  - **Cola de trabajo con presupuesto**: la GUI muestra «te quedan ~N
    peticiones hoy» (aprendido del propio uso) y encola lo que no quepa,
    reanudando cuando la ración vuelve (mañana) — el sistema sigue
    trabajando mientras duermes, sin saltarse nada.
  - **Presupuesto por tarea**: Melchior propone, Balthasar refuta y Casper
    decide con un máximo de turnos configurable (por defecto austero).

## Parte 6 · Calidad y entrega

- Tests de todo lo anterior sin red (FakeVenice + servidor de la GUI en
  puerto efímero + ffmpeg de mentira inyectado).
- CI ya verde en el repo privado; release con zip + checksums ya montado.
- v2.0.0 cuando: GUI operativa + puerta aparcada + suite en verde.

---

## Orden de ejecución

```
1. GUI (Parte 1)          — lo visible primero: sin esto no hay IDE
2. Puerta aparcada (2)    — pequeña, inmediata, gran alivio visual
3. Herramientas IDE (3)   — read/patch/journal/hardware/shell con aprobación
4. Medios (4)             — galería + video_planos local
5. Ración (5)             — caché, cola y presupuesto
6. v2.0.0                 — release
```

## Lo que este plan NO propone

- Headless puro sin navegador: medido, 403. No es terquedad: es el muro.
- Elusión de cuota por rotación de IP: riesgo de bloqueo total y va
  contra la letra de la Parte 5.
- Vídeo AI fluido sin cuenta Pro: Venice lo reserva; disfrazarlo sería
  mentir en el panel.
