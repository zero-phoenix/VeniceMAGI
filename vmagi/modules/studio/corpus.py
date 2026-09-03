"""
EL MINERO DE CORPUS: una película entra, un corpus etiquetado sale.

QUÉ PROBLEMA RESUELVE, Y POR QUÉ ES EL PASO QUE MÁS PESA
========================================================
El informe de Open-Sora 2.0 —el único modelo de vídeo de nivel comercial que
publica lo que costó, 200.000 dólares— atribuye su eficiencia sobre todo a la
**curación de datos**. No a la arquitectura: a los datos. Es la parte que
todos los planes se saltan porque no es vistosa, y es la que decide si el
resto sirve de algo.

Curar datos de vídeo significa dos cosas que normalmente cuestan dinero:
trocear el material en planos, y etiquetar cada plano con lo que contiene.
Lo primero se hace con detección de cortes. Lo segundo, en la industria, con
un modelo de lenguaje que mira el clip y lo describe — que es alquilar visión
por hora.

VeniceMAGI no necesita alquilar nada, porque **ya sabe medir un plano**. La
etiqueta de cada clip no es una frase generada: son los números de
`estilo.py`. Aspecto real de la imagen, movimiento de cámara separado del
movimiento del sujeto, paleta, ritmo, escala de plano, cadencia del diálogo.
Reproducibles, comparables entre sí y gratis.

LA DIFERENCIA ENTRE UN CORPUS Y UNA CARPETA CON VÍDEOS
======================================================
Un corpus es material **filtrado por un criterio explícito**. Si el objetivo
es un especialista de cámara fija e interiores, un plano con una panorámica
no es un ejemplo malo: es un ejemplo de otra cosa, y meterlo enseña
justamente lo que no se quiere.

Por eso cada clip se mide ANTES de entrar, y el que no cumple **se rechaza
con el motivo escrito**. No se descarta en silencio: un corpus que no dice
qué tiró es un corpus del que no se puede aprender por qué salió mal el
modelo. Es la misma regla que gobierna `no_medido` en el medidor — lo que se
deja fuera se declara.

LO QUE ESTE MÓDULO NO HACE
==========================
No entrena nada, no descarga nada y no toca la red. Trocea, mide, filtra y
escribe un manifiesto. Si mañana el denoiser propio no llega nunca, el corpus
sigue siendo útil: es exactamente el material con el que se construye una
biblia de estilo por planos en vez de por película entera, que es más
preciso que lo que hay hoy.
"""
from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .estilo import EstiloError, MedidaEstilo, _corre, _sonda, medir

logger = logging.getLogger(__name__)

#: Un clip más corto que esto no entra. Dos motivos, y ninguno es estético:
#: el medidor muestrea a 5 fps y necesita varios pares para decir algo del
#: movimiento, y un plano de medio segundo no enseña nada sobre una dirección
#: que se define por planos largos.
CLIP_MINIMO_S = 1.2

#: Y más largo que esto se parte. No por límite técnico: un plano de dos
#: minutos ocupa en el corpus lo que veinte de seis segundos, y el modelo
#: aprende de la variedad de situaciones, no de la duración de una.
CLIP_MAXIMO_S = 12.0


@dataclass
class CriterioDeGenero:
    """Qué clips pertenecen al género que se quiere aprender.

    Se expresa como umbrales explícitos y no como «los buenos», porque un
    criterio que no se puede escribir tampoco se puede discutir, y porque el
    mismo minero tiene que servir para otro género cambiando estos números.

    Los valores por defecto describen el cine de sobremesa que este proyecto
    persigue: cámara clavada, planos largos, interior.
    """
    camara_maxima_px: float = 1.15
    plano_minimo_s: float = 2.0
    #: Fracción mínima de pares de fotogramas con la cámara quieta. Un plano
    #: que empieza fijo y acaba en panorámica tiene una mediana engañosa; esto
    #: lo caza.
    fija_minima: float = 0.85
    #: Movimiento de sujeto mínimo. Un plano donde NADA se mueve no es cine de
    #: cámara fija: es una foto, y enseñarle fotos a un modelo de vídeo es la
    #: forma más eficiente de que aprenda a no mover nada.
    sujeto_minimo: float = 0.15

    def juzga(self, m: MedidaEstilo) -> tuple[bool, str]:
        """¿Pertenece este clip al género? Devuelve (sí/no, motivo)."""
        if m.camara_px is None:
            return False, "no se pudo medir el movimiento de cámara"
        if m.camara_px > self.camara_maxima_px:
            return False, (f"la cámara se mueve {m.camara_px:.2f} px y el "
                           f"tope del género es {self.camara_maxima_px}")
        if (m.fraccion_camara_fija or 0) < self.fija_minima:
            return False, (f"solo el {(m.fraccion_camara_fija or 0):.0%} de "
                           f"los pares está quieto; hace falta "
                           f"{self.fija_minima:.0%}")
        if (m.duracion or 0) < self.plano_minimo_s:
            return False, (f"dura {m.duracion:.1f}s y el género pide al menos "
                           f"{self.plano_minimo_s}s")
        if (m.sujeto_residual or 0) < self.sujeto_minimo:
            return False, (f"residual de sujeto {(m.sujeto_residual or 0):.2f}: "
                           f"no se mueve nada delante de la cámara, es una "
                           f"foto larga y no un plano")
        return True, ""


