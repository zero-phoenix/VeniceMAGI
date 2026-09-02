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

    # --- oídos --------------------------------------------------------
    tiene_audio: bool = False
    rms_medio: float | None = None
    #: Fracción del tiempo por debajo del umbral de silencio. En un cine de
    #: sonido ambiente y sin música bajo el diálogo, es alta.
    fraccion_silencio: float | None = None
    #: Fracción del tiempo con energía dominante en la banda de la voz.
    fraccion_banda_voz: float | None = None
    rango_dinamico_db: float | None = None

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
        if self.fraccion_silencio is not None:
            p.append(f"silencio {self.fraccion_silencio:.0%}")
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


def _histograma(gris, bins: int = 48):
    import numpy as np
    h, _ = np.histogram(gris, bins=bins, range=(0, 255))
    s = h.sum()
    return h / s if s else h.astype(float)


def _distancia_hist(h1, h2) -> float:
    """Distancia L1 normalizada entre histogramas, de 0 a 1."""
    import numpy as np
    return float(np.abs(h1 - h2).sum() / 2.0)


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
        mx = pila.max(axis=3 - 1)
        mn = pila.min(axis=3 - 1)
        with np.errstate(divide="ignore", invalid="ignore"):
            sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
        medida.saturacion = round(float(sat.mean()), 4)

        # --- cortes ---------------------------------------------------------
        hists = [_histograma(g) for g in grises]
        distancias = [_distancia_hist(hists[i], hists[i + 1])
                      for i in range(len(hists) - 1)]
        cortes = [i for i, d in enumerate(distancias) if d > UMBRAL_CORTE]
        medida.planos = len(cortes) + 1
        if medida.duracion > 0:
            medida.duracion_media_plano = round(
                medida.duracion / max(1, medida.planos), 3)
        medida.evidencia.append(
            f"{len(marcos)} fotogramas muestreados a {MUESTREO_FPS} fps · "
            f"{len(cortes)} cortes detectados")

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

        medida.no_medido.append(
            "escala de plano (primer plano contra plano general): exige un "
            "detector de rostros local, que este sistema todavía no tiene")
    finally:
        shutil.rmtree(destino, ignore_errors=True)


# ----------------------------------------------------------------- los oídos

async def _mide_audio(ruta: Path, medida: MedidaEstilo) -> None:
    """Mide la banda sonora. No la escucha: la mide.

    POR QUÉ MEDIR Y NO ESCUCHAR
    ===========================
    Nadie en esta cadena —ni los proveedores guest, ni el sistema— oye. Pero
    lo que hace falta para dirigir no es una impresión auditiva: son números.
    Si el ambiente domina y no hay música bajo el diálogo, eso se ve en la
    envolvente y en el reparto de energía por bandas, y se ve mejor que
    oyéndolo, porque sale un número que se puede comparar contra el corte
    generado.

    Lo que NO se mide aquí, y se declara: quién habla, qué dice, y si dos
    voces se solapan. Separar voces exige diarización, que es un modelo. En
    cuanto el cascarón local tenga uno, entra por esta misma puerta.
    """
    import numpy as np

    rc, crudo = await _corre([
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", str(ruta), "-vn", "-ac", "1", "-ar", str(AUDIO_HZ),
        "-f", "s16le", "-"], timeout=300)
    if rc != 0 or len(crudo) < AUDIO_HZ:
        medida.tiene_audio = False
        medida.no_medido.append(
            "sin pista de audio utilizable: no se ha medido nada del sonido")
        return

    medida.tiene_audio = True
    x = np.frombuffer(crudo, dtype="<i2").astype(np.float32) / 32768.0
    n_v = max(1, int(AUDIO_HZ * AUDIO_VENTANA))
    n_ventanas = len(x) // n_v
    if n_ventanas < 4:
        medida.no_medido.append("audio demasiado corto para medir")
        return
    marco = x[:n_ventanas * n_v].reshape(n_ventanas, n_v)

    rms = np.sqrt((marco ** 2).mean(axis=1) + 1e-12)
    medida.rms_medio = round(float(rms.mean()), 5)

    # Umbral de silencio RELATIVO al propio material, no absoluto. Un absoluto
    # declara «todo silencio» en una mezcla suave y «nada de silencio» en una
    # ruidosa, y las dos lecturas son del volumen de masterizado, no del cine.
    pico = float(np.percentile(rms, 95))
    umbral = max(pico * 0.06, 1e-4)
    medida.fraccion_silencio = round(float((rms < umbral).mean()), 4)

    p95, p05 = float(np.percentile(rms, 95)), float(np.percentile(rms, 5))
    medida.rango_dinamico_db = round(
        20.0 * math.log10(max(p95, 1e-9) / max(p05, 1e-9)), 2)

    # Reparto de energía por bandas sobre las ventanas con sonido. La banda de
    # la voz (300-3400 Hz) dominando indica diálogo y ambiente; una cola de
    # graves fuerte indica música con base.
    activas = marco[rms >= umbral]
    if len(activas) >= 4:
        vent = np.hanning(n_v).astype(np.float32)
        esp = np.abs(np.fft.rfft(activas * vent, axis=1)) ** 2
        frec = np.fft.rfftfreq(n_v, 1.0 / AUDIO_HZ)
        voz = esp[:, (frec >= 300) & (frec <= 3400)].sum(axis=1)
        total = esp.sum(axis=1) + 1e-12
        ratio = voz / total
        medida.fraccion_banda_voz = round(float((ratio > 0.5).mean()), 4)
        medida.evidencia.append(
            f"audio: {n_ventanas} ventanas de {AUDIO_VENTANA * 1000:.0f} ms · "
            f"silencio {medida.fraccion_silencio:.0%} · "
            f"rango {medida.rango_dinamico_db:.1f} dB")
    else:
        medida.no_medido.append(
            "casi todo el audio está por debajo del umbral: no se ha podido "
            "repartir la energía por bandas")

    medida.no_medido.append(
        "solapamiento de diálogo y separación de voces: exige diarización, "
        "que este sistema todavía no tiene en local")


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

    if any(s.get("codec_type") == "audio" for s in flujos):
        if not numpy_disponible():
            m.no_medido.append("numpy sin instalar: el audio no se ha medido")
        else:
            try:
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


