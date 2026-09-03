"""
El MEDIDOR DE ESTILO: ojos y oídos sobre un fichero de vídeo.

POR QUÉ EXISTE
==============
`video.py` ya mira un vídeo y caza dos fallos: el negro y el congelado. Son
los fallos de que *no haya nada*. Este módulo caza el escalón siguiente: que
haya algo, y que sea **otra cosa** de la que se pidió.

Un cortometraje puede salir perfectamente válido —se abre, dura, se mueve, no
está en negro— y no parecerse en nada a la dirección artística encargada. La
cámara se pasea cuando debía estar clavada. Los planos duran dos segundos
cuando debían durar veinte. La paleta se va al naranja cuando el encargo era
verde de jardín y madera. Nada de eso lo detecta `observe_video`, y ningún
proveedor guest puede juzgarlo porque **ninguno acepta imágenes de entrada**
(`docs/AUTOMODELO.json`, afirmación «El crítico del taller puede juzgar lo que
se ve en la imagen»: REFUTADA).

Así que se mide con una máquina. Es la regla del taller de arte llevada al
vídeo: se separa lo que MIDE una máquina de lo que juzga un modelo leyendo, y
**cuando discrepan, manda la máquina**.

EL MISMO INSTRUMENTO EN LOS DOS EXTREMOS
========================================
Esto no es un validador. Es una regla de medir. Se pasa sobre el fichero de
REFERENCIA para obtener la biblia de estilo, y se pasa sobre cada corte
GENERADO para puntuarlo. Si fueran dos instrumentos distintos, la comparación
no significaría nada: la mitad de la diferencia medida sería la diferencia
entre los instrumentos.

Por eso `medir()` no sabe nada de biblias ni de tolerancias. Devuelve números
crudos. `compara()` es quien enfrenta dos medidas, y es una función aparte y
pura.

LO QUE ESTE MÓDULO NO FINGE
===========================
* **Sin ffmpeg no mide nada** y lo dice; no devuelve ceros.
* **Sin numpy/Pillow no mira los fotogramas** y lo dice; no aprueba por
  omisión. Es exactamente el agujero que se encontró en `observe_video`
  simulando el entorno de CI: sin Pillow, un vídeo negro y congelado salía
  con `ok=True` y cero problemas.
* **No distingue un rostro.** La escala de plano (primer plano contra plano
  general) exige un detector de caras que este sistema todavía no tiene en
  local. Figura en `no_medido`, no en los resultados.
* **El movimiento se mide sobre LUMA, no sobre color.** Un objeto que se
  desplaza pero tiene la misma luminancia que el fondo es invisible para el
  estimador. No es hipotético: al calibrar este módulo, un recuadro rojo
  puro moviéndose sobre un fondo azul oscuro dio un residual de 0,013 —
  `0xFF0000` pesa 54 en luma y `0x2E3B4E` pesa 56, o sea el mismo gris. La
  medida era correcta; la pregunta estaba mal hecha. Se deja así a propósito
  (luma es lo que gobierna la percepción de movimiento y cuesta un tercio),
  pero quien lea `sujeto_residual` tiene que saber de qué habla.
* **De un tráiler NO se puede medir el montaje.** Un tráiler lo corta el
  departamento de marketing, no el director: su duración media de plano habla
  del montador del tráiler. Lo que SÍ sobrevive intacto de la película son la
  relación de aspecto, la paleta y el movimiento de cámara DENTRO de cada
  plano, porque esos planos están levantados del corte final. `medir()` marca
  la procedencia para que nadie confunda una cosa con la otra.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import shutil
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# --------------------------------------------------------------- constantes

#: Fotogramas por segundo a los que se muestrea. No es la cadencia del vídeo:
#: es la resolución temporal del instrumento, y va FIJA a propósito. Si
#: dependiera del vídeo, dos ficheros con cadencias distintas darían
#: duraciones de plano incomparables, que es justo lo que hay que comparar.
MUESTREO_FPS = 5.0

#: Lado mayor al que se reduce cada fotograma antes de analizarlo. Suficiente
#: para paleta, corte y desplazamiento global; barato para que medir dos
#: minutos no cueste dos minutos.
ANCHO_ANALISIS = 128

#: Distancia entre histogramas por encima de la cual se declara un CORTE.
#: Calibrado sobre material sintético con cortes conocidos (ver
#: tests/test_estilo.py, que genera un vídeo con N cortes exactos y exige
#: que el medidor encuentre N).
UMBRAL_CORTE = 0.38

#: Desplazamiento global máximo, en píxeles de la imagen reducida, por debajo
#: del cual la cámara se considera FIJA. No es cero: la compresión y el
#: submuestreo mueven el óptimo un píxel largo sin que nadie haya tocado el
#: trípode.
UMBRAL_CAMARA_FIJA = 1.15

#: Desplazamiento máximo que se busca. Una panorámica más rápida que esto
#: satura y se informa como saturada, en vez de devolver un número falso bajo
#: porque el óptimo cayó fuera de la ventana de búsqueda.
BUSQUEDA_MAX = 8

#: Frecuencia de muestreo del audio extraído. 16 kHz cubre la banda de la voz
#: (300-3400 Hz) con margen y pesa cuatro veces menos que 44,1.
AUDIO_HZ = 16000

#: Ventana de análisis de audio, en segundos.
AUDIO_VENTANA = 0.025


class EstiloError(RuntimeError):
    """No se pudo medir. Con el motivo, siempre."""


# ------------------------------------------------------------- disponibilidad

# Se REUSAN las de `video.py` en vez de escribir otras dos iguales. Dos
# funciones que responden a la misma pregunta acaban divergiendo —una mira el
# PATH y la otra intenta ejecutar, y un día una dice que sí y la otra que no
# sobre la misma máquina—, y además el trinquete de huérfanos las señala con
# razón: son código público que nadie llama porque ya existía.
from .video import ffmpeg_available as ffmpeg_disponible  # noqa: E402
from .video import ffprobe_available as ffprobe_disponible  # noqa: E402


def numpy_disponible() -> bool:
    """¿Se pueden hacer cuentas sobre los píxeles en esta máquina?

    Igual que `pillow_available` en `artifacts.py`, y por el mismo motivo:
    quien mide necesita distinguir «he medido y sale esto» de «no he podido
    medir». Sin la pregunta explícita, la segunda se cuela como la primera.
    """
    try:
        import numpy  # noqa: F401
        return True
    except ImportError:
        return False


def pillow_disponible() -> bool:
    try:
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        return False


def informe_instrumento() -> dict[str, bool]:
    """Qué partes del instrumento están operativas en esta máquina."""
    return {
        "ffmpeg": ffmpeg_disponible(),
        "ffprobe": ffprobe_disponible(),
        "numpy": numpy_disponible(),
        "pillow": pillow_disponible(),
    }


# ------------------------------------------------------------------ resultado

@dataclass
class MedidaEstilo:
    """Números crudos. Sin veredicto: el veredicto lo da `compara()`."""

    ruta: str = ""
    procedencia: str = "desconocida"   # "obra" | "trailer" | "generado"

    # --- ojos ---------------------------------------------------------
    ancho: int = 0
    alto: int = 0
    duracion: float = 0.0
    #: Relación de aspecto de la IMAGEN, no del contenedor. Un 1.85:1 dentro
    #: de un contenedor 4:3 con barras negras da 1.333 si se lee el
    #: contenedor y 1.85 si se miran los píxeles. Se miran los píxeles.
    aspecto: float | None = None
    aspecto_contenedor: float | None = None
    planos: int | None = None
    duracion_media_plano: float | None = None
    #: Mediana del desplazamiento global entre fotogramas consecutivos, en
    #: píxeles de la imagen reducida. Es la medida de si la cámara se mueve.
    camara_px: float | None = None
    #: Fracción de pares de fotogramas cuyo desplazamiento global está por
    #: debajo del umbral. En Kore-eda esto debería ser casi 1.
    fraccion_camara_fija: float | None = None
    #: Cambio que QUEDA tras compensar el desplazamiento global. Es el
    #: movimiento del SUJETO. La firma de una cámara fija con vida delante
    #: es camara_px ~ 0 y sujeto_residual > 0. Un plano congelado da los dos
    #: a cero, y ese es un fallo distinto que `observe_video` ya caza.
    sujeto_residual: float | None = None
    rgb_medio: tuple[int, int, int] | None = None
    luma: float | None = None
    saturacion: float | None = None
    contraste: float | None = None
    #: ESCALA DE PLANO. Mediana de la altura del rostro mayor como fracción
    #: del alto del cuadro, sobre los fotogramas donde se detecta alguno.
    #: Distingue un cine de primeros planos de uno de planos generales, que
    #: es la decisión de encuadre más visible de todas y la que el medidor no
    #: podía ver hasta que entró el cascarón local.
    escala_plano: float | None = None
    escala_plano_nombre: str = ""
    #: Fracción de fotogramas con al menos un rostro FRONTAL. Es un suelo, no
    #: un censo: una nuca no la ve nadie, y este cine está lleno de nucas.
    fraccion_con_rostro: float | None = None
    rostros_por_fotograma: float | None = None

    # --- oídos --------------------------------------------------------
    tiene_audio: bool = False
    rms_medio: float | None = None
    #: Fracción del tiempo por debajo del umbral de silencio. En un cine de
    #: sonido ambiente y sin música bajo el diálogo, es alta.
    fraccion_silencio: float | None = None
    #: Fracción del tiempo con energía dominante en la banda de la voz.
    fraccion_banda_voz: float | None = None
    rango_dinamico_db: float | None = None
    #: RITMO DE LOS TURNOS. Tramos de sonido sostenido separados por pausas.
    #: No dice QUIÉN habla —eso exige diarización— pero sí con qué cadencia se
    #: habla, y en un cine donde lo importante es lo que no se dice, la
    #: cadencia de las pausas ES la dirección. Se mide con la envolvente que
    #: ya estaba calculada: cero dependencias nuevas, cero modelos.
    turnos_por_minuto: float | None = None
    duracion_media_turno: float | None = None
    pausa_media: float | None = None
    #: La pausa más larga entre dos turnos. Un silencio de seis segundos en
    #: mitad de una conversación es una decisión de dirección, y la media lo
    #: esconde entre pausas de medio segundo.
    pausa_maxima: float | None = None

    # --- honestidad ---------------------------------------------------
    no_medido: list[str] = field(default_factory=list)
    evidencia: list[str] = field(default_factory=list)

    @property
    def completa(self) -> bool:
        """¿Se midió todo lo que este instrumento sabe medir?"""
        return not self.no_medido

    def render(self) -> str:
        p = []
        if self.aspecto:
            p.append(f"aspecto {self.aspecto:.3f}")
        if self.duracion_media_plano:
            p.append(f"plano medio {self.duracion_media_plano:.1f}s")
        if self.camara_px is not None:
            p.append(f"cámara {self.camara_px:.2f}px")
        if self.fraccion_camara_fija is not None:
            p.append(f"fija {self.fraccion_camara_fija:.0%}")
        if self.saturacion is not None:
            p.append(f"sat {self.saturacion:.3f}")
        if self.escala_plano is not None:
            p.append(f"escala {self.escala_plano:.3f} "
                     f"({self.escala_plano_nombre})")
        if self.fraccion_silencio is not None:
            p.append(f"silencio {self.fraccion_silencio:.0%}")
        if self.turnos_por_minuto is not None:
            p.append(f"{self.turnos_por_minuto:.0f} turnos/min")
        if self.pausa_maxima is not None:
            p.append(f"pausa máx {self.pausa_maxima:.1f}s")
        cabeza = " · ".join(p) or "sin medidas"
        if self.no_medido:
            cabeza += f"  [{len(self.no_medido)} sin medir]"
        return cabeza

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


# --------------------------------------------------------------- utilidades

async def _corre(args: list[str], timeout: int = 300) -> tuple[int, bytes]:
    """Ejecuta un binario sin shell y devuelve (código, stdout crudo).

    Sin shell por el mismo motivo que en `video.py`: las rutas llevan
    espacios, acentos y comillas, y componer una cadena para `sh -c` con eso
    dentro es una fuente inagotable de fallos raros.

    Devuelve bytes, no texto: por aquí salen fotogramas PNG y PCM crudo.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL)
    except FileNotFoundError as e:
        raise EstiloError(f"{args[0]} no está instalado") from e
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()          # sin esto queda un zombi
        raise EstiloError(
            f"{args[0]} superó el plazo de {timeout}s") from None
    return proc.returncode or 0, out or b""