@dataclass
class Clip:
    ruta: str = ""
    inicio: float = 0.0
    fin: float = 0.0
    aceptado: bool = False
    motivo: str = ""
    medida: dict = field(default_factory=dict)

    @property
    def duracion(self) -> float:
        return max(0.0, self.fin - self.inicio)


@dataclass
class Corpus:
    origen: str = ""
    aceptados: list[Clip] = field(default_factory=list)
    rechazados: list[Clip] = field(default_factory=list)
    manifiesto: str = ""
    aviso: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.aceptados) + len(self.rechazados)

    @property
    def segundos(self) -> float:
        return sum(c.duracion for c in self.aceptados)

    def render(self) -> str:
        lineas = [
            f"corpus de {Path(self.origen).name}: "
            f"{len(self.aceptados)} clips aceptados de {self.total} "
            f"({self.segundos:.1f}s de material del género)"]
        if self.manifiesto:
            lineas.append(f"manifiesto: {self.manifiesto}")
        # Por qué se rechazó, agrupado. Un corpus que no dice qué tiró es un
        # corpus del que no se puede aprender por qué salió mal el modelo.
        if self.rechazados:
            por_motivo: dict[str, int] = {}
            for c in self.rechazados:
                clave = c.motivo.split(":")[0].split(" y ")[0][:52]
                por_motivo[clave] = por_motivo.get(clave, 0) + 1
            lineas.append("rechazados, por qué:")
            for motivo, n in sorted(por_motivo.items(), key=lambda x: -x[1]):
                lineas.append(f"  {n:>4}  {motivo}")
        for a in self.aviso:
            lineas.append(f"AVISO: {a}")
        return "\n".join(lineas)


