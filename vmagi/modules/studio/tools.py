"""
Herramientas de la fábrica de artefactos (Plan MAGI 9.0 §5).

Sin este registro, artifacts.py sería andamiaje. Con él, Melchior construye un
juego y Balthasar lo ARRANCA y mira la captura antes de opinar.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from ...core.tools.registry import ToolRegistry, ToolResult


def register_studio_tools(reg: ToolRegistry) -> ToolRegistry:

    @reg.tool("crear_arte",
              "Encarga una imagen al taller: dos autores independientes "
              "(venice y notrack) proponen por separado, un tercer modelo "
              "más estricto comprueba que lo entregado cumple el encargo, y "
              "el reintento lleva dentro qué corregir.",
              {"type": "object", "properties": {
                  "prompt": {"type": "string"},
                  "aspect_ratio": {"type": "string",
                                   "enum": ["1:1", "16:9", "9:16", "4:3", "3:4"]},
                  "seed": {"type": "integer"}},
               "required": ["prompt"]}, access={"exec"})
    async def crear_arte(prompt: str, ctx=None, aspect_ratio: str = "1:1",
                         seed: int | None = None):
        """La entrada del taller desde el enjambre.

        Se registra aquí y no vive suelto a propósito: la primera regla del
        proyecto es que todo cambio se conecta o se borra. `arte.py` sin
        esta línea sería código correcto que ningún agente puede invocar
        — que es exactamente el andamiaje que el trinquete de huérfanos
        existe para cazar, y lo cazó.
        """
        from vmagi.core.providers.cloud import FreeCloudLLM
        from vmagi.venice.cliente import Venice

        from .arte import TallerDeArte

        pintor = Venice()
        taller = TallerDeArte(FreeCloudLLM(), pintor.imagen)
        obra = await taller.crear(prompt, aspect_ratio=aspect_ratio, seed=seed)

        md = obra.metadata()
        if obra.ruta is not None:
            # Trazabilidad: cada render deja su metadata reproducible al lado.
            try:
                (obra.ruta.with_suffix(obra.ruta.suffix + ".json")).write_text(
                    json.dumps(md, indent=1, ensure_ascii=False),
                    encoding="utf-8")
            except OSError:
                pass

        v = obra.veredictos[-1] if obra.veredictos else None
        lineas = [f"estado: {obra.estado} (pasadas: {obra.pasadas})",
                  f"archivo: {obra.ruta or '(ninguno)'}"]
        for p in obra.propuestas:
            lineas.append(f"[{p.autor}] {p.prompt or p.error}")
        if v:
            lineas.append(f"crítico ({v.familia}): "
                          f"{len(v.cumplidos)} cumplidas, "
                          f"{len(v.incumplidos)} incumplidas, "
                          f"{len(v.no_verificables)} no verificables")
            for x in v.incumplidos:
                lineas.append(f"  INCUMPLE: {x}")
            for x in v.no_verificables:
                lineas.append(f"  NO VERIFICABLE: {x}")
        return ToolResult(obra.estado == "entregada", "\n".join(lineas),
                          error=None if obra.estado == "entregada"
                          else f"el taller no convergió: {obra.estado}",
                          meta=md)

    @reg.tool("observe_artifact",
              "Inspecciona un artefacto ya generado: arranca un programa, "
              "renderiza un juego y captura un fotograma, mide un documento o "
              "analiza una imagen. Devuelve lo que SE VE, no lo que se supone.",
              {"type": "object", "properties": {
                  "path": {"type": "string"},
                  "kind": {"type": "string",
                           "enum": ["programa", "juego", "imagen",
                                    "documento", "video", "datos"]},
                  "entry": {"type": "string",
                            "description": "punto de entrada del juego, p.ej. main.py"}},
               "required": ["path"]}, access={"exec"})
    async def observe_artifact(path: str, ctx=None, kind: str = "",
                               entry: str = ""):
        from .artifacts import observe
        p = ctx.resolve(path) if ctx else Path(path)
        kw = {}
        if entry:
            kw["entry"] = entry
        obs = await observe(p, kind or None, **kw)
        return ToolResult(obs.ok, obs.render(),
                          error=None if obs.ok else "; ".join(obs.problems),
                          meta={"screenshot": obs.screenshot,
                                "kind": obs.kind.value})

    @reg.tool("inspect_image",
              "Analiza una imagen sin gastar cuota de visión: tamaño, número "
              "de colores y color dominante. Detecta pantallas en negro.",
              {"type": "object", "properties": {"path": {"type": "string"}},
               "required": ["path"]}, access={"read"})
    async def inspect_image(path: str, ctx=None):
        from .artifacts import observe_image
        p = ctx.resolve(path) if ctx else Path(path)
        obs = await observe_image(p)
        return ToolResult(obs.ok, obs.render(),
                          error=None if obs.ok else "; ".join(obs.problems))

    @reg.tool("compose_manga_page",
              "Compone una página de manga con viñetas y lectura RTL, "
              "validando la composición antes de dibujar nada.",
              {"type": "object", "properties": {
                  "out_path": {"type": "string"},
                  "rows": {"type": "integer"},
                  "cols": {"type": "integer"},
                  "prompts": {"type": "array", "items": {"type": "string"},
                              "description": "descripción de cada viñeta"},
                  "layout": {"type": "string", "enum": ["grid", "dramatic"]},
                  "order": {"type": "string",
                            "enum": ["rtl", "ltr"],
                            "description": "rtl = manga (por defecto)"}},
               "required": ["out_path"]}, access={"write"}, dangerous=True)
    async def compose_manga_page(out_path: str, ctx=None, rows: int = 2,
                                 cols: int = 2, prompts: list | None = None,
                                 layout: str = "grid", order: str = "rtl"):
        from .manga import ReadingOrder, compose_page, dramatic_page, grid_page
        ro = ReadingOrder.RTL if order == "rtl" else ReadingOrder.LTR
        prompts = prompts or []
        spec = (dramatic_page(prompts, order=ro) if layout == "dramatic"
                else grid_page(rows, cols, prompts, order=ro))
        problems = spec.validate()
        if problems:
            return ToolResult(False, "", error="; ".join(problems))
        out = ctx.resolve(out_path) if ctx else Path(out_path)
        if ctx is not None:
            ctx.get_journal().record(out, "create", tool="compose_manga_page")

        with tempfile.TemporaryDirectory(dir=ctx.cwd if ctx else None) as tmpd:
            tmp_out = Path(tmpd) / out.name
            report = await compose_page(spec, tmp_out)
            if report.get("ok"):
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(tmp_out, out)
                report["path"] = str(out)

        lines = [f"página: {report.get('path')}",
                 f"viñetas: {report.get('panels')} · "
                 f"generadas: {report.get('generated')} · "
                 f"lectura: {report.get('reading_order')}"]
        if report.get("problems"):
            lines.append("problemas: " + "; ".join(report["problems"]))
        return ToolResult(report.get("ok", False), "\n".join(lines),
                          error=None if report.get("ok")
                          else "; ".join(report.get("problems", [])))

    @reg.tool("validate_manga_layout",
              "Comprueba una composición (solapes, huecos, viñetas fuera de "
              "página) SIN generar dibujos. Barato: evita gastar cuota en una "
              "página mal montada.",
              {"type": "object", "properties": {
                  "rows": {"type": "integer"}, "cols": {"type": "integer"},
                  "layout": {"type": "string", "enum": ["grid", "dramatic"]}},
               "required": ["rows", "cols"]}, access={"read"})
    def validate_manga_layout(rows: int, cols: int, layout: str = "grid"):
        from .manga import dramatic_page, grid_page
        spec = dramatic_page() if layout == "dramatic" else grid_page(rows, cols)
        problems = spec.validate()
        seq = [f"({p.row},{p.col})" for p in spec.reading_sequence()]
        body = (f"{len(spec.panels)} viñetas, lectura {spec.order.value}\n"
                f"orden: {' -> '.join(seq)}")
        if problems:
            return ToolResult(False, body, error="; ".join(problems))
        return ToolResult(True, body + "\ncomposición válida")

    @reg.tool("studio_backends",
              "Qué se puede generar y observar en esta máquina.",
              {"type": "object", "properties": {}}, access={"read"})
    def studio_backends():
        from .artifacts import backends_report
        return ToolResult(True, backends_report())

    @reg.tool("entregar_artefacto",
              "Fabrica y entrega al Escritorio del usuario el contenido final "
              "de la tarea: une los bloques ```python, los verifica con el "
              "guardián GUI, empaqueta a .exe si es un juego o ventana (pygame, "
              "tkinter, turtle) y copia el resultado con hash SHA-256 y evento "
              "swarm.artefacto_listo. Solo sobre una propuesta final ya "
              "verificada por Casper.",
              {"type": "object", "properties": {
                  "nombre": {"type": "string",
                             "description": "nombre del archivo, p.ej. tetris.exe"},
                  "codigo": {"type": "string",
                             "description": "propuesta final con bloques ```python"},
                  "empaquetar": {"type": "boolean",
                                 "description": "True fuerza .exe; False fuerza "
                                                ".py; sin valor, la heurística "
                                                "de GUI decide"}},
               "required": ["nombre", "codigo"]},
              access={"write", "exec"}, dangerous=True)
    async def entregar_artefacto(nombre: str, codigo: str, ctx=None,
                                 empaquetar: bool | None = None):
        from .entrega import fabricar_y_entregar
        informe = await fabricar_y_entregar(
            codigo, nombre=nombre,
            task_id=getattr(ctx, "task_id", "") if ctx else "",
            bus=getattr(ctx, "bus", None) if ctx else None,
            empaquetar=empaquetar)
        if not informe.ok:
            return ToolResult(False, "", error=informe.motivo)
        cuerpo = (f"{informe.tipo} entregado en {informe.destino}:\n"
                  f"  archivo: {informe.ruta}\n"
                  f"  tamaño:  {informe.bytes_} bytes\n"
                  f"  sha256:  {informe.sha256}\n"
                  f"pasos:\n  " + "\n  ".join(informe.pasos))
        return ToolResult(
            True, cuerpo,
            meta={"ruta": str(informe.ruta), "sha256": informe.sha256,
                  "tipo": informe.tipo, "destino": informe.destino})

    # ------------------------------------------------------------------ §5.5

    # Presets en lugar de ancho/alto/fps sueltos. Tres motivos: la línea del
    # catálogo baja de 224 a ~130 caracteres, elegir "vertical" es más fácil
    # de acertar que recordar que el manga va en 1080x1920, y no hay forma de
    # pedir dimensiones impares, que H.264 rechaza.
    FORMATOS = {
        "horizontal": (1920, 1080, 30),   # informes, demos, tutoriales
        "vertical":   (1080, 1920, 30),   # manga y móvil
        "cuadrado":   (1080, 1080, 30),
        "rapido":     (640, 360, 24),     # pruebas: renderiza en segundos
    }

    @reg.tool("render_animatic",
              "Monta imágenes en vídeo con zoom Ken Burns y transiciones, y "
              "lo inspecciona. Para manga, informes y demos.",
              {"type": "object", "properties": {
                  "images": {"type": "array", "items": {"type": "string"}},
                  "out_path": {"type": "string"},
                  "seconds_each": {"type": "number"},
                  "format": {"type": "string",
                             "enum": sorted(FORMATOS)},
                  "audio": {"type": "string"}},
               "required": ["images", "out_path"]}, access={"write"})
    async def render_animatic(images: list, out_path: str, ctx=None,
                              seconds_each: float = 3.0,
                              format: str = "horizontal", audio: str = "",
                              crossfade: float = 0.5, ken_burns: bool = True):
        from .video import Slide, VideoSpec, render_slideshow
        if format not in FORMATOS:
            return ToolResult(
                False, "", error=f"formato '{format}' desconocido. "
                f"Disponibles: {', '.join(sorted(FORMATOS))}")
        ancho, alto, fps = FORMATOS[format]
        rutas = [str(ctx.resolve(i)) if ctx else str(i) for i in images]
        spec = VideoSpec(
            slides=[Slide(r, float(seconds_each)) for r in rutas],
            width=ancho, height=alto, fps=fps,
            crossfade=float(crossfade), ken_burns=bool(ken_burns),
            audio=str(ctx.resolve(audio)) if (audio and ctx) else audio)
        destino = ctx.resolve(out_path) if ctx else Path(out_path)
        if ctx and getattr(ctx, "journal", None):
            ctx.journal.record(destino, "create", tool="render_animatic")

        with tempfile.TemporaryDirectory(dir=ctx.cwd if ctx else None) as tmpd:
            tmp_out = Path(tmpd) / destino.name
            obs = await render_slideshow(spec, tmp_out)
            if obs.ok:
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(tmp_out, destino)

        return ToolResult(obs.ok, obs.render(),
                          error=None if obs.ok else "; ".join(obs.problems),
                          meta={"path": str(destino), "screenshot": obs.screenshot})

    @reg.tool("record_program",
              "Graba en vídeo un programa gráfico en ejecución y lo revisa. "
              "Ver treinta fotogramas dice si se mueve o se congela.",
              {"type": "object", "properties": {
                  "path": {"type": "string"},
                  "out_path": {"type": "string"},
                  "seconds": {"type": "number"},
                  "fps": {"type": "integer"},
                  "entry": {"type": "string"}},
               "required": ["path", "out_path"]}, access={"exec", "write"})
    async def record_program(path: str, out_path: str, ctx=None,
                             seconds: float = 6.0, fps: int = 20,
                             entry: str = "main.py"):
        from .video import capture_program
        origen = ctx.resolve(path) if ctx else Path(path)
        destino = ctx.resolve(out_path) if ctx else Path(out_path)
        if ctx and getattr(ctx, "journal", None):
            ctx.journal.record(destino, "create", tool="record_program")

        with tempfile.TemporaryDirectory(dir=ctx.cwd if ctx else None) as tmpd:
            tmp_out = Path(tmpd) / destino.name
            obs = await capture_program(origen, tmp_out, seconds=float(seconds),
                                        fps=int(fps), entry=entry)
            if obs.ok:
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(tmp_out, destino)

        return ToolResult(obs.ok, obs.render(),
                          error=None if obs.ok else "; ".join(obs.problems),
                          meta={"path": str(destino)})

    # ------------------------------------------------- ojos y oídos de estilo
    #
    # POR QUÉ ESTAS TRES ENTRAN AL REGISTRO Y NO SE QUEDAN EN `estilo.py`
    # ===================================================================
    # Regla 3 del proyecto: cada capacidad tiene que poder invocarse desde la
    # interfaz. Un medidor que solo puedo llamar yo desde fuera no le sirve de
    # nada al enjambre — y el objetivo declarado es que el sistema haga sin
    # supervisión lo mismo que se hace supervisándolo.
    #
    # Son tres y no una porque el bucle tiene tres momentos distintos: medir
    # la referencia, congelarla en biblia, y juzgar cada corte contra ella.
    # Fundirlas obligaría a volver a medir la referencia en cada juicio, que
    # es lento y —peor— permitiría que la vara de medir cambiara entre
    # comparaciones.

    @reg.tool("medir_estilo",
              "Mide la dirección artística de un vídeo con una máquina, no "
              "con una opinión: relación de aspecto real de la imagen, "
              "cortes y duración media de plano, si la cámara se mueve o "
              "está clavada, paleta, y del audio la envolvente, el silencio "
              "y la banda de voz. Declara explícitamente lo que NO ha "
              "podido medir.",
              {"type": "object", "properties": {
                  "path": {"type": "string"},
                  "procedencia": {
                      "type": "string", "enum": ["obra", "trailer", "generado"],
                      "description": "de un tráiler no vale la duración de "
                                     "plano: la corta el montador del tráiler"}},
               "required": ["path"]}, access={"read", "exec"})
    async def medir_estilo(path: str, ctx=None, procedencia: str = "obra"):
        from .estilo import medir
        p = ctx.resolve(path) if ctx else Path(path)
        m = await medir(p, procedencia=procedencia)
        lineas = [m.render()]
        lineas += [f"  · {e}" for e in m.evidencia]
        if m.no_medido:
            lineas.append("SIN MEDIR (no es lo mismo que correcto):")
            lineas += [f"  · {s}" for s in m.no_medido]
        # `ok` es «se midió algo», no «el vídeo está bien». Un vídeo horrible
        # se mide perfectamente; el juicio es de `juzgar_estilo`.
        hubo = m.aspecto is not None or m.tiene_audio
        return ToolResult(hubo, "\n".join(lineas),
                          error=None if hubo else "; ".join(m.no_medido),
                          meta={"medida": m.to_dict()})

    @reg.tool("biblia_de_estilo",
              "Convierte la medida de un vídeo de REFERENCIA en la biblia de "
              "estilo del encargo y la guarda en JSON. Los números salen del "
              "fichero, no de la opinión de nadie.",
              {"type": "object", "properties": {
                  "referencia": {"type": "string"},
                  "out_path": {"type": "string"},
                  "nombre": {"type": "string"},
                  "procedencia": {"type": "string",
                                  "enum": ["obra", "trailer", "generado"]},
                  "holgura": {"type": "number",
                              "description": "desvío admitido, en fracción "
                                             "del propio valor (0.15 = 15%)"}},
               "required": ["referencia", "out_path"]},
              access={"read", "write", "exec"}, dangerous=True)
    async def biblia_de_estilo(referencia: str, out_path: str, ctx=None,
                               nombre: str = "referencia",
                               procedencia: str = "obra",
                               holgura: float = 0.15):
        from .estilo import BibliaDeEstilo, medir
        origen = ctx.resolve(referencia) if ctx else Path(referencia)
        destino = ctx.resolve(out_path) if ctx else Path(out_path)
        m = await medir(origen, procedencia=procedencia)
        if m.aspecto is None:
            return ToolResult(
                False, "no se pudo medir la referencia",
                error="; ".join(m.no_medido) or "sin medidas visuales")
        b = BibliaDeEstilo.desde(m, nombre=nombre, holgura=float(holgura))
        if ctx and getattr(ctx, "journal", None):
            ctx.journal.record(destino, "create", tool="biblia_de_estilo")
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(b.to_json(), encoding="utf-8", newline="\n")
        ejes = ", ".join(f"{t.eje}={t.objetivo:.4g}±{t.margen:.3g}"
                         for t in b.tolerancias)
        aviso = ""
        if procedencia == "trailer":
            aviso = ("\nNOTA: procedencia tráiler. La duración de plano y las "
                     "medidas de mezcla NO entran: las decide el montador del "
                     "tráiler, no el director.")
        return ToolResult(
            True,
            f"biblia '{nombre}' con {len(b.tolerancias)} ejes -> {destino}\n"
            f"{ejes}{aviso}",
            meta={"path": str(destino), "ejes": len(b.tolerancias)})

    @reg.tool("juzgar_estilo",
              "Mide un vídeo generado y lo enfrenta a una biblia de estilo "
              "guardada. Devuelve qué ejes cumplen, cuáles no y en qué "
              "dirección hay que corregir. Un eje que no se pudo medir NO "
              "aprueba por omisión.",
              {"type": "object", "properties": {
                  "path": {"type": "string"},
                  "biblia": {"type": "string"}},
               "required": ["path", "biblia"]}, access={"read", "exec"})
    async def juzgar_estilo(path: str, biblia: str, ctx=None):
        from .estilo import BibliaDeEstilo, Desvio, Tolerancia, compara, medir
        p = ctx.resolve(path) if ctx else Path(path)
        bp = ctx.resolve(biblia) if ctx else Path(biblia)
        if not bp.exists():
            return ToolResult(False, "", error=f"no existe la biblia {bp}")
        try:
            crudo = json.loads(bp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            return ToolResult(False, "", error=f"biblia ilegible: {e}")
        b = BibliaDeEstilo(
            nombre=crudo.get("nombre", ""), origen=crudo.get("origen", ""),
            procedencia=crudo.get("procedencia", "desconocida"),
            tolerancias=[Tolerancia(**t) for t in crudo.get("tolerancias", [])])
        m = await medir(p, procedencia="generado")
        v = compara(m, b)
        cuerpo = [v.render()]

        # Los ejes que fallan por MUCHO se sacan aparte. Una lista plana de
        # incumplimientos trata igual «el aspecto se pasó un 2%» que «la
        # cámara se mueve seis veces más de lo permitido», y la siguiente
        # pasada se gasta arreglando lo barato mientras lo grave sigue igual.
        def _gravedad(d: Desvio) -> float:
            if d.obtenido is None or not d.margen:
                return float("inf")
            return abs(d.obtenido - d.objetivo) / d.margen

        graves = sorted(v.incumplidos, key=_gravedad, reverse=True)[:3]
        if not v.aprueba:
            if graves:
                cuerpo.append("\nLO MÁS GRAVE PRIMERO:")
                cuerpo += [
                    f"  · {d.eje}: se pasa {_gravedad(d):.1f}x del margen"
                    for d in graves]
            cuerpo.append("\nQUÉ CORREGIR EN LA SIGUIENTE PASADA:")
            cuerpo += [f"  - {f}" for f in v.lista_para_reintento()]
            cuerpo += [f"  - sin juzgar: {s}" for s in v.sin_juzgar]
        return ToolResult(
            v.aprueba, "\n".join(cuerpo),
            error=None if v.aprueba else
            f"{len(v.incumplidos)} ejes incumplidos, "
            f"{len(v.sin_juzgar)} sin juzgar",
            meta={"aprueba": v.aprueba,
                  "incumplidos": [d.eje for d in v.incumplidos],
                  "reintento": v.lista_para_reintento()})

    return reg