async def _sonda(ruta: Path) -> dict:
    rc, out = await _corre([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(ruta)], timeout=60)
    if rc != 0:
        raise EstiloError(f"ffprobe falló sobre {ruta.name}")
    try:
        return json.loads(out.decode("utf-8", "replace"))
    except json.JSONDecodeError as e:
        raise EstiloError(f"ffprobe no devolvió JSON: {e}") from e


# ------------------------------------------------------------------ los ojos

def _area_activa(arr, umbral: int = 20):
    """Recorta las barras negras y devuelve (arriba, abajo, izq, der).

    EL FALLO QUE ESTO CIERRA. Leer la relación de aspecto de `ffprobe` da la
    del CONTENEDOR. Una película en 1.85:1 distribuida dentro de un 4:3 con
    barras negras arriba y abajo —que es exactamente cómo llegan casi todos
    los tráileres de 2008— reporta 1.333. Comparar el encuadre de la
    referencia contra el de la salida usando ese número compara dos envases,
    no dos imágenes.
    """
    import numpy as np
    gris = arr.max(axis=2) if arr.ndim == 3 else arr
    filas = np.where(gris.max(axis=1) > umbral)[0]
    cols = np.where(gris.max(axis=0) > umbral)[0]
    if not len(filas) or not len(cols):
        return None
    return int(filas[0]), int(filas[-1]), int(cols[0]), int(cols[-1])


