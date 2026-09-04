"""
EL PERITO: un testigo que MIRA, y al que se le hace contrainterrogatorio.

EL FALLO QUE ESTE MÓDULO CIERRA
===============================
`docs/AUTOMODELO.json`, afirmación «El jurado de tres IAs puede puntuar la
imagen de un corte»: **REFUTADA**. Los tres nodos del enjambre son de texto y
no ven el vídeo. Solo pueden leer lo que el medidor les cuenta, así que no son
una señal independiente — son la misma señal leída dos veces con pasos de
más. Un jurado donde tres de los cuatro miembros repiten al cuarto no es un
jurado.

Lo que hacía falta no era otro razonador: era **un testigo que hubiera estado
en la escena**. Un modelo de visión local, pequeño, que mire los píxeles y
conteste. Y su valor no está en que sea bueno —no lo es, pesa unos cientos de
megas— sino en que su error es **independiente** del error del medidor. Dos
instrumentos que se equivocan por motivos distintos valen mucho más que uno
bueno repetido.

POR QUÉ PREGUNTAS CERRADAS Y NO UNA DESCRIPCIÓN
===============================================
Un modelo pequeño al que se le pide «describe la escena» produce una frase
plausible que nadie puede comprobar, y esa frase entra en el prompt de tres
nodos que se la creen. Es la peor forma posible de introducir una alucinación:
con formato de evidencia.

Preguntas cerradas —sí/no, o una entre pocas opciones— hacen tres cosas que
una descripción no hace: se pueden contar, se pueden comparar entre
fotogramas, y **se pueden falsear**.

EL CONTRAINTERROGATORIO, QUE ES LA IDEA QUE FALTABA
===================================================
Cada tanda de preguntas lleva dentro **preguntas de control cuya respuesta ya
se sabe por medición**. Si el medidor dice que el fotograma es verde oscuro y
el perito contesta que la escena es roja y brillante, el perito está
alucinando — y su testimonio **de esa tanda entera** se descarta.

No se pregunta si el testigo es fiable: se comprueba, cada vez. Es el
principio del adversario aplicado a un testigo, y es la diferencia entre
usar un modelo de 250 MB y que ese modelo te mienta sin que te enteres.

DEGRADACIÓN
===========
Sin modelo instalado, `disponible()` devuelve False con el motivo y el jurado
vuelve a su posición honesta: los nodos juzgan el guion y el plan de planos,
que es lo que sí pueden juzgar leyendo. Nunca se inventa un testimonio.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

#: Modelos de visión que caben en esta máquina, de menor a mayor. El orden no
#: es casual: en una tarjeta de 2 GB el más grande de la lista ya roza el
#: límite, y como aquí se regala electricidad y no dinero, **el camino por
#: defecto es CPU** — lento, gratis y sin pelearse por la VRAM con nada.
MODELOS_VISION = {
    "smolvlm-256m": ("~250 MB", "el más pequeño que contesta preguntas"),
    "florence-2-base": ("~230 MB", "bueno describiendo, flojo razonando"),
    "moondream2": ("~1,9 GB", "el mejor de los que caben; roza los 2 GB"),
}

#: Umbral de la prueba de control. Por debajo de esto, el testimonio de la
#: tanda se descarta entero.
#:
#: Se exige mayoría estricta y no unanimidad: un modelo pequeño falla una de
#: cada tantas por ruido, y descartar por un solo fallo tiraría casi todo. Es
#: el mismo criterio que `deriva_es_concluyente` en `naoko.py`, y por el mismo
#: motivo: con instrumentos ruidosos, acertar una de tres es ruido normal.
CONTROL_MINIMO = 0.6


@dataclass
class Pregunta:
    """Una pregunta cerrada. Con su respuesta esperada si es de control."""
    texto: str
    opciones: tuple[str, ...] = ("sí", "no")
    #: Si no es None, esta pregunta es de CONTROL: su respuesta se conoce por
    #: medición y sirve para comprobar que el testigo no está inventando.
    esperada: str | None = None
    #: De dónde salió la respuesta esperada. Se guarda para que el informe
    #: pueda decir POR QUÉ se sabía, en vez de pedir que se le crea.
    fuente: str = ""

    @property
    def es_control(self) -> bool:
        return self.esperada is not None


@dataclass
class Respuesta:
    pregunta: str
    dicho: str = ""
    esperada: str | None = None
    acierta: bool | None = None      # None = no era de control


@dataclass
class Testimonio:
    """Lo que el perito dijo, y si se le puede creer."""
    respuestas: list[Respuesta] = field(default_factory=list)
    modelo: str = ""
    motivo: str = ""                 # por qué no hay testimonio, si no lo hay

    @property
    def controles(self) -> list[Respuesta]:
        return [r for r in self.respuestas if r.acierta is not None]

    @property
    def aciertos(self) -> int:
        return sum(1 for r in self.controles if r.acierta)

    @property
    def fiable(self) -> bool:
        """¿Se puede usar este testimonio?

        Sin preguntas de control NO es fiable, y esa es la decisión que hace
        que todo esto sirva de algo. Un testimonio sin forma de comprobarlo
        es exactamente lo que este módulo existe para no producir: una frase
        plausible con formato de evidencia.
        """
        if not self.respuestas or self.motivo:
            return False
        if not self.controles:
            return False
        return self.aciertos / len(self.controles) >= CONTROL_MINIMO

    @property
    def utiles(self) -> list[Respuesta]:
        """Las respuestas que aportan información nueva: las que NO son de
        control. Las de control ya se sabían — su trabajo era otro."""
        return [] if not self.fiable else [
            r for r in self.respuestas if r.acierta is None]

    def render(self) -> str:
        if self.motivo:
            return f"  ????  sin testimonio: {self.motivo}"
        if not self.fiable:
            if not self.controles:
                return ("  DESCARTADO  no había preguntas de control: un "
                        "testimonio que no se puede comprobar no se usa")
            return (f"  DESCARTADO  el perito falló {len(self.controles) - self.aciertos} "
                    f"de {len(self.controles)} controles: está alucinando")
        lineas = [f"  testigo: {self.modelo} · controles "
                  f"{self.aciertos}/{len(self.controles)}"]
        lineas += [f"    {r.pregunta} -> {r.dicho}" for r in self.utiles]
        return "\n".join(lineas)


#: El runtime del perito, POR NOMBRE Y NO POR `import`.
#:
#: `VeniceMAGI.spec` excluye `torch` y `transformers` del binario a propósito:
#: pesan gigas y colgaron tres compilaciones seguidas en «Looking for dynamic
#: libraries». `test_nada_de_magi_importa_lo_que_el_spec_deja_fuera` lo cazó en
#: la primera pasada de este módulo, y tenía razón — un `import torch` escrito
#: aquí, aunque estuviera dentro de un `try`, es una declaración de que el
#: paquete debería viajar dentro.
#:
#: Y no debería. El perito es una capacidad de la MÁQUINA de David, no del
#: .exe: quien instala el modelo instala también el runtime. Resolverlo por
#: nombre dice exactamente eso, y deja el .exe arrancando igual y contestando
#: «no hay perito aquí» en vez de reventar.
RUNTIME = "torch"
BIBLIOTECA = "transformers"


def _hay(modulo: str) -> bool:
    from importlib.util import find_spec
    try:
        return find_spec(modulo) is not None
    except (ImportError, ValueError):
        return False


def disponible() -> tuple[bool, str]:
    """¿Hay un perito en esta máquina? Devuelve (sí/no, motivo).

    Función explícita, como `pillow_available` y `cv2_disponible`, y por el
    mismo motivo de siempre: quien pregunta necesita distinguir «he mirado y
    no hay nadie» de «no he podido mirar».
    """
    from .cascaron import carpeta_modelos
    if not (_hay(RUNTIME) and _hay(BIBLIOTECA)):
        return False, (
            f"no hay runtime de visión instalado ({RUNTIME} + {BIBLIOTECA}). "
            f"No viajan dentro del .exe a propósito: pesan gigas. En esta "
            f"máquina se instalan aparte y el modelo va en {carpeta_modelos()}. "
            f"Sin él, el jurado solo puede juzgar el guion y el plan de "
            f"planos, que es lo que sí puede juzgar leyendo.")
    carpeta = carpeta_modelos()
    presentes = [n for n in MODELOS_VISION
                 if (carpeta / n).exists()]
    if not presentes:
        return False, (
            f"runtime listo pero no hay ningún modelo de visión en {carpeta}. "
            f"Opciones: " + ", ".join(
                f"{n} ({peso})" for n, (peso, _) in MODELOS_VISION.items()))
    return True, presentes[0]


def preguntas_de_control(medida) -> list[Pregunta]:
    """Fabrica preguntas cuya respuesta YA se conoce por medición.

    Son la trampa del contrainterrogatorio. Se derivan de cifras que el
    medidor ya tiene, así que no cuestan nada, y comprueban justo lo que un
    modelo pequeño falla cuando alucina: el color dominante, si hay
    movimiento, si el cuadro está vacío.

    NO se le dice al perito cuáles son de control. Si supiera cuáles se
    comprueban, la comprobación no comprobaría nada — que es el mismo motivo
    por el que un examen no lleva las respuestas al final.
    """
    ctrl: list[Pregunta] = []

    rgb = getattr(medida, "rgb_medio", None)
    if rgb:
        r, g, b = rgb
        dominante = "rojo" if r >= g and r >= b else (
            "verde" if g >= b else "azul")
        ctrl.append(Pregunta(
            texto="¿Qué color domina la imagen?",
            opciones=("rojo", "verde", "azul"),
            esperada=dominante,
            fuente=f"rgb medio medido {rgb}"))

    luma = getattr(medida, "luma", None)
    if luma is not None:
        ctrl.append(Pregunta(
            texto="¿La imagen es clara u oscura?",
            opciones=("clara", "oscura"),
            esperada="clara" if luma > 128 else "oscura",
            fuente=f"luma medida {luma:.0f} sobre 255"))

    sat = getattr(medida, "saturacion", None)
    if sat is not None:
        ctrl.append(Pregunta(
            texto="¿La imagen tiene colores vivos o está casi en gris?",
            opciones=("vivos", "gris"),
            esperada="gris" if sat < 0.12 else "vivos",
            fuente=f"saturación medida {sat:.3f}"))

    return ctrl


def baraja(utiles: list[Pregunta], control: list[Pregunta],
           semilla: int = 0) -> list[Pregunta]:
    """Mezcla las preguntas útiles con las de control, de forma determinista.

    Determinista y no aleatoria porque una tanda que cambia entre corridas
    hace que dos testimonios del mismo fotograma no sean comparables — la
    misma exigencia que el proyecto ya le pone al troceo de subagentes, al
    medidor y al corpus.

    Y mezcladas de verdad, no las de control al final: un modelo que atiende
    peor al final de un prompt largo fallaría los controles por posición y no
    por alucinación, y se descartaría un testimonio bueno.
    """
    todas = list(utiles) + list(control)
    if not todas:
        return []
    # Permutación determinista sencilla: se ordena por un hash estable del
    # texto más la semilla. Sin `random`, que arrastra estado global.
    import hashlib
    def clave(p: Pregunta) -> str:
        return hashlib.sha1(
            f"{semilla}:{p.texto}".encode()).hexdigest()
    return sorted(todas, key=clave)


def evalua(respuestas_crudas: dict[str, str],
           preguntas: list[Pregunta], modelo: str = "") -> Testimonio:
    """Monta el testimonio y aplica el contrainterrogatorio.

    Separado de la inferencia A PROPÓSITO, igual que `build_filtergraph` en
    `video.py`: siendo una función pura sobre un diccionario, todo el
    mecanismo —incluido el caso del perito que miente— se comprueba en un
    test sin cargar un solo modelo ni abrir un fotograma.
    """
    t = Testimonio(modelo=modelo)
    for p in preguntas:
        dicho = (respuestas_crudas.get(p.texto) or "").strip().lower()
        r = Respuesta(pregunta=p.texto, dicho=dicho, esperada=p.esperada)
        if p.es_control:
            r.acierta = dicho == (p.esperada or "").lower()
        t.respuestas.append(r)
    return t


# ------------------------------------------------------------- el fotograma

async def extrae_fotograma(ruta, segundo: float, destino) -> Path | None:
    """Saca UN fotograma a un instante concreto. Devuelve None si no pudo.

    `-ss` va DESPUÉS de `-i`, igual que en el minero: delante es rápido pero
    salta al fotograma clave anterior, y entonces el perito estaría mirando
    un fotograma distinto del que se midió. Aquí eso no es una imprecisión:
    invalida el contrainterrogatorio entero, porque los controles se
    calcularon sobre otra imagen.
    """
    from .estilo import EstiloError, _corre

    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        rc, _ = await _corre([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(ruta), "-ss", f"{max(0.0, segundo):.3f}",
            "-frames:v", "1", "-q:v", "2", str(destino)], timeout=120)
    except EstiloError:
        return None
    return destino if rc == 0 and destino.exists() else None


def _formula(preguntas: list[Pregunta]) -> str:
    """El prompt. Numerado y con las opciones a la vista, porque un modelo de
    250 MB al que se le deja contestar en prosa contesta en prosa, y entonces
    la respuesta no se puede comparar con nada."""
    lineas = ["Mira la imagen y responde SOLO con la opción elegida, "
              "una línea por pregunta, con su número delante."]
    for i, p in enumerate(preguntas, 1):
        lineas.append(f"{i}. {p.texto} ({' / '.join(p.opciones)})")
    return "\n".join(lineas)


def descifra(bruto: str, preguntas: list[Pregunta]) -> dict[str, str]:
    """Convierte lo que salió del modelo en {pregunta: opción}.

    Función pura y con nombre propio a propósito: el desciframiento de una
    salida libre es donde se cuelan los falsos positivos —un modelo que
    contesta «no es rojo» contiene la palabra «rojo»—, así que tiene que
    poder probarse sin modelo. Se busca la opción por línea numerada, y una
    línea que menciona dos opciones se descarta por ambigua en vez de
    quedarse con la primera.
    """
    fuera: dict[str, str] = {}
    lineas = [ln.strip() for ln in (bruto or "").splitlines() if ln.strip()]
    for i, p in enumerate(preguntas, 1):
        candidata = ""
        for ln in lineas:
            cabeza = ln.split(".", 1)[0].split(")", 1)[0].strip()
            if cabeza == str(i):
                candidata = ln.lower()
                break
        if not candidata and len(lineas) == len(preguntas):
            candidata = lineas[i - 1].lower()      # sin numerar, pero en orden
        if not candidata:
            continue
        vistas = [o for o in p.opciones if o.lower() in candidata]
        if len(vistas) == 1:
            fuera[p.texto] = vistas[0]
    return fuera


async def interroga(ruta, medida, preguntas: list[Pregunta], *,
                    segundo: float = 0.0, carpeta=None) -> Testimonio:
    """Interroga al perito sobre un fotograma, con contrainterrogatorio.

    Es la única puerta de entrada. Nadie llama al modelo sin controles: si se
    pudiera, alguien lo haría el día que tuviera prisa, y el testimonio sin
    comprobar entraría al prompt de los tres nodos con formato de evidencia.
    """
    hay, quien = disponible()
    if not hay:
        return Testimonio(motivo=quien)

    control = preguntas_de_control(medida)
    if not control:
        return Testimonio(motivo=(
            "la medida no trae ni color ni luz ni saturación, así que no hay "
            "con qué fabricar preguntas de control. Sin controles el "
            "testimonio no se puede comprobar, y sin comprobar no se usa."))

    from ...core.paths import cache_dir
    carpeta = carpeta or (cache_dir() / "perito")
    tanda = baraja(preguntas, control, semilla=int(segundo * 1000))
    marco = await extrae_fotograma(ruta, segundo, carpeta / "vista.jpg")
    if marco is None:
        return Testimonio(motivo=f"no se pudo extraer el fotograma a {segundo}s")

    try:
        bruto = await _pregunta(marco, _formula(tanda), quien)
    except Exception as e:                       # noqa: BLE001
        return Testimonio(motivo=f"el perito falló al mirar: {e}")

    return evalua(descifra(bruto, tanda), tanda, modelo=quien)


async def _pregunta(imagen, prompt: str, modelo: str) -> str:
    """La inferencia. En CPU y en un hilo aparte.

    En CPU **a propósito**: en una tarjeta de 2 GB, cargar aquí un modelo de
    visión es quitarle a la generación la memoria que necesita, y aquí se
    regala electricidad, no VRAM. Lento y gratis gana a rápido y bloqueante.

    Y en un hilo aparte porque `generate` es una llamada bloqueante de varios
    segundos: en el bucle de eventos congelaría la interfaz entera, que es el
    mismo motivo por el que `medir` lanza ffmpeg como subproceso.
    """
    import asyncio

    from .cascaron import carpeta_modelos

    def _trabajo() -> str:
        from importlib import import_module

        from PIL import Image

        # Por nombre, y no `from transformers import ...`, por lo que dice el
        # comentario de RUNTIME: el .spec lo excluye del binario a propósito.
        tf = import_module(BIBLIOTECA)
        ruta = str(carpeta_modelos() / modelo)
        proc = tf.AutoProcessor.from_pretrained(ruta, trust_remote_code=False)
        red = tf.AutoModelForCausalLM.from_pretrained(
            ruta, trust_remote_code=False).eval()
        with Image.open(imagen) as im:
            entradas = proc(images=im.convert("RGB"), text=prompt,
                            return_tensors="pt")
        salida = red.generate(**entradas, max_new_tokens=160, do_sample=False)
        return proc.batch_decode(salida, skip_special_tokens=True)[0]

    return await asyncio.to_thread(_trabajo)
