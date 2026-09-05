"""
Las herramientas de ESTILO: medir, juzgar, buscar y auditar la dirección
artística de un vídeo.

POR QUÉ VIVEN APARTE DE `tools.py`
=================================
`tools.py` nació siendo el registro de la fábrica de artefactos —encargar una
imagen, arrancar un juego, componer una página de manga— y se le fueron
colgando encima las nueve herramientas del taller de cine hasta pasar de las
ochocientas líneas. El trinquete lo cazó, y el trinquete tenía razón por el
motivo que dice su mensaje y no por el número: son DOS subsistemas. Uno
fabrica cosas; el otro las mide contra una biblia de estilo. Comparten el
registro y nada más.

La frontera es la misma que separa `estilo.py` de `biblia.py`: lo que produce
por un lado, lo que juzga por el otro.
"""
from __future__ import annotations

import json
from pathlib import Path

from ...core.tools.registry import ToolRegistry, ToolResult


def _carga_biblia(bp: Path):
    """Lee una biblia de estilo de disco. Devuelve (biblia, error).

    Existía copiada dentro de tres herramientas, con las mismas nueve líneas
    y los mismos dos `except`. La lectura del JSON vive ahora en
    `BibliaDeEstilo.desde_json` —pura, comprobable sin disco— y esto solo
    pone el fichero y traduce los fallos a mensajes.
    """
    from .biblia import BibliaDeEstilo
    if not bp.exists():
        return None, f"no existe la biblia {bp}"
    try:
        return BibliaDeEstilo.desde_json(bp.read_text(encoding="utf-8")), ""
    except (OSError, json.JSONDecodeError, TypeError) as e:
        return None, f"biblia ilegible: {e}"


