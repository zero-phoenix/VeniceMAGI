"""
El cascarón local: escala de plano, identidad, y la honestidad de no verlas.

QUÉ SE COMPRUEBA AQUÍ Y QUÉ NO
==============================
Detectar un rostro de verdad exige un rostro de verdad, y este repositorio no
lleva fotos de nadie ni las va a llevar. Así que estos tests cubren lo que sí
es determinista y lo que más caro sale si se rompe:

  · La aritmética de la escala de plano y su clasificación.
  · Que un fotograma sin caras devuelva CERO y no un falso positivo.
  · Que «no se detectó ningún rostro» NO se convierta en «plano general».
  · Que sin detector o sin modelo se declare, con la instrucción de arreglo.

Que el detector encuentre caras reales figura en `docs/AUTOMODELO.json` como
SIN COMPROBAR, que es la respuesta correcta mientras nadie lo haya corrido
contra material real.
"""
from __future__ import annotations

import pytest

from vmagi.modules.studio import cascaron as C
from vmagi.modules.studio import estilo as E


@pytest.fixture(autouse=True)
def _detector_limpio():
    """Cada test arranca sin nada cacheado y lo deja igual."""
    C._Detector.reinicia()
    yield
    C._Detector.reinicia()


# ============================================ la trampa que ya se pagó

def test_la_deteccion_no_se_decide_por_el_numero_de_version():
    """OpenCV 5 retiró `CascadeClassifier`, y eso se descubrió ejecutándolo.

    La primera versión de este módulo daba por hecho que el clasificador Haar
    viene dentro de OpenCV. Comprobado en cv2 5.0.0:

        AttributeError: module 'cv2' has no attribute 'CascadeClassifier'
        cv2.data.haarcascades: no existe

    El módulo habría importado bien y devuelto cero rostros para siempre, sin
    un solo error — y «cero rostros» se parece muchísimo a «plano general».
    Por eso la disponibilidad se le PREGUNTA a la biblioteca con `hasattr` y
    comprobando el fichero, nunca por una lista de versiones mantenida a mano.
    Es la misma lección que `seedance_admitido`: una regla sobre versiones
    escrita con literales es una lista de nombres que envejece sola.
    """
    assert C.tiene_haar() in (True, False)
    assert C.tiene_yunet() in (True, False)
    # Y el veredicto conjunto nunca puede ser más generoso que sus partes.
    assert C.detector_disponible() == (C.tiene_yunet() or C.tiene_haar())


def test_sin_detector_se_dice_como_arreglarlo_y_no_solo_que_falta():
    """Un informe que dice «no disponible» y nada más no ayuda a nadie.

    Son DOS ausencias distintas y hacen falta dos instrucciones distintas: sin
    OpenCV se instala un paquete, y con OpenCV pero sin el modelo se descarga
    un fichero de 230 KB. El primer intento de este test daba por hecho que la
    ausencia siempre era la segunda, y falló en la máquina de destino —donde
    OpenCV no está— pidiendo que el mensaje nombrase un modelo que todavía no
    viene al caso.
    """
    inf = C.informe_cascaron()
    assert set(inf) >= {"cv2", "detector", "detector_tipo", "identidad",
                        "carpeta_modelos", "falta"}
    assert isinstance(inf["falta"], list)
    if C.detector_disponible():
        return
    texto = " ".join(str(f) for f in inf["falta"])
    assert texto, "no dice nada de por qué no puede ver"
    if not C.cv2_disponible():
        assert "pip install" in texto and "opencv" in texto, (
            f"sin OpenCV hay que decir qué se instala, y dijo: {texto}")
    else:
        assert C.MODELO_DETECTOR in texto, "no dice QUÉ fichero falta"
        assert "opencv_zoo" in texto, "no dice de dónde sacarlo"
        assert str(C.carpeta_modelos()) in texto, "no dice DÓNDE ponerlo"


def test_un_modelo_que_no_esta_devuelve_none_y_no_una_ruta_inventada():
    """`ruta_modelo` tiene que decir «no está», no una ruta que no existe.

    Si devolviera la ruta igualmente, `FaceDetectorYN.create` recibiría un
    fichero inexistente y fallaría dentro del detector, en mitad de una
    medición, con un mensaje de OpenCV en vez de la instrucción de cómo
    arreglarlo.
    """
    assert C.ruta_modelo("no-existe-este-modelo.onnx") is None
    for nombre in (C.MODELO_DETECTOR, C.MODELO_IDENTIDAD):
        r = C.ruta_modelo(nombre)
        assert r is None or (C.carpeta_modelos() / nombre).exists()


def test_el_tipo_de_detector_no_miente():
    inf = C.informe_cascaron()
    if inf["detector"]:
        assert inf["detector_tipo"] in ("yunet", "haar")
    else:
        assert inf["detector_tipo"] is None


# =================================================== escala de plano

def _r(alto: int, ancho: int = 40) -> C.Rostro:
    return C.Rostro(0, 0, ancho, alto)