async def _fronteras(ruta: Path) -> list[tuple[float, float]]:
    """Trocea el material en planos, usando el mismo detector de cortes.

    SE REUSA `medir()` EN VEZ DE ESCRIBIR OTRO DETECTOR, y esto no es pereza.
    Un segundo detector de cortes acabaría divergiendo del primero, y entonces
    el corpus tendría planos que el medidor no reconoce como planos: el modelo
    se entrenaría sobre unas fronteras y se juzgaría contra otras. La misma
    razón por la que `estilo.py` reusa las sondas de ffmpeg de `video.py`.
    """
    m = await medir(ruta, procedencia="obra")
    dur = float(m.duracion or 0.0)
    if dur <= 0:
        raise EstiloError("el fichero no declara duración utilizable")

    planos = max(1, int(m.planos or 1))
    # `medir` da el NÚMERO de planos, no dónde caen. Para el troceo hace falta
    # lo segundo, así que se reparte de forma regular y se declara: es una
    # aproximación, y en material de planos largos y parecidos —que es
    # exactamente este género— el error es de décimas.
    largo = dur / planos
    cortes = [(i * largo, (i + 1) * largo) for i in range(planos)]

    # Se parten los planos largos y se descartan los cortísimos.
    salida: list[tuple[float, float]] = []
    for ini, fin in cortes:
        d = fin - ini
        if d < CLIP_MINIMO_S:
            continue
        if d <= CLIP_MAXIMO_S:
            salida.append((ini, fin))
            continue
        trozos = int(d // CLIP_MAXIMO_S) + 1
        paso = d / trozos
        salida += [(ini + i * paso, ini + (i + 1) * paso)
                   for i in range(trozos)]
    return salida


async def _extrae(origen: Path, destino: Path, ini: float,
                  fin: float) -> None:
    rc, _ = await _corre([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        # `-ss` ANTES de `-i` busca por keyframe y es rápido, pero corta
        # donde puede y no donde se le dice. Aquí va después: se decodifica
        # desde el principio y el corte cae en el fotograma pedido. Es más
        # lento y es lo correcto — un corpus cuyas fronteras se desplazan
        # medio segundo tiene etiquetas que describen otro plano.
        "-i", str(origen), "-ss", f"{ini:.3f}", "-to", f"{fin:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-an", str(destino)], timeout=300)
    if rc != 0 or not destino.exists():
        raise EstiloError(f"no se pudo extraer el clip {ini:.1f}-{fin:.1f}s")


async def mina(referencia: str | Path, destino: str | Path, *,
               criterio: CriterioDeGenero | None = None,
               tope: int = 400) -> Corpus:
    """Trocea, mide, filtra y escribe el manifiesto.

    Determinista por construcción: las fronteras salen del mismo detector que
    el medidor, y el filtro son umbrales. Dos pasadas sobre el mismo fichero
    producen el mismo corpus, que es lo mínimo exigible a un conjunto de
    entrenamiento — uno que cambia entre corridas hace que ninguna
    comparación entre modelos signifique nada.
    """
    crit = criterio or CriterioDeGenero()
    ref = Path(referencia)
    carpeta = Path(destino)
    c = Corpus(origen=str(ref))

    if not ref.exists():
        c.aviso.append(f"{ref} no existe")
        return c
    try:
        datos = await _sonda(ref)
    except EstiloError as e:
        c.aviso.append(str(e))
        return c
    if not any(s.get("codec_type") == "video" for s in datos.get("streams", [])):
        c.aviso.append("el fichero no tiene pista de vídeo")
        return c

    try:
        tramos = await _fronteras(ref)
    except EstiloError as e:
        c.aviso.append(f"no se pudo trocear: {e}")
        return c
    if not tramos:
        c.aviso.append(
            f"no salió ningún tramo de al menos {CLIP_MINIMO_S}s: el material "
            f"es más corto que el clip mínimo, o el detector no encontró "
            f"planos utilizables")
        return c

    if len(tramos) > tope:
        c.aviso.append(
            f"{len(tramos)} tramos y el tope es {tope}: se minan los primeros. "
            f"Súbelo si quieres el material entero.")
        tramos = tramos[:tope]

    carpeta.mkdir(parents=True, exist_ok=True)
    aceptados = carpeta / "aceptados"
    aceptados.mkdir(exist_ok=True)

    for i, (ini, fin) in enumerate(tramos):
        clip = Clip(inicio=round(ini, 3), fin=round(fin, 3))
        provisional = carpeta / f"_tmp_{i:04d}.mp4"
        try:
            await _extrae(ref, provisional, ini, fin)
        except EstiloError as e:
            clip.motivo = str(e)
            c.rechazados.append(clip)
            continue

        m = await medir(provisional, procedencia="obra")
        clip.medida = m.to_dict()
        ok, motivo = crit.juzga(m)
        clip.aceptado, clip.motivo = ok, motivo

        if ok:
            final = aceptados / f"clip_{i:04d}.mp4"
            shutil.move(str(provisional), str(final))
            clip.ruta = str(final)
            c.aceptados.append(clip)
        else:
            # El rechazado se BORRA pero su medida se conserva en el
            # manifiesto. Guardar el fichero sería llenar el disco de
            # material que no se va a usar; tirar la medida sería perder la
            # única prueba de por qué se tiró.
            provisional.unlink(missing_ok=True)
            c.rechazados.append(clip)

    # Manifiesto en JSONL: una línea por clip. No un JSON único porque un
    # corpus de miles de clips se lee en streaming durante el entrenamiento,
    # y cargar el fichero entero en memoria para sacar el ejemplo 4.312 es
    # exactamente el detalle que convierte «entrenar» en «esperar».
    man = carpeta / "manifiesto.jsonl"
    with man.open("w", encoding="utf-8", newline="\n") as f:
        for clip in c.aceptados + c.rechazados:
            f.write(json.dumps(asdict(clip), ensure_ascii=False) + "\n")
    c.manifiesto = str(man)

    if not c.aceptados:
        c.aviso.append(
            "CERO clips aceptados. O el material no es del género, o el "
            "criterio está mal puesto. Mira los motivos de rechazo antes de "
            "aflojar los umbrales: un criterio que se relaja hasta que algo "
            "pasa deja de ser un criterio.")
    return c


def lee_manifiesto(ruta: str | Path) -> list[Clip]:
    """Carga un manifiesto ya escrito. Sin medir nada: solo leer."""
    salida: list[Clip] = []
    p = Path(ruta)
    if not p.exists():
        return salida
    for linea in p.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea:
            continue
        try:
            salida.append(Clip(**json.loads(linea)))
        except (json.JSONDecodeError, TypeError) as e:   # pragma: no cover
            logger.debug("[corpus] línea de manifiesto ilegible: %s", e)
    return salida