# ------------------------------------------------------------- biblia y juicio

#: Ejes que NO sobreviven a un tráiler: los decide el montador del tráiler,
#: no el director de la película.
EJES_SOLO_OBRA = frozenset({"duracion_media_plano", "planos",
                            "fraccion_silencio", "rango_dinamico_db",
                            "fraccion_banda_voz"})


@dataclass
class Tolerancia:
    """Cuánto se puede desviar un eje antes de declararlo incumplido."""
    eje: str
    objetivo: float
    margen: float
    #: Si es True, basta con estar POR DEBAJO del objetivo más el margen.
    #: Sirve para «la cámara no debe moverse más de X», donde quedarse corto
    #: no es un fallo.
    solo_maximo: bool = False


@dataclass
class BibliaDeEstilo:
    """La dirección artística, en números, con su procedencia.

    Se construye desde una `MedidaEstilo` de la REFERENCIA. No se escribe a
    mano: una biblia escrita a mano son las suposiciones de quien la escribe
    con aspecto de dato.
    """
    nombre: str = ""
    origen: str = ""
    procedencia: str = "desconocida"
    tolerancias: list[Tolerancia] = field(default_factory=list)

    @classmethod
    def desde(cls, medida: MedidaEstilo, *, nombre: str = "referencia",
              holgura: float = 0.15) -> BibliaDeEstilo:
        """Deriva tolerancias de una medida real.

        `holgura` es la fracción del propio valor que se admite de desvío.
        Relativa y no absoluta porque un margen absoluto que vale para la
        saturación (0-1) no vale para la duración de plano (segundos).
        """
        b = cls(nombre=nombre, origen=medida.ruta,
                procedencia=medida.procedencia)
        pares = [
            ("aspecto", medida.aspecto, False),
            ("duracion_media_plano", medida.duracion_media_plano, False),
            ("camara_px", medida.camara_px, True),
            ("fraccion_camara_fija", medida.fraccion_camara_fija, False),
            ("saturacion", medida.saturacion, False),
            ("luma", medida.luma, False),
            ("contraste", medida.contraste, False),
            ("fraccion_silencio", medida.fraccion_silencio, False),
        ]
        for eje, valor, solo_max in pares:
            if valor is None:
                continue
            if medida.procedencia == "trailer" and eje in EJES_SOLO_OBRA:
                continue
            b.tolerancias.append(Tolerancia(
                eje=eje, objetivo=float(valor),
                margen=abs(float(valor)) * holgura or holgura,
                solo_maximo=solo_max))
        return b

    def to_json(self) -> str:
        from dataclasses import asdict
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)