def register_style_tools(reg: ToolRegistry) -> ToolRegistry:

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
                      "type": "string",
                      "enum": ["obra", "trailer", "generado", "sintetica"],
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

    @reg.tool("animatica_hasta_cumplir",
              "Monta una animática con las imágenes dadas, la MIDE contra una "
              "biblia de estilo y la vuelve a montar corrigiendo lo que falló, "
              "hasta que cumpla o hasta que deje de mejorar. Cierra el bucle "
              "sin key, sin login y sin gastar ración.",
              {"type": "object", "properties": {
                  "imagenes": {"type": "array", "items": {"type": "string"}},
                  "biblia": {"type": "string"},
                  "out_path": {"type": "string"},
                  "encargo": {"type": "string"},
                  "segundos_por_plano": {"type": "number"}},
               "required": ["imagenes", "biblia", "out_path", "encargo"]},
              access={"read", "write", "exec"}, dangerous=True)
    async def animatica_hasta_cumplir(imagenes: list, biblia: str,
                                      out_path: str, encargo: str, ctx=None,
                                      segundos_por_plano: float = 5.0):
        """El bucle cerrado sobre el único generador que hoy existe sin key.

        Las correcciones no son decorativas: cada eje incumplido mueve un
        parámetro concreto del montaje. Si la cámara se mueve de más, se apaga
        el Ken Burns —que es exactamente lo que la mueve—; si los planos duran
        poco, se alargan. Un bucle que reintenta con los mismos parámetros no
        es un bucle, es la misma pasada cuatro veces.
        """
        from .bucle import rueda_hasta_cumplir
        from .video import Slide, VideoSpec, render_slideshow

        destino = ctx.resolve(out_path) if ctx else Path(out_path)
        bp = ctx.resolve(biblia) if ctx else Path(biblia)
        rutas = [str(ctx.resolve(i) if ctx else Path(i)) for i in imagenes]
        b, err = _carga_biblia(bp)
        if b is None:
            return ToolResult(False, "", error=err)

        if ctx and getattr(ctx, "journal", None):
            ctx.journal.record(destino, "create", tool="animatica_hasta_cumplir")
        destino.parent.mkdir(parents=True, exist_ok=True)

        # Las reglas y la siembra viven en `reglas.py`: son funciones puras
        # sobre el mismo `Genoma` que usa la búsqueda evolutiva. Estaban aquí
        # dentro, encima de un diccionario suelto, y eso las dejaba sin poder
        # probar (hacía falta ffmpeg para comprobar un `if`) y sin poder
        # comparar contra nada.
        from .busqueda import Genoma
        from .reglas import aplica_reglas, describe, siembra_desde_biblia

        genoma, sembrado = siembra_desde_biblia(
            b, Genoma(segundos_plano=float(segundos_por_plano), zoom=0.08))
        estado = {"g": genoma}

        async def generar(version: int, correcciones: list):
            estado["g"] = aplica_reglas(estado["g"], correcciones)
            g = estado["g"]
            spec = VideoSpec(
                slides=[Slide(r, g.segundos_plano) for r in rutas],
                ken_burns=g.ken_burns, grado=g.grado)
            obs = await render_slideshow(spec, destino)
            return destino if obs.ok else None

        r = await rueda_hasta_cumplir(encargo, b, generar)
        cuerpo = []
        if sembrado:
            cuerpo.append("sembrado desde la biblia ANTES de la 1ª pasada:")
            cuerpo += [f"  · {s}" for s in sembrado]
        cuerpo += [r.render(),
                   f"parámetros finales: {describe(estado['g'])}"]
        if r.medida is not None and r.medida.no_medido:
            cuerpo.append("sin juzgar (fuera del contrato):")
            cuerpo += [f"  · {s}" for s in r.medida.no_medido]
        return ToolResult(r.ok, "\n".join(cuerpo),
                          error=None if r.ok else (r.motivo or r.estado),
                          meta={"estado": r.estado, "path": str(destino),
                                "pasadas": r.version,
                                "fallos_de_generacion": r.fallos_de_generacion,
                                "genero_algo": r.genero_algo,
                                "sembrado": sembrado})

    @reg.tool("minar_corpus",
              "Trocea un vídeo de referencia en planos, mide cada uno y se "
              "queda solo con los que pertenecen al género pedido. Escribe un "
              "manifiesto con la medida completa de cada clip como etiqueta, "
              "y dice qué rechazó y por qué.",
              {"type": "object", "properties": {
                  "referencia": {"type": "string"},
                  "destino": {"type": "string"},
                  "camara_maxima_px": {"type": "number"},
                  "plano_minimo_s": {"type": "number"},
                  "tope": {"type": "integer",
                           "description": "máximo de tramos a minar"}},
               "required": ["referencia", "destino"]},
              access={"read", "write", "exec"}, dangerous=True)
    async def minar_corpus(referencia: str, destino: str, ctx=None,
                           camara_maxima_px: float = 1.15,
                           plano_minimo_s: float = 2.0, tope: int = 400):
        """La curación de datos, hecha con el instrumento que ya existe.

        Etiquetar clips de vídeo cuesta dinero en cualquier otro sitio: se
        alquila un modelo con visión por hora para que describa cada uno.
        Aquí la etiqueta no es una frase generada, son los números del
        medidor — reproducibles, comparables y gratis.
        """
        from .corpus import CriterioDeGenero, mina
        ref = ctx.resolve(referencia) if ctx else Path(referencia)
        dest = ctx.resolve(destino) if ctx else Path(destino)
        if ctx and getattr(ctx, "journal", None):
            ctx.journal.record(dest, "create", tool="minar_corpus")
        crit = CriterioDeGenero(camara_maxima_px=float(camara_maxima_px),
                                plano_minimo_s=float(plano_minimo_s))
        c = await mina(ref, dest, criterio=crit, tope=int(tope))
        # `ok` es «salió corpus», no «el material era bueno». Cero aceptados
        # con los motivos escritos es un resultado informativo, no un fallo
        # de la herramienta — pero tampoco es un éxito.
        return ToolResult(
            bool(c.aceptados), c.render(),
            error=None if c.aceptados else
            "ningún clip pasó el criterio del género",
            meta={"aceptados": len(c.aceptados),
                  "rechazados": len(c.rechazados),
                  "segundos": round(c.segundos, 2),
                  "manifiesto": c.manifiesto})

    @reg.tool("auditar_medidor",
              "Fabrica un contraejemplo por cada eje de la biblia —material "
              "que DEBE suspender— y comprueba que el medidor lo suspende por "
              "ese eje. Un medidor al que nadie ataca no está medido: está "
              "descrito. Solo informa; no ajusta nada.",
              {"type": "object", "properties": {
                  "referencia": {"type": "string"},
                  "biblia": {"type": "string"},
                  "carpeta": {"type": "string",
                              "description": "dónde dejar el material adverso"}},
               "required": ["referencia", "biblia", "carpeta"]},
              access={"read", "write", "exec"}, dangerous=True)
    async def auditar_medidor(referencia: str, biblia: str, carpeta: str,
                              ctx=None):
        """La auditoría del instrumento, y es trabajo de Ritsuko.

        Audita, no arregla: fabrica el ataque, mira el veredicto y emite un
        informe. No toca el medidor ni ajusta umbrales. Un auditor con permiso
        para corregir el instrumento que audita deja de ser auditor a la
        segunda vez que lo corrige.
        """
        from .adversario import ataca
        ref = ctx.resolve(referencia) if ctx else Path(referencia)
        bp = ctx.resolve(biblia) if ctx else Path(biblia)
        dest = ctx.resolve(carpeta) if ctx else Path(carpeta)
        b, err = _carga_biblia(bp)
        if b is None:
            return ToolResult(False, "", error=err)
        if ctx and getattr(ctx, "journal", None):
            ctx.journal.record(dest, "create", tool="auditar_medidor")

        inf = await ataca(b, ref, dest)
        cuerpo = [inf.render()]
        if inf.escapados:
            cuerpo.append("\nLO QUE SE LE ESCAPÓ, y qué significa:")
            for a in inf.escapados:
                cuerpo.append(
                    f"  - {a.eje}: se fabricó {a.descripcion} y el veredicto "
                    f"NO lo suspendió por ese eje. Cualquier corte que falle "
                    f"así pasará la compuerta sin que nadie lo vea.")
        return ToolResult(
            inf.solido, "\n".join(cuerpo),
            error=None if inf.solido else
            f"{len(inf.escapados)} ejes ciegos",
            meta={"solido": inf.solido,
                  "escapados": [a.eje for a in inf.escapados],
                  "sin_ataque": inf.no_atacados,
                  "atacados": [a.eje for a in inf.ataques]})

    @reg.tool("cascaron_estado",
              "Dice qué sabe percibir esta máquina en local (escala de plano, "
              "identidad entre planos) y, si falta algo, exactamente qué "
              "fichero hace falta, cuánto pesa y dónde ponerlo.",
              {"type": "object", "properties": {}}, access={"read"})
    async def cascaron_estado(ctx=None):
        from .cascaron import informe_cascaron
        from .estilo import informe_instrumento
        inf = informe_cascaron()
        ins = informe_instrumento()
        lineas = [
            "instrumento: " + ", ".join(
                f"{k}={'sí' if v else 'NO'}" for k, v in ins.items()),
            "cascarón local: " + ", ".join(
                f"{k}={'sí' if v else 'NO'}"
                for k, v in (("cv2", inf["cv2"]), ("detector", inf["detector"]),
                             ("identidad", inf["identidad"]))),
            f"detector: {inf['detector_tipo'] or 'ninguno'}",
            f"modelos en: {inf['carpeta_modelos']}",
        ]
        faltan = list(inf["falta"])                   # type: ignore[arg-type]
        if faltan:
            lineas.append("FALTA, y así se arregla:")
            lineas += [f"  · {f}" for f in faltan]
        # `ok` es «he podido responder», no «está todo». Que falte un modelo
        # es información, no un fallo de la herramienta.
        return ToolResult(True, "\n".join(lineas),
                          meta={"instrumento": ins, "cascaron": inf})

    @reg.tool("biblia_de_estilo",
              "Convierte la medida de un vídeo de REFERENCIA en la biblia de "
              "estilo del encargo y la guarda en JSON. Los números salen del "
              "fichero, no de la opinión de nadie.",
              {"type": "object", "properties": {
                  "referencia": {"type": "string"},
                  "out_path": {"type": "string"},
                  "nombre": {"type": "string"},
                  "procedencia": {"type": "string",
                                  "enum": ["obra", "trailer", "generado", "sintetica"]},
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
        # LO QUE LA REFERENCIA NO DA DERECHO A EXIGIR se dice AQUÍ, al fabricar
        # la biblia, y no solo al usarla. Enterarse de que el objetivo de
        # duración de plano salió de un clip sin cortes después de una noche
        # de búsqueda es enterarse tarde.
        objeciones = b.avisos_de_dominio()
        if objeciones:
            aviso += ("\nOJO, ejes que esta referencia NO respalda:\n"
                      + "\n".join(f"  · {o}" for o in objeciones))
        return ToolResult(
            True,
            f"biblia '{nombre}' con {len(b.tolerancias)} ejes -> {destino}\n"
            f"{ejes}{aviso}",
            meta={"path": str(destino), "ejes": len(b.tolerancias),
                  "avisos_de_dominio": objeciones})

    @reg.tool("combinar_biblias",
              "Une varias biblias de estilo en una por INTERSECCIÓN eje a eje: "
              "se queda con lo que todas exigen a la vez. Nunca promedia, y "
              "los ejes donde dos referencias se contradicen los declara.",
              {"type": "object", "properties": {
                  "biblias": {"type": "array", "items": {"type": "string"}},
                  "out_path": {"type": "string"},
                  "nombre": {"type": "string"}},
               "required": ["biblias", "out_path"]},
              access={"read", "write"}, dangerous=True)
    async def combinar_biblias(biblias: list, out_path: str, ctx=None,
                               nombre: str = "combinada"):
        from .biblia import combina
        cargadas, fallos = [], []
        for ruta in biblias:
            bp = ctx.resolve(ruta) if ctx else Path(ruta)
            b, err = _carga_biblia(bp)
            if b is None:
                fallos.append(f"{ruta}: {err}")
            else:
                cargadas.append(b)
        if fallos:
            # NO se combina lo que se pudo leer y se ignora el resto. Una
            # biblia combinada a la que le falta una de sus fuentes es MENOS
            # estricta que la que se pidió, y no lo parece.
            return ToolResult(False, "", error="; ".join(fallos))
        if not cargadas:
            return ToolResult(False, "", error="ninguna biblia que combinar")

        fusion = combina(cargadas, nombre=nombre)
        destino = ctx.resolve(out_path) if ctx else Path(out_path)
        if ctx and getattr(ctx, "journal", None):
            ctx.journal.record(destino, "create", tool="combinar_biblias")
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(fusion.to_json(), encoding="utf-8", newline="\n")

        cuerpo = [f"biblia '{nombre}' con {len(fusion.tolerancias)} ejes de "
                  f"{len(cargadas)} referencias -> {destino}"]
        cuerpo += [f"  {t.eje} = {t.objetivo:.4g}±{t.margen:.3g}"
                   for t in fusion.tolerancias]
        if fusion.conflictos:
            cuerpo.append("\nEJES RETIRADOS POR CONTRADICCIÓN (no se promedian, "
                          "decide una persona cuál de las dos películas haces):")
            cuerpo += [f"  · {c.render()}" for c in fusion.conflictos]
        objeciones = fusion.avisos_de_dominio()
        if objeciones:
            cuerpo.append("\nOJO, ejes que el material combinado NO respalda:")
            cuerpo += [f"  · {o}" for o in objeciones]
        return ToolResult(
            True, "\n".join(cuerpo),
            meta={"path": str(destino), "ejes": len(fusion.tolerancias),
                  "conflictos": [c.eje for c in fusion.conflictos],
                  "avisos_de_dominio": objeciones})

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
        from .estilo import Desvio, compara, medir
        p = ctx.resolve(path) if ctx else Path(path)
        bp = ctx.resolve(biblia) if ctx else Path(biblia)
        b, err = _carga_biblia(bp)
        if b is None:
            return ToolResult(False, "", error=err)
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
        correcciones = v.lista_para_reintento()
        # La cabecera solo se escribe si hay algo debajo. Un «QUÉ CORREGIR EN
        # LA SIGUIENTE PASADA:» seguido de nada le dice al nodo que hay
        # trabajo pendiente y no le dice cuál — y la prueba de extremo a
        # extremo lo sacó impreso exactamente así.
        if graves:
            cuerpo.append("\nLO MÁS GRAVE PRIMERO:")
            cuerpo += [f"  · {d.eje}: se pasa {_gravedad(d):.1f}x del margen"
                       for d in graves]
        if correcciones:
            cuerpo.append("\nQUÉ CORREGIR EN LA SIGUIENTE PASADA:")
            cuerpo += [f"  - {f}" for f in correcciones]
        if v.sin_juzgar:
            cuerpo.append("\nFUERA DEL CONTRATO, sin mirar (no suspende):")
            cuerpo += [f"  - {s}" for s in v.sin_juzgar]
        return ToolResult(
            v.aprueba, "\n".join(cuerpo),
            error=None if v.aprueba else
            f"{len(v.incumplidos)} ejes incumplidos",
            meta={"aprueba": v.aprueba, "sin_dudas": v.sin_dudas,
                  "incumplidos": [d.eje for d in v.incumplidos],
                  "sin_juzgar": list(v.sin_juzgar),
                  "reintento": correcciones})

    @reg.tool("interrogar_fotograma",
              "Pregunta cosas cerradas sobre un fotograma a un perito de "
              "visión local, mezcladas con preguntas de control ya resueltas "
              "por medición: si las falla, alucina y se descarta la tanda.",
              {"type": "object", "properties": {
                  "path": {"type": "string"},
                  "preguntas": {"type": "array", "items": {"type": "string"},
                                "description": "preguntas de SÍ/NO sobre lo "
                                               "que se ve en el fotograma"},
                  "segundo": {"type": "number"}},
               "required": ["path", "preguntas"]},
              access={"read", "exec"})
    async def interrogar_fotograma(path: str, preguntas: list, ctx=None,
                                   segundo: float = 0.0):
        from .estilo import medir
        from .perito import Pregunta, disponible, interroga
        p = ctx.resolve(path) if ctx else Path(path)
        hay, quien = disponible()
        if not hay:
            # NO es un fallo de la herramienta: es la respuesta honesta a la
            # pregunta «¿qué ves aquí?» en una máquina sin ojos. Devolver
            # ok=False mandaría al enjambre a reintentar algo que no depende
            # de él.
            return ToolResult(
                True, f"no hay perito en esta máquina: {quien}",
                meta={"disponible": False, "motivo": quien})
        m = await medir(p, procedencia="generado")
        t = await interroga(
            p, m, [Pregunta(texto=str(q)) for q in preguntas],
            segundo=float(segundo))
        cabeza = ("testimonio ADMITIDO" if t.fiable
                  else "testimonio DESCARTADO")
        return ToolResult(
            True, f"{cabeza}\n{t.render()}",
            meta={"fiable": t.fiable, "modelo": t.modelo,
                  "controles": [f"{r.pregunta}={r.dicho}"
                                for r in t.controles],
                  "aciertos": t.aciertos,
                  "respuestas": {r.pregunta: r.dicho for r in t.utiles}})

    # POBLACIÓN Y GENERACIONES NO SE EXPONEN, y no es por ahorrar caracteres.
    # En esta máquina el único límite real es el PLAZO: la electricidad es
    # gratis y la tarjeta es suya. Un tope de generaciones obliga a adivinar de
    # antemano cuántas caben en la noche, que es precisamente la cuenta que el
    # presupuesto hace sola. El tope queda alto para que nunca sea él quien
    # pare la búsqueda.
    @reg.tool("buscar_parametros",
              "Evoluciona el montaje con el medidor como aptitud, hasta "
              "agotar el plazo. Sin gradientes ni VRAM.",
              {"type": "object", "properties": {
                  "imagenes": {"type": "array", "items": {"type": "string"}},
                  "biblia": {"type": "string"},
                  "out_dir": {"type": "string"},
                  "presupuesto_s": {"type": "number",
                                    "description": "plazo en segundos; es lo "
                                                   "que de verdad limita"},
                  "auditado": {"type": "boolean",
                               "description": "pon true SOLO si acabas de "
                                              "pasar auditar_medidor sobre "
                                              "esta misma biblia"},
                  "semilla": {"type": "integer"}},
               "required": ["imagenes", "biblia", "out_dir"]},
              access={"read", "write", "exec"}, dangerous=True)
    async def buscar_parametros(imagenes: list, biblia: str, out_dir: str,
                                ctx=None, poblacion: int = 10,
                                generaciones: int = 200,
                                presupuesto_s: float = 900.0,
                                auditado: bool = False,
                                semilla: int = 0):
        from .busqueda import ALTO_PROXY, ANCHO_PROXY, Genoma, busca
        from .video import Slide, VideoSpec, render_slideshow
        bp = ctx.resolve(biblia) if ctx else Path(biblia)
        b, err = _carga_biblia(bp)
        if b is None:
            return ToolResult(False, "", error=err)
        destino = ctx.resolve(out_dir) if ctx else Path(out_dir)
        destino.mkdir(parents=True, exist_ok=True)
        fuentes = [str(ctx.resolve(i) if ctx else Path(i)) for i in imagenes]
        if not fuentes:
            return ToolResult(False, "", error="sin imágenes no hay qué montar")

        def _spec(g: Genoma, ancho: int, alto: int) -> VideoSpec:
            return VideoSpec(
                slides=[Slide(f, g.segundos_plano) for f in fuentes],
                width=ancho, height=alto,
                ken_burns=g.ken_burns, crossfade=g.crossfade, grado=g.grado)

        async def _monta(spec: VideoSpec, salida: Path):
            if spec.validate():
                return None            # candidato inválido: no es un fallo
            if ctx and getattr(ctx, "journal", None):
                ctx.journal.record(salida, "create", tool="buscar_parametros")
            try:
                await render_slideshow(spec, salida)
            except Exception:          # noqa: BLE001
                return None
            return salida if salida.exists() else None

        async def generar(g: Genoma, idx: int):
            # PROXY. El medidor mira a 128 px de ancho: montar el candidato a
            # 1920 para que lo tire a 128 es pagar cien veces por el mismo dato.
            return await _monta(_spec(g, ANCHO_PROXY, ALTO_PROXY),
                                destino / f"cand-{idx:03d}-{g.firma}.mp4")

        f = await busca(b, generar, poblacion=int(poblacion),
                        generaciones=int(generaciones),
                        presupuesto_s=float(presupuesto_s),
                        auditado=bool(auditado), semilla=int(semilla))

        # CONFORMADO: el ganador se vuelve a montar a tamaño real. Entregar el
        # proxy sería entregar el borrador con el que se decidió, que es
        # exactamente lo que un montaje con proxies NO hace.
        conformado = None
        if f.mejor is not None:
            conformado = await _monta(_spec(f.mejor.genoma, 1920, 1080),
                                      destino / "ganador-1080.mp4")
        return ToolResult(
            f.mejor is not None,
            f.render() + (f"\nconformado a 1920x1080 -> {conformado}"
                          if conformado else ""),
            error=None if f.mejor else "ningún candidato llegó a evaluarse",
            meta={"mejor": str(conformado) if conformado else (
                      f.mejor.ruta if f.mejor else None),
                  "proxy": f.mejor.ruta if f.mejor else None,
                  "distancia": None if not f.mejor else f.mejor.distancia,
                  "evaluaciones": f.evaluaciones,
                  "historial": f.historial})

    return reg