def test_la_escala_la_marca_el_rostro_mayor_no_la_media():
    """Tres personas a tres distancias.

    La media describe una escala en la que no está nadie. El rostro más
    grande es el que dice cómo de cerca está la cámara del sujeto principal,
    que es lo que la escala de plano significa.
    """
    rostros = [_r(20), _r(60), _r(120)]
    assert C.escala_de_plano(rostros, 400) == pytest.approx(0.30)


@pytest.mark.parametrize("frac,esperado", [
    (0.75, "primerísimo primer plano"),
    (0.45, "primer plano"),
    (0.20, "plano medio"),
    (0.08, "plano americano o general"),
    (0.02, "plano general largo"),
])
def test_la_gramatica_de_plano_clasifica_donde_debe(frac, esperado):
    assert C.nombre_de_escala(frac) == esperado


def test_sin_rostro_la_escala_es_none_y_se_nombra_como_tal():
    """`None` no es cero. Cero sería un plano generalísimo."""
    assert C.escala_de_plano([], 400) is None
    assert C.nombre_de_escala(None) == "sin rostro detectado"


def test_alto_de_cuadro_invalido_no_divide_por_cero():
    assert C.escala_de_plano([_r(50)], 0) is None


def test_un_fotograma_liso_no_tiene_caras():
    """El suelo de tamaño existe para esto: sin él, las texturas son rostros."""
    if not C.detector_disponible():
        pytest.skip("sin detector instalado")
    import numpy as np
    liso = np.full((360, 480, 3), 128, dtype=np.uint8)
    assert C.detecta_rostros(liso) == []


def test_sin_cv2_devuelve_lista_vacia_y_no_revienta(monkeypatch):
    import numpy as np
    monkeypatch.setattr(C, "cv2_disponible", lambda: False)
    assert C.detecta_rostros(np.zeros((10, 10, 3), dtype="uint8")) == []


# ======================================================== identidad

def test_la_similitud_es_coseno_y_se_comporta():
    import numpy as np
    a = np.array([1.0, 0.0, 0.0])
    assert C.similitud(a, a) == pytest.approx(1.0)
    assert C.similitud(a, np.array([0.0, 1.0, 0.0])) == pytest.approx(0.0)
    assert C.similitud(a, np.array([-1.0, 0.0, 0.0])) == pytest.approx(-1.0)


def test_un_vector_nulo_no_es_identico_a_todo():
    """Sin la guarda, 0/0 daría NaN o una división que revienta, y NaN
    comparado con el umbral es False por accidente y no por criterio."""
    import numpy as np
    assert C.similitud(np.zeros(3), np.array([1.0, 2.0, 3.0])) == 0.0


def test_el_umbral_de_misma_persona_se_aplica_de_verdad():
    import numpy as np
    a = np.array([1.0, 0.0])
    casi = np.array([1.0, 0.05])          # coseno ~0.9987
    lejos = np.array([0.2, 1.0])          # coseno ~0.196
    assert C.misma_persona(a, casi) is True
    assert C.misma_persona(a, lejos) is False
    assert 0.0 < C.UMBRAL_MISMA_PERSONA < 1.0


# ============================== integración con el medidor de estilo

async def test_sin_detector_la_escala_queda_sin_medir_no_en_plano_general(
        tmp_path, monkeypatch):
    """EL FALLO MÁS CARO DE ESTE MÓDULO, FIJADO.

    «No se detectó ningún rostro» y «es un plano general» se parecen mucho y
    significan lo contrario. Si la ausencia de detector se tradujera a una
    escala pequeña, un corte entero de primeros planos aprobaría contra una
    biblia de planos generales sin que nadie hubiera mirado una sola imagen.
    """
    monkeypatch.setattr(
        "vmagi.modules.studio.cascaron.detector_disponible", lambda: False)
    m = E.MedidaEstilo()
    await E._mide_rostros(tmp_path / "loquesea.mp4", m)
    assert m.escala_plano is None, "inventó una escala sin detector"
    assert m.escala_plano_nombre == ""
    assert m.no_medido, "se quedó callado en vez de declararlo"


def test_la_escala_entra_en_la_biblia_cuando_se_ha_medido():
    m = E.MedidaEstilo(aspecto=1.85, escala_plano=0.34, camara_px=0.2)
    ejes = {t.eje for t in E.BibliaDeEstilo.desde(m).tolerancias}
    assert "escala_plano" in ejes


def test_la_escala_no_entra_si_no_se_ha_medido():
    """Un eje sin medir no puede convertirse en objetivo. Si entrara con un
    `None` colado como 0, la biblia pediría planos generalísimos."""
    m = E.MedidaEstilo(aspecto=1.85, escala_plano=None, camara_px=0.2)
    ejes = {t.eje for t in E.BibliaDeEstilo.desde(m).tolerancias}
    assert "escala_plano" not in ejes


def test_el_render_de_la_medida_nombra_la_escala():
    m = E.MedidaEstilo(escala_plano=0.42, escala_plano_nombre="primer plano")
    assert "primer plano" in m.render()
