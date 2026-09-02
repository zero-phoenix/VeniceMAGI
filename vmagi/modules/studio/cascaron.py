"""
EL CASCARÓN LOCAL: lo poco que corre en tu máquina, y por qué es justo eso.

LA DECISIÓN, Y SU MOTIVO
========================
La forma evidente de usar una GPU en un proyecto de vídeo es generar vídeo con
ella. Aquí es la peor. Medido en el equipo de destino con `nvidia-smi`:

    NVIDIA GeForce GTX 1050 · 2048 MiB · driver 582.66

Los tres generadores de vídeo con pesos abiertos que existen —Wan 2.2 T2V-1.3B,
HunyuanVideo 1.5 1.3B y LTX-Video— piden 8 GB en su variante más ligera. Con
2 GB no van lentos: no cargan. Y aunque cargaran, estarían quemando la tarjeta
para producir lo que la nube guest ya produce gratis.

Así que el cascarón **no genera: percibe**. Hace lo que ningún proveedor guest
de este sistema puede hacer —porque ninguno acepta imágenes de entrada— y lo
hace con unos pocos megas y en CPU.

POR QUÉ OpenCV Y NO PyTorch
===========================
La ruta habitual para «visión local» es torch más un modelo de HuggingFace. La
rueda de torch pesa cientos de megas (miles con CUDA) sobre un ejecutable
onefile que ya va por 143 MB, y arrastra un runtime que esta tarjeta apenas
aprovecha. OpenCV carga ONNX por sí solo, sin runtime extra:

    YuNet   detección de rostros    ~230 KB
    SFace   identidad               ~37 MB

Detección y encuadre por 230 KB. Ese es el tamaño correcto de un cascarón.

LA TRAMPA DE VERSIONES QUE ESTE MÓDULO YA PAGÓ
==============================================
La primera versión usaba el clasificador Haar de `cv2.data.haarcascades`, que
tiene la ventaja de venir DENTRO del paquete y no exigir ninguna descarga.
Comprobado antes de darlo por bueno:

    cv2 5.0.0 -> AttributeError: module 'cv2' has no attribute
                 'CascadeClassifier'
                 cv2.data.haarcascades: no existe

**OpenCV 5 retiró las cascadas Haar.** El módulo habría existido, importado
bien, y devuelto cero rostros para siempre sin un solo error — el modo de
fallo más caro de todos, porque «no se detectó ningún rostro» se parece
muchísimo a «es un plano general».

De ahí la forma actual: YuNet primero (existe en OpenCV 4.5.4+ y en 5.x), Haar
solo como respaldo donde siga estando, y si no hay ninguno **se declara**. La
comprobación de qué detector hay se hace preguntándoselo a la biblioteca, no
suponiéndolo por el número de versión.

DEGRADACIÓN, COMO EL RESTO DEL PROYECTO
=======================================
Sin `cv2`, sin detector o sin el modelo de identidad, se devuelve `None` y el
motivo. Nunca un cero, nunca un valor por defecto. Un cero en un eje de estilo
es peor que una ausencia: «la cámara no se mueve» es justo lo que se busca,
así que un cero por no haber mirado APRUEBA el corte.

LO QUE SIGUE SIN PODER MEDIRSE, Y SE DICE
=========================================
Ningún detector ve una nuca, y el cine de sobremesa está lleno de nucas.
`fraccion_con_rostro` es un SUELO, no un censo. Sirve para comparar dos vídeos
con el mismo instrumento —que es para lo que existe— pero nadie debería
leerla como «había dos personas en la habitación».
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: Escala de plano por altura del rostro respecto a la del cuadro. Los cortes
#: son los de la gramática de plano de siempre; van nombrados y no como
#: números sueltos porque el veredicto lo lee una persona.
ESCALAS = (
    (0.60, "primerísimo primer plano"),
    (0.30, "primer plano"),
    (0.12, "plano medio"),
    (0.05, "plano americano o general"),
    (0.00, "plano general largo"),
)

#: Similitud coseno por encima de la cual dos rostros son LA MISMA persona.
#: Es el umbral que la documentación de SFace recomienda para coseno; se deja
#: como constante nombrada para poder discutirlo con un número delante en vez
#: de con una intuición.
UMBRAL_MISMA_PERSONA = 0.363

#: Confianza mínima de YuNet. Por debajo son manchas con forma de cara.
CONFIANZA_MINIMA = 0.75

MODELO_DETECTOR = "face_detection_yunet_2023mar.onnx"
MODELO_IDENTIDAD = "face_recognition_sface_2021dec.onnx"

#: De dónde salen. NO se descargan solos: bajar ficheros sin que nadie lo haya
#: pedido es exactamente el tipo de cosa que este proyecto no hace, y además
#: rompería la promesa de una sola salida de red si ocurriera fuera de ella.
MODELOS = {
    MODELO_DETECTOR: (
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_detection_yunet/face_detection_yunet_2023mar.onnx", "230 KB"),
    MODELO_IDENTIDAD: (
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_recognition_sface/face_recognition_sface_2021dec.onnx", "37 MB"),
}


def cv2_disponible() -> bool:
    """¿Hay OpenCV en esta máquina?

    Función explícita por el mismo motivo que `pillow_available`: quien mide
    tiene que distinguir «he mirado y no hay caras» de «no he podido mirar».
    Sin la pregunta, la segunda se cuela como la primera.
    """
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


def carpeta_modelos():
    from ...core.paths import data_dir
    return data_dir() / "modelos"


def ruta_modelo(nombre: str) -> str | None:
    p = carpeta_modelos() / nombre
    return str(p) if p.exists() else None


def tiene_yunet() -> bool:
    """¿Están la clase Y el fichero? Las dos cosas, y se preguntan aparte."""
    if not cv2_disponible():
        return False
    import cv2
    return (hasattr(cv2, "FaceDetectorYN")
            and ruta_modelo(MODELO_DETECTOR) is not None)


def tiene_haar() -> bool:
    """Respaldo para OpenCV 4.x, donde las cascadas siguen viniendo dentro.

    Se pregunta con `hasattr` y comprobando el fichero, NO por el número de
    versión: la retirada de `CascadeClassifier` en OpenCV 5 se descubrió
    ejecutándolo, y una lista de versiones que hay que mantener a mano es lo
    que produjo el fallo de `seedance_admitido` con dos cadenas literales.
    """
    if not cv2_disponible():
        return False
    import os

    import cv2
    if not hasattr(cv2, "CascadeClassifier") or not hasattr(cv2, "data"):
        return False
    ruta = getattr(cv2.data, "haarcascades", None)
    if not ruta:
        return False
    return os.path.exists(
        os.path.join(ruta, "haarcascade_frontalface_default.xml"))


def detector_disponible() -> bool:
    return tiene_yunet() or tiene_haar()


def identidad_disponible() -> bool:
    if not cv2_disponible():
        return False
    import cv2
    return (hasattr(cv2, "FaceRecognizerSF")
            and ruta_modelo(MODELO_IDENTIDAD) is not None)


def informe_cascaron() -> dict[str, object]:
    """Qué sabe percibir esta máquina, qué le falta, y exactamente cómo se
    arregla. Un informe que dice «no disponible» y nada más no ayuda a nadie:
    es la misma regla que el script de huérfanos."""
    carpeta = carpeta_modelos()
    faltan: list[str] = []
    if not cv2_disponible():
        faltan.append(
            "OpenCV no está: `pip install opencv-python-headless`. Sin él no "
            "hay escala de plano ni continuidad de identidad.")
    else:
        if not detector_disponible():
            url, peso = MODELOS[MODELO_DETECTOR]
            faltan.append(
                f"falta el detector de rostros ({peso}): pon "
                f"{MODELO_DETECTOR} en {carpeta}. Se descarga de {url}. Sin "
                f"él la escala de plano queda SIN MEDIR, que no es lo mismo "
                f"que plano general.")
        if not identidad_disponible():
            url, peso = MODELOS[MODELO_IDENTIDAD]
            faltan.append(
                f"falta el modelo de identidad ({peso}): pon "
                f"{MODELO_IDENTIDAD} en {carpeta}. Se descarga de {url}. Sin "
                f"él la continuidad de personaje entre planos queda SIN "
                f"MEDIR.")
    return {
        "cv2": cv2_disponible(),
        "detector": detector_disponible(),
        "detector_tipo": ("yunet" if tiene_yunet()
                          else "haar" if tiene_haar() else None),
        "identidad": identidad_disponible(),
        "carpeta_modelos": str(carpeta),
        "falta": faltan,
    }


@dataclass
class Rostro:
    x: int
    y: int
    ancho: int
    alto: int
    confianza: float = 1.0

    @property
    def area(self) -> int:
        return self.ancho * self.alto


class _Detector:
    """Carga el detector UNA vez y lo reutiliza.

    Cargar el modelo por cada fotograma cuesta más que detectar en él. En un
    tráiler de dos minutos son cientos de cargas del mismo fichero, y ese es
    el detalle que convierte «medir un vídeo» en «esperar a que mida».
    """

    _yunet = None
    _haar = None
    _tam: tuple[int, int] | None = None

    @classmethod
    def reinicia(cls) -> None:
        """Para los tests: olvida lo cargado y vuelve a preguntar."""
        cls._yunet = None
        cls._haar = None
        cls._tam = None

    @classmethod
    def _dame_yunet(cls, ancho: int, alto: int):
        import cv2
        if cls._yunet is None:
            cls._yunet = cv2.FaceDetectorYN.create(
                ruta_modelo(MODELO_DETECTOR), "", (ancho, alto),
                CONFIANZA_MINIMA, 0.3, 5000)
            cls._tam = (ancho, alto)
        elif cls._tam != (ancho, alto):
            # YuNet exige que se le diga el tamaño de entrada. Si cambia y no
            # se le avisa, devuelve coordenadas de otro cuadro: cajas
            # plausibles, en el sitio equivocado.
            cls._yunet.setInputSize((ancho, alto))
            cls._tam = (ancho, alto)
        return cls._yunet

    @classmethod
    def _dame_haar(cls):
        import os

        import cv2
        if cls._haar is None:
            c = cv2.CascadeClassifier(os.path.join(
                cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))
            if c.empty():                             # pragma: no cover
                return None
            cls._haar = c
        return cls._haar


def detecta_rostros(imagen, *, min_lado_frac: float = 0.045) -> list[Rostro]:
    """Rostros en un fotograma. Acepta BGR/RGB (H,W,3) o gris (H,W).

    `min_lado_frac` descarta detecciones más pequeñas que esa fracción del
    alto del cuadro. No es cosmética: un detector produce falsos positivos
    diminutos sobre texturas —una rejilla, un estampado, hojas— y sin el suelo
    un plano general de un jardín «tiene doce caras». Se expresa en fracción y
    no en píxeles para que la medida no cambie al cambiar la resolución de
    análisis.
    """
    if not cv2_disponible():
        return []
    import numpy as np

    arr = np.asarray(imagen)
    alto = int(arr.shape[0])
    ancho = int(arr.shape[1])
    minimo = max(10, int(alto * min_lado_frac))
    salida: list[Rostro] = []

    if tiene_yunet():
        import cv2
        color = arr if arr.ndim == 3 else cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
        color = np.ascontiguousarray(color[:, :, :3].astype(np.uint8))
        try:
            det = _Detector._dame_yunet(ancho, alto)
            _, caras = det.detect(color)
        except Exception as e:                        # pragma: no cover
            logger.debug("[cascaron] YuNet falló: %s", e)
            return []
        if caras is None:
            return []
        for f in caras:
            x, y, w, h = (int(f[0]), int(f[1]), int(f[2]), int(f[3]))
            if w >= minimo and h >= minimo:
                salida.append(Rostro(x, y, w, h, float(f[-1])))
        return salida

    if tiene_haar():                                  # pragma: no cover
        import cv2
        gris = arr if arr.ndim == 2 else cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
        det = _Detector._dame_haar()
        if det is None:
            return []
        try:
            cajas = det.detectMultiScale(
                gris.astype(np.uint8), scaleFactor=1.12, minNeighbors=6,
                minSize=(minimo, minimo))
        except Exception as e:
            logger.debug("[cascaron] Haar falló: %s", e)
            return []
        return [Rostro(int(x), int(y), int(w), int(h))
                for x, y, w, h in cajas]

    return []


def escala_de_plano(rostros: list[Rostro], alto_cuadro: int) -> float | None:
    """Altura del rostro MAYOR como fracción del alto del cuadro.

    El mayor y no la media: en un plano de tres personas a distintas
    distancias, la media describe una escala en la que no está nadie. El
    rostro más grande es el que define cómo de cerca está la cámara del
    sujeto principal, que es lo que la escala de plano quiere decir.
    """
    if not rostros or alto_cuadro <= 0:
        return None
    return max(r.alto for r in rostros) / float(alto_cuadro)


def nombre_de_escala(fraccion: float | None) -> str:
    if fraccion is None:
        return "sin rostro detectado"
    for corte, nombre in ESCALAS:
        if fraccion >= corte:
            return nombre
    return ESCALAS[-1][1]                             # pragma: no cover


def similitud(a, b) -> float:
    """Coseno entre dos firmas de identidad. 1 = idéntico, 0 = sin relación."""
    import numpy as np
    va, vb = np.ravel(np.asarray(a, dtype=float)), np.ravel(
        np.asarray(b, dtype=float))
    na, nb = np.linalg.norm(va), np.linalg.norm(vb)
    if not na or not nb:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def misma_persona(a, b) -> bool:
    return similitud(a, b) >= UMBRAL_MISMA_PERSONA