def _desplazamiento_global(a, b, maxd: int = BUSQUEDA_MAX):
    """Estima cuánto se ha MOVIDO LA CÁMARA entre dos fotogramas.

    Busca el desplazamiento entero (dx, dy) que minimiza la diferencia
    absoluta entre los dos fotogramas. Es correlación por fuerza bruta sobre
    una imagen ya reducida: barato, determinista y sin dependencias.

    POR QUÉ ESTO Y NO «CUÁNTOS PÍXELES CAMBIAN»
    -------------------------------------------
    `observe_video` cuenta píxeles que cambian, y con eso distingue movimiento
    de congelado. Pero no distingue las dos cosas que aquí hay que separar:

        cámara quieta + gente moviéndose   -> muchos píxeles cambian, (0,0)
        cámara moviéndose + nada más       -> muchos píxeles cambian, (dx,dy)

    Para una dirección de cámara fija, el primero es lo pedido y el segundo
    es el fallo — y contando píxeles los dos dan el mismo número. El
    desplazamiento óptimo los separa: la cámara se mide por (dx,dy), el
    sujeto por lo que queda después de compensarlo.

    Devuelve (magnitud, residual, saturado).
    """
    import numpy as np
    mejor, mejor_dx, mejor_dy = None, 0, 0
    h, w = a.shape
    m = maxd
    if h <= 2 * m + 2 or w <= 2 * m + 2:
        m = max(1, min(h, w) // 4)
    centro_a = a[m:h - m, m:w - m]
    for dy in range(-m, m + 1):
        for dx in range(-m, m + 1):
            trozo = b[m + dy:h - m + dy, m + dx:w - m + dx]
            if trozo.shape != centro_a.shape:
                continue
            d = float(np.abs(centro_a - trozo).mean())
            if mejor is None or d < mejor:
                mejor, mejor_dx, mejor_dy = d, dx, dy
    if mejor is None:
        return 0.0, 0.0, False
    magnitud = math.hypot(mejor_dx, mejor_dy)
    # Si el óptimo cae en el borde de la ventana, el movimiento real puede ser
    # mayor y este número es un suelo, no una medida. Se dice.
    saturado = abs(mejor_dx) >= m or abs(mejor_dy) >= m
    return magnitud, mejor, saturado


def _histograma(rgb, bins: int = 16):
    """Histograma NORMALIZADO en exposición, para que un corte sea un corte.

    EL ACOPLAMIENTO QUE ESTO ROMPE, ENCONTRADO EJECUTÁNDOLO
    =======================================================
    Un corte es un cambio de CONTENIDO. Comparar histogramas crudos lo
    confunde con un cambio de EXPOSICIÓN, y eso no es una sutileza teórica:
    en cuanto el bucle de autocorrección aprendió a etalonar para acercar la
    paleta a la biblia, empezó a aplanar el contraste —`contrast=0.422`— y al
    aplanarlo los histogramas de dos planos distintos se parecían lo bastante
    como para caer por debajo del umbral. Los cortes DESAPARECÍAN.

    Consecuencia medida: el mismo montaje pasaba de 3 planos a 2, la duración
    media de plano se disparaba de 5,7 s a 13,9 s, y el bucle se ponía a
    corregir la duración de los planos por un cambio que había hecho él mismo
    en el color. Corregir un eje rompía la medición de otro, y el sistema
    perseguía su propio reflejo.

    Se estira cada fotograma a rango completo antes de contar. Así un cambio
    global de brillo o de contraste no mueve el histograma, y lo que lo mueve
    es lo que tiene que moverlo: que en el cuadro haya otra cosa.

    El guardia del rango pequeño no es cosmético: un fotograma casi plano —un
    fundido a negro, una pared— tiene un rango de dos o tres niveles, y
    estirarlo a 255 amplifica el ruido de compresión hasta convertir dos
    fotogramas idénticos en un corte.
    """
    import numpy as np
    a = np.asarray(rgb, dtype=np.float32)
    g = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    # PERCENTILES, NO MIN Y MAX. Y esto lo enseñó el adversario.
    #
    # La primera versión estiraba entre el mínimo y el máximo absolutos. Son
    # dos valores que dependen de UN píxel cada uno, así que un objeto claro
    # entrando o saliendo del cuadro cambia el máximo y remapea el histograma
    # entero. Medido sobre un plano ÚNICO y continuo con un rectángulo claro
    # cruzándolo: distancias de base 0,15 con dos picos de 0,70 justo cuando
    # el objeto tocaba el borde. Tres planos donde hay uno.
    #
    # Es el fallo clásico de normalizar por extremos, y lo irónico es que
    # apareció al arreglar OTRO fallo: la normalización se metió para que el
    # etalonaje no borrase los cortes, y de paso inventó cortes nuevos. Un
    # arreglo que crea el problema simétrico es medio arreglo.
    # SE MIRA EL COLOR, NO SOLO LA LUMINANCIA. Y esto también lo enseñó el
    # adversario, en el mismo sitio y con la ironía completa.
    #
    # La normalización de exposición se metió para que el etalonaje no borrase
    # los cortes. Funcionó, y de paso borró otra cosa: si el histograma solo
    # cuenta luminancia y además se normaliza, un corte entre dos planos de
    # colores distintos pero brillo parecido se vuelve INVISIBLE.
    #
    # Medido sobre una animática de rojo -> verde -> azul con encadenados: el
    # corte rojo/verde daba 0,242 de distancia, muy por debajo del umbral de
    # 0,38, mientras el verde/azul daba 0,563. Un detector que ve unos cortes
    # sí y otros no según los colores que se cruzan no es un detector.
    #
    # La solución conserva las dos propiedades a la vez: se calcula la escala
    # de normalización sobre la LUMA y se aplica IGUAL a los tres canales. Un
    # cambio global de exposición se cancela —los tres se mueven juntos—;
    # una diferencia de tono sobrevive, porque lo que la define es la
    # proporción ENTRE canales y esa no la toca una escala común.
    lo, hi = np.percentile(g, (2.0, 98.0))
    if hi - lo > 12.0:
        a = np.clip((a - lo) * (255.0 / (hi - lo)), 0.0, 255.0)
    trozos = [np.histogram(a[..., c], bins=bins, range=(0, 255))[0]
              for c in range(3)]
    h = np.concatenate(trozos).astype(np.float64)
    s = h.sum()
    return h / s if s else h


def _distancia_hist(h1, h2) -> float:
    """Distancia L1 normalizada entre histogramas, de 0 a 1."""
    import numpy as np
    return float(np.abs(h1 - h2).sum() / 2.0)


#: Cuánto tiene que destacar un pico sobre su vecindario para ser un corte.
#: Un corte es un salto; un sujeto que cruza el cuadro es una MESETA.
PROMINENCIA_CORTE = 2.2

#: Muestras a cada lado que forman el vecindario. Con 4 a 5 fps son 0,8 s por
#: lado: bastante para ver si el cambio es un pico o el estado normal de ese
#: tramo, y poco para no meter dentro el corte siguiente.
VECINDARIO_CORTE = 4


def _destaca(distancias: list[float], i: int) -> bool:
    """¿Es este pico un CORTE, o el ruido normal de un plano con movimiento?

    EL FALSO POSITIVO QUE ESTO CIERRA, ENCONTRADO POR EL ADVERSARIO
    ==============================================================
    El umbral absoluto solo pregunta «¿cambió mucho la imagen?». Un corte
    cambia mucho la imagen; un objeto claro y grande cruzando un plano fijo,
    también. Medido sobre la referencia del adversario —un plano ÚNICO y
    continuo, cámara clavada, con un rectángulo claro atravesando el cuadro—
    el detector encontraba **3 planos donde hay 1**.

    Y eso envenena todo lo que cuelga de ahí: la duración media de plano sale
    a un tercio de la real, la biblia se construye con esa cifra, y el bucle
    persigue un ritmo de montaje que nadie pidió.

    La diferencia entre las dos cosas no está en la altura del pico, está en
    su forma. Un corte es un SALTO: una muestra alta entre muestras bajas. Un
    sujeto en movimiento es una MESETA: muchas muestras seguidas parecidas
    entre sí, porque el objeto sigue cruzando. Se compara el pico con la
    mediana de su vecindario y se exige que destaque.

    La mediana y no la media, porque la media de un vecindario que contiene
    otro corte se dispara y esconde el pico que se está juzgando.
    """
    n = len(distancias)
    ini, fin = max(0, i - VECINDARIO_CORTE), min(n, i + VECINDARIO_CORTE + 1)
    vecinos = sorted(distancias[j] for j in range(ini, fin) if j != i)
    if not vecinos:
        return True
    mediana = vecinos[len(vecinos) // 2]
    # Un vecindario prácticamente quieto no puede dividir por cero ni exigir
    # una prominencia infinita: por debajo de este suelo, el umbral absoluto
    # ya es criterio suficiente.
    if mediana < 0.02:
        return True
    return distancias[i] >= mediana * PROMINENCIA_CORTE


def _une_transiciones(picos: list[int]) -> list[int]:
    """Un encadenado es UN corte, no tres.

    EL FALLO QUE ESTO CIERRA, ENCONTRADO EJECUTÁNDOLO
    =================================================
    Un corte seco es un salto instantáneo: un único pico de distancia entre
    dos fotogramas consecutivos. Un encadenado dura medio segundo, y a 5
    muestras por segundo eso son dos o tres pares seguidos por encima del
    umbral. Contarlos sueltos convierte cada transición gradual en dos o tres
    cortes.

    Medido en la prueba de extremo a extremo del 2026-09-02: una animática de
    TRES imágenes con encadenados salía con **6 planos**, y la duración media
    de plano por tanto a la mitad de la real. Y eso no se quedó en un número
    feo: el bucle de autocorrección leyó «los planos duran poco, SÚBELOS» y
    subió de 6 a 15,36 segundos por plano persiguiendo un objetivo que nunca
    podía alcanzar, porque el error no estaba en la duración sino en el
    recuento. Una medida mal hecha no da un informe peor: da un sistema que
    corrige en la dirección equivocada con toda la autoridad de un dato.

    Se unen los índices CONSECUTIVOS, y solo esos. Un corte seco real sigue
    siendo un pico aislado, así que el montaje rápido no se penaliza: lo que
    se colapsa es exactamente la firma de una transición gradual.
    """
    if not picos:
        return []
    unidos = [picos[0]]
    for p in picos[1:]:
        if p != unidos[-1] + 1:
            unidos.append(p)
        else:
            unidos[-1] = p          # sigue el mismo fundido: se extiende
    return unidos


async def _mide_imagen(ruta: Path, medida: MedidaEstilo) -> None:
    """Extrae fotogramas, los mira y rellena la parte visual de la medida."""
    import numpy as np
    from PIL import Image

    from ...core.paths import cache_dir

    huella = hashlib.sha1(str(ruta.resolve()).encode("utf-8")).hexdigest()[:10]
    destino = cache_dir() / "estilo_frames" / f"{ruta.stem}-{huella}"
    shutil.rmtree(destino, ignore_errors=True)
    destino.mkdir(parents=True, exist_ok=True)

    try:
        rc, _ = await _corre([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(ruta),
            "-vf", f"fps={MUESTREO_FPS},scale={ANCHO_ANALISIS}:-2",
            "-frames:v", "3000",
            str(destino / "f_%05d.png")], timeout=600)
        marcos = sorted(destino.glob("f_*.png"))
        if rc != 0 or len(marcos) < 2:
            medida.no_medido.append(
                f"no se pudieron extraer fotogramas suficientes "
                f"({len(marcos)}): el contenedor puede estar corrupto o la "
                f"pista de vídeo ser más corta que el contenedor")
            return

        arrays, grises = [], []
        for m in marcos:
            with Image.open(m) as im:
                arrays.append(np.asarray(im.convert("RGB"), dtype=np.float32))
        # área activa medida sobre el fotograma MÁS CLARO, no sobre el
        # primero: muchos tráileres abren en negro y el primer fotograma
        # daría un área activa vacía.
        idx_claro = max(range(len(arrays)), key=lambda i: arrays[i].mean())
        caja = _area_activa(arrays[idx_claro])
        if caja:
            arriba, abajo, izq, der = caja
            medida.aspecto = round(
                (der - izq + 1) / max(1, (abajo - arriba + 1)), 4)
            medida.evidencia.append(
                f"área activa {der - izq + 1}x{abajo - arriba + 1} dentro de "
                f"{arrays[0].shape[1]}x{arrays[0].shape[0]} "
                f"(barras: {arriba} arriba, "
                f"{arrays[0].shape[0] - 1 - abajo} abajo)")
            arrays = [a[arriba:abajo + 1, izq:der + 1] for a in arrays]
        else:
            medida.no_medido.append(
                "todos los fotogramas son negros: no hay área activa que medir")
            return

        for a in arrays:
            grises.append(0.2126 * a[..., 0] + 0.7152 * a[..., 1]
                          + 0.0722 * a[..., 2])

        # --- paleta y luz -------------------------------------------------
        pila = np.stack(arrays)
        medio = pila.reshape(-1, 3).mean(axis=0)
        medida.rgb_medio = tuple(int(round(v)) for v in medio)
        gpila = np.stack(grises)
        medida.luma = round(float(gpila.mean()), 2)
        medida.contraste = round(float(gpila.std()), 2)
        # `axis=-1` ES EL CANAL. La primera versión ponía `axis=3 - 1`, o sea
        # `axis=2`, con la intención de decir «el último». Sobre un fotograma
        # suelto (alto, ancho, 3) habría sido correcto; sobre `pila`, que es
        # (n, alto, ancho, 3), el eje 2 es LA ANCHURA.
        #
        # Así que la «saturación» medía el recorrido de luminancia a lo largo
        # de cada fila de píxeles. Un número perfectamente estable, plausible
        # y sin ninguna relación con el color: pasar el vídeo entero a gris
        # con `hue=s=0` solo lo movía de 0,313 a 0,262, cuando tenía que
        # desplomarse a cero.
        #
        # Lo encontró el adversario, y es exactamente para lo que existe: una
        # métrica que devuelve cifras razonables mientras mide otra cosa no la
        # caza mirar el código, la caza ponerle delante material que DEBE
        # suspender y ver que no suspende.
        mx = pila.max(axis=-1)
        mn = pila.min(axis=-1)
        with np.errstate(divide="ignore", invalid="ignore"):
            sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
        medida.saturacion = round(float(sat.mean()), 4)

        # --- cortes ---------------------------------------------------------
        # Sobre los fotogramas EN COLOR, no sobre los grises: un corte entre
        # dos planos de tono distinto y brillo parecido no existe en luma.
        hists = [_histograma(a) for a in arrays]
        distancias = [_distancia_hist(hists[i], hists[i + 1])
                      for i in range(len(hists) - 1)]
        # SE DESCARTAN LOS EXTREMOS, y no por comodidad.
        #
        # Un pico en el primer par significaría que el plano de apertura dura
        # una sola muestra: 0,2 s a 5 fps. Eso no es un montaje, es el
        # decodificador arrancando — medido sobre un vídeo con 3 cortes
        # exactos, el detector encontraba 4, y el sobrante estaba siempre en
        # el índice 0 con una distancia de 0,586 entre dos fotogramas del
        # MISMO plano. `extract_frames` en `video.py` ya evita los extremos
        # por la misma razón y lo dice en su docstring.
        #
        # El coste está declarado: un primer o último plano más corto que una
        # muestra no se cuenta. Este instrumento no puede medir esa duración
        # de todas formas, así que no se pierde nada que se supiera.
        interior = range(1, max(1, len(distancias) - 1))
        picos = [i for i in interior
                 if distancias[i] > UMBRAL_CORTE
                 and _destaca(distancias, i)]
        cortes = _une_transiciones(picos)
        medida.planos = len(cortes) + 1
        if medida.duracion > 0:
            medida.duracion_media_plano = round(
                medida.duracion / max(1, medida.planos), 3)
        fundidos = len(picos) - len(cortes)
        medida.evidencia.append(
            f"{len(marcos)} fotogramas muestreados a {MUESTREO_FPS} fps · "
            f"{len(cortes)} cortes detectados"
            + (f" ({fundidos} picos unidos: transiciones graduales)"
               if fundidos else ""))

        # --- cámara contra sujeto -------------------------------------------
        # Solo se miden pares DENTRO del mismo plano. Medir a través de un
        # corte daría un desplazamiento enorme y falso: no es que la cámara
        # se moviera, es que cambió el plano. Este era el error obvio de
        # medir movimiento sin detectar cortes primero.
        en_corte = set(cortes)
        magnitudes, residuales, saturados = [], [], 0
        for i in range(len(grises) - 1):
            if i in en_corte:
                continue
            mag, resid, sat_ = _desplazamiento_global(grises[i], grises[i + 1])
            magnitudes.append(mag)
            residuales.append(resid)
            saturados += 1 if sat_ else 0
        if magnitudes:
            magnitudes.sort()
            medida.camara_px = round(
                float(magnitudes[len(magnitudes) // 2]), 3)
            medida.fraccion_camara_fija = round(
                sum(1 for m in magnitudes if m <= UMBRAL_CAMARA_FIJA)
                / len(magnitudes), 4)
            medida.sujeto_residual = round(
                float(sum(residuales) / len(residuales)), 3)
            medida.evidencia.append(
                f"{len(magnitudes)} pares intra-plano medidos · cámara "
                f"mediana {medida.camara_px:.2f}px · residual de sujeto "
                f"{medida.sujeto_residual:.2f}")
            if saturados:
                medida.no_medido.append(
                    f"{saturados} pares saturaron la ventana de búsqueda de "
                    f"±{BUSQUEDA_MAX}px: en esos el movimiento de cámara es "
                    f"AL MENOS el medido, no exactamente el medido")
        else:
            medida.no_medido.append(
                "no hubo dos fotogramas consecutivos dentro del mismo plano: "
                "el movimiento de cámara no se ha medido")

    finally:
        shutil.rmtree(destino, ignore_errors=True)


#: Anchura a la que se extraen los fotogramas PARA ROSTROS, distinta de la del
#: resto del análisis y por un motivo concreto: paleta, cortes y
#: desplazamiento global se miden perfectamente en 128 px, pero a esa anchura
#: un rostro de primer plano ocupa 30 px y uno de plano general no llega a 6.
#: La cascada Haar no ve nada ahí. Se paga resolución solo donde hace falta.
ANCHO_ROSTROS = 480

#: Cadencia del muestreo para rostros. Más baja que la del resto porque la
#: detección es lo caro y la escala de plano no cambia dentro de un plano —
#: para eso está la cámara fija.
MUESTREO_ROSTROS_FPS = 1.0


async def _mide_rostros(ruta: Path, medida: MedidaEstilo) -> None:
    """Escala de plano, con el detector que viene dentro de OpenCV.

    Se hace en una pasada aparte y a más resolución (ver `ANCHO_ROSTROS`).
    Podría parecer un desperdicio extraer los fotogramas dos veces; es más
    barato que subir la resolución de TODO el análisis para que un solo eje
    funcione, y mantiene los demás ejes idénticos a como estaban calibrados.
    """
    from . import cascaron

    if not cascaron.detector_disponible():
        # Se copian los motivos concretos del informe del cascarón en vez de
        # escribir «no disponible»: un aviso que no dice cómo se arregla
        # obliga a quien lo lee a ir a buscarlo, y normalmente no va.
        for motivo in cascaron.informe_cascaron()["falta"]:   # type: ignore
            medida.no_medido.append(str(motivo))
        return

    import numpy as np
    from PIL import Image

    from ...core.paths import cache_dir

    huella = hashlib.sha1(
        (str(ruta.resolve()) + "rostros").encode("utf-8")).hexdigest()[:10]
    destino = cache_dir() / "estilo_rostros" / f"{ruta.stem}-{huella}"
    shutil.rmtree(destino, ignore_errors=True)
    destino.mkdir(parents=True, exist_ok=True)
    try:
        rc, _ = await _corre([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(ruta),
            "-vf", f"fps={MUESTREO_ROSTROS_FPS},scale={ANCHO_ROSTROS}:-2",
            "-frames:v", "600",
            str(destino / "r_%05d.png")], timeout=600)
        marcos = sorted(destino.glob("r_*.png"))
        if rc != 0 or not marcos:
            medida.no_medido.append(
                "no se pudieron extraer fotogramas para medir rostros")
            return

        escalas: list[float] = []
        cuentas: list[int] = []
        for m in marcos:
            with Image.open(m) as im:
                gris = np.asarray(im.convert("L"), dtype=np.uint8)
            rostros = cascaron.detecta_rostros(gris)
            cuentas.append(len(rostros))
            frac = cascaron.escala_de_plano(rostros, gris.shape[0])
            if frac is not None:
                escalas.append(frac)

        medida.rostros_por_fotograma = round(
            sum(cuentas) / max(1, len(cuentas)), 3)
        medida.fraccion_con_rostro = round(
            sum(1 for c in cuentas if c) / max(1, len(cuentas)), 4)

        if escalas:
            escalas.sort()
            medida.escala_plano = round(escalas[len(escalas) // 2], 4)
            medida.escala_plano_nombre = cascaron.nombre_de_escala(
                medida.escala_plano)
            medida.evidencia.append(
                f"rostros: {len(marcos)} fotogramas a {MUESTREO_ROSTROS_FPS} "
                f"fps · con rostro {medida.fraccion_con_rostro:.0%} · escala "
                f"mediana {medida.escala_plano:.3f} "
                f"({medida.escala_plano_nombre})")
        else:
            # NO es «plano general». Es que no se detectó ninguna cara
            # frontal, y las dos cosas se parecen mucho y significan lo
            # contrario. Sin esta rama, un documental de nucas mediría como
            # el plano más abierto posible.
            medida.no_medido.append(
                f"no se detectó ningún rostro frontal en {len(marcos)} "
                f"fotogramas: la escala de plano queda SIN MEDIR. No "
                f"significa plano general — un detector frontal no ve "
                f"perfiles ni nucas.")

        if not cascaron.identidad_disponible():
            for motivo in cascaron.informe_cascaron()["falta"]:  # type: ignore
                if "identidad" in str(motivo):
                    medida.no_medido.append(str(motivo))
    finally:
        shutil.rmtree(destino, ignore_errors=True)



# ------------------------------------------------------------------- fachada

async def medir(ruta: str | Path, *,
                procedencia: str = "desconocida") -> MedidaEstilo:
    """Mide un fichero de vídeo. Devuelve números crudos, nunca un veredicto.

    `procedencia` no cambia ni una cuenta: se guarda para que el veredicto
    posterior sepa qué ejes son legítimos. De un tráiler, la duración media
    de plano habla del montador del tráiler y no del director, y `compara()`
    la ignora si la procedencia lo dice.
    """
    p = Path(ruta)
    m = MedidaEstilo(ruta=str(p), procedencia=procedencia)

    if not p.exists():
        m.no_medido.append(f"{p} no existe")
        return m
    if not ffmpeg_disponible() or not ffprobe_disponible():
        m.no_medido.append(
            "ffmpeg/ffprobe no están instalados: no se ha medido NADA. "
            "Instálalos para cerrar el instrumento.")
        return m

    try:
        datos = await _sonda(p)
    except EstiloError as e:
        m.no_medido.append(str(e))
        return m

    flujos = datos.get("streams", [])
    vid = next((s for s in flujos if s.get("codec_type") == "video"), None)
    fmt = datos.get("format", {})
    m.duracion = float(fmt.get("duration") or 0.0)
    if vid:
        m.ancho = int(vid.get("width") or 0)
        m.alto = int(vid.get("height") or 0)
        if m.alto:
            m.aspecto_contenedor = round(m.ancho / m.alto, 4)
    else:
        m.no_medido.append("el fichero no tiene pista de vídeo")

    if not numpy_disponible() or not pillow_disponible():
        faltan = [n for n, ok in (("numpy", numpy_disponible()),
                                  ("Pillow", pillow_disponible())) if not ok]
        m.no_medido.append(
            f"{' y '.join(faltan)} sin instalar: los fotogramas NO se han "
            f"mirado. Aspecto real, paleta, cortes y movimiento de cámara "
            f"quedan SIN MEDIR — que no es lo mismo que correctos.")
    elif vid:
        try:
            await _mide_imagen(p, m)
        except EstiloError as e:
            m.no_medido.append(f"parte visual: {e}")
        except Exception as e:                        # pragma: no cover
            logger.debug("[estilo] fallo midiendo imagen: %s", e)
            m.no_medido.append(f"parte visual falló: {type(e).__name__}: {e}")
        try:
            await _mide_rostros(p, m)
        except EstiloError as e:
            m.no_medido.append(f"escala de plano: {e}")
        except Exception as e:                        # pragma: no cover
            logger.debug("[estilo] fallo midiendo rostros: %s", e)
            m.no_medido.append(
                f"escala de plano falló: {type(e).__name__}: {e}")

    if any(s.get("codec_type") == "audio" for s in flujos):
        if not numpy_disponible():
            m.no_medido.append("numpy sin instalar: el audio no se ha medido")
        else:
            try:
                from .oido import _mide_audio
                await _mide_audio(p, m)
            except EstiloError as e:
                m.no_medido.append(f"parte de audio: {e}")
            except Exception as e:                    # pragma: no cover
                logger.debug("[estilo] fallo midiendo audio: %s", e)
                m.no_medido.append(
                    f"parte de audio falló: {type(e).__name__}: {e}")
    else:
        m.no_medido.append("el fichero no tiene pista de audio")

    return m


# ----------------------------------------------------------------- el juicio
#
# `BibliaDeEstilo`, `compara` y compañía viven en `biblia.py`. Se reexportan
# aquí porque la frontera útil para quien LLAMA es «lo del estilo», y obligarle
# a importar de dos módulos para medir y juzgar es la clase de costura que
# acaba en dos formas distintas de hacer lo mismo. La frontera que sí importa
# —medir no juzga— la impone el código, no el import.
from .biblia import (  # noqa: E402,F401
    EJES_SOLO_OBRA,
    BibliaDeEstilo,
    Desvio,
    Tolerancia,
    Veredicto,
    compara,
)