@dataclass
class Desvio:
    eje: str
    objetivo: float
    obtenido: float | None
    margen: float
    cumple: bool
    motivo: str = ""


@dataclass
class Veredicto:
    """Qué cumple, qué no, y qué no se pudo juzgar. Las tres cosas."""
    desvios: list[Desvio] = field(default_factory=list)
    sin_juzgar: list[str] = field(default_factory=list)

    @property
    def incumplidos(self) -> list[Desvio]:
        return [d for d in self.desvios if not d.cumple]

    @property
    def aprueba(self) -> bool:
        """Aprueba solo si TODO lo comprobable cumple y no falta nada.

        Un eje que no se pudo medir NO aprueba por omisión. Es la quinta
        regla del proyecto, y es la que se saltó `observe_video` cuando sin
        Pillow devolvía «correcto» sobre una captura que nunca abrió.
        """
        return not self.incumplidos and not self.sin_juzgar

    def render(self) -> str:
        lineas = []
        for d in self.desvios:
            marca = "OK  " if d.cumple else "FALLA"
            obt = "sin medir" if d.obtenido is None else f"{d.obtenido:.4g}"
            lineas.append(
                f"  {marca} {d.eje:<22} objetivo {d.objetivo:.4g} "
                f"±{d.margen:.4g} · obtenido {obt}")
        for s in self.sin_juzgar:
            lineas.append(f"  ????  {s}")
        cab = ("APRUEBA" if self.aprueba
               else f"NO APRUEBA · {len(self.incumplidos)} incumplidos, "
                    f"{len(self.sin_juzgar)} sin juzgar")
        return cab + "\n" + "\n".join(lineas)

    def lista_para_reintento(self) -> list[str]:
        """Los incumplimientos, en frases que se le pueden dar a un modelo.

        Un veredicto negativo no manda «hazlo mejor»: manda la lista concreta
        de lo que falló, igual que el reintento dirigido del taller de arte.
        """
        fuera = []
        for d in self.incumplidos:
            if d.obtenido is None:
                fuera.append(f"{d.eje}: no se pudo medir ({d.motivo})")
            elif d.obtenido > d.objetivo:
                fuera.append(
                    f"{d.eje}: salió {d.obtenido:.4g} y el objetivo es "
                    f"{d.objetivo:.4g}. Hay que BAJARLO.")
            else:
                fuera.append(
                    f"{d.eje}: salió {d.obtenido:.4g} y el objetivo es "
                    f"{d.objetivo:.4g}. Hay que SUBIRLO.")
        return fuera


def compara(medida: MedidaEstilo, biblia: BibliaDeEstilo) -> Veredicto:
    """Enfrenta una medida contra la biblia. Función pura, sin red ni disco.

    Pura a propósito, igual que `build_filtergraph` en `video.py`: así se
    puede comprobar en un test sin generar un vídeo ni esperar dos minutos,
    que es la diferencia entre tener tests de esto y no tenerlos.
    """
    v = Veredicto()
    for tol in biblia.tolerancias:
        obtenido = getattr(medida, tol.eje, None)
        if obtenido is None:
            v.desvios.append(Desvio(
                eje=tol.eje, objetivo=tol.objetivo, obtenido=None,
                margen=tol.margen, cumple=False,
                motivo="el instrumento no pudo medir este eje"))
            continue
        obtenido = float(obtenido)
        if tol.solo_maximo:
            cumple = obtenido <= tol.objetivo + tol.margen
        else:
            cumple = abs(obtenido - tol.objetivo) <= tol.margen
        v.desvios.append(Desvio(
            eje=tol.eje, objetivo=tol.objetivo, obtenido=obtenido,
            margen=tol.margen, cumple=cumple))
    # Lo que el instrumento declaró que no pudo medir viaja al veredicto. Si
    # se quedara en la medida, un corte cuyo movimiento de cámara no se pudo
    # medir aprobaría por no tener ningún desvío en contra.
    v.sin_juzgar = list(medida.no_medido)
    return v
