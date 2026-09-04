"""
El perito: un testigo que mira, y al que se le hace contrainterrogatorio.

LA AFIRMACIÓN QUE ESTOS TESTS PUEDEN REFUTAR
============================================
«El perito nunca aporta un testimonio que contradiga una medición.»

Se refuta si el perito aprueba un testimonio que falla las preguntas de
control. Ese es el test central de este fichero y está escrito para fallar
si alguien relaja el umbral, olvida barajar las preguntas o —lo más
probable— añade un atajo «si no hay controles, dalo por bueno».

TODO ESTO CORRE SIN MODELO
==========================
El contrainterrogatorio es una función pura sobre un diccionario, a propósito.
Un mecanismo de detección de alucinaciones que solo se puede probar teniendo
instalado el modelo que alucina no se prueba nunca.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

from vmagi.modules.studio import perito as P
from vmagi.modules.studio.estilo import MedidaEstilo

# ========================================================== las de control

def test_las_preguntas_de_control_salen_de_la_medicion_y_no_del_aire():
    m = MedidaEstilo(rgb_medio=(40, 90, 55), luma=70.0, saturacion=0.31)
    ctrl = P.preguntas_de_control(m)

    assert ctrl, "una medida con color, luz y saturación da al menos tres"
    for p in ctrl:
        assert p.es_control
        assert p.esperada in p.opciones, (
            f"«{p.esperada}» no está entre las opciones que se le ofrecen al "
            f"perito: esa pregunta es imposible de acertar")
        assert p.fuente, (
            "una respuesta esperada sin decir de dónde sale pide que se le "
            "crea. El informe tiene que poder enseñar el número")

    porEje = {p.texto: p.esperada for p in ctrl}
    assert porEje["¿Qué color domina la imagen?"] == "verde"
    assert porEje["¿La imagen es clara u oscura?"] == "oscura"


def test_sin_medidas_no_hay_controles_y_eso_bloquea_el_testimonio():
    """Y es la respuesta correcta, no un caso degenerado.

    Sin nada con qué comprobar al testigo, lo honesto es no llamarlo. La
    alternativa —preguntarle igual y creerle— es exactamente el agujero.
    """
    assert P.preguntas_de_control(MedidaEstilo()) == []


# =================================================== el contrainterrogatorio

def _tanda():
    utiles = [P.Pregunta("¿Hay una persona en el cuadro?")]
    control = [
        P.Pregunta("¿Qué color domina la imagen?",
                   opciones=("rojo", "verde", "azul"), esperada="verde"),
        P.Pregunta("¿La imagen es clara u oscura?",
                   opciones=("clara", "oscura"), esperada="oscura"),
        P.Pregunta("¿La imagen tiene colores vivos o está casi en gris?",
                   opciones=("vivos", "gris"), esperada="vivos"),
    ]
    return P.baraja(utiles, control, semilla=7)


def test_un_perito_que_acierta_los_controles_es_admitido():
    tanda = _tanda()
    t = P.evalua({
        "¿Hay una persona en el cuadro?": "sí",
        "¿Qué color domina la imagen?": "verde",
        "¿La imagen es clara u oscura?": "oscura",
        "¿La imagen tiene colores vivos o está casi en gris?": "vivos",
    }, tanda, modelo="smolvlm-256m")

    assert t.aciertos == 3
    assert t.fiable
    assert [r.pregunta for r in t.utiles] == ["¿Hay una persona en el cuadro?"]
    assert "ADMITIDO" not in t.render()      # el rótulo lo pone la herramienta
    assert "controles 3/3" in t.render()


def test_EL_TEST_CENTRAL_un_perito_que_alucina_se_descarta_entero():
    """LA REFUTACIÓN.

    El medidor dice que el fotograma es verde y oscuro. El perito contesta
    que es rojo y claro. Está inventando, y la respuesta que SÍ interesaba
    —«hay una persona»— se cae con todo lo demás, aunque suene razonable.

    Que se caiga la respuesta razonable es el punto entero del mecanismo. Una
    alucinación no viene marcada: viene con la misma cara que un acierto.
    """
    tanda = _tanda()
    t = P.evalua({
        "¿Hay una persona en el cuadro?": "sí",       # plausible, y da igual
        "¿Qué color domina la imagen?": "rojo",       # el medidor dice verde
        "¿La imagen es clara u oscura?": "clara",     # el medidor dice oscura
        "¿La imagen tiene colores vivos o está casi en gris?": "gris",
    }, tanda, modelo="smolvlm-256m")

    assert t.aciertos == 0
    assert not t.fiable, (
        "el perito falló los tres controles y su testimonio se dio por bueno. "
        "Esto es la afirmación del módulo refutada: si esto pasa, el perito "
        "no es un testigo, es una fuente de alucinaciones con formato de "
        "evidencia.")
    assert t.utiles == [], (
        "se descarta la TANDA ENTERA, no solo los controles. Quedarse con la "
        "respuesta útil de un testigo que acaba de mentir tres veces es peor "
        "que no preguntarle")
    assert "DESCARTADO" in t.render() and "alucinando" in t.render()


def test_un_fallo_suelto_no_tumba_el_testimonio():
    """Un modelo de 250 MB falla una de cada tantas por ruido.

    Descartar por un solo fallo tiraría casi todo y el perito no serviría de
    nada. Es el mismo criterio que `deriva_es_concluyente` en Naoko: con
    instrumentos ruidosos, acertar dos de tres es señal y fallar uno es ruido.
    """
    tanda = _tanda()
    t = P.evalua({
        "¿Hay una persona en el cuadro?": "no",
        "¿Qué color domina la imagen?": "verde",
        "¿La imagen es clara u oscura?": "clara",       # el único fallo
        "¿La imagen tiene colores vivos o está casi en gris?": "vivos",
    }, tanda, modelo="smolvlm-256m")

    assert t.aciertos == 2
    assert t.fiable
    assert len(t.utiles) == 1


def test_sin_controles_el_testimonio_no_se_usa():
    """LA DECISIÓN QUE HACE QUE ESTO SIRVA DE ALGO.

    Es tentador dejar pasar el testimonio cuando no hay con qué comprobarlo:
    total, «no se ha demostrado que mienta». Es la quinta regla del proyecto
    al revés — «no he podido comprobarlo» tratado como «está bien».
    """
    t = P.evalua({"¿Hay una persona en el cuadro?": "sí"},
                 [P.Pregunta("¿Hay una persona en el cuadro?")])
    assert not t.fiable
    assert "no había preguntas de control" in t.render()


def test_una_respuesta_en_blanco_cuenta_como_fallo_y_no_como_ausencia():
    """Un modelo que no contesta una pregunta de control no la ha acertado.

    Tratar el silencio como «no evaluable» y sacarlo del denominador deja al
    testigo aprobar callándose justo en las preguntas que lo delatan.
    """
    tanda = _tanda()
    t = P.evalua({"¿Qué color domina la imagen?": "verde"}, tanda)
    assert len(t.controles) == 3, "los tres controles siguen contando"
    assert t.aciertos == 1
    assert not t.fiable


# ============================================================ el desciframiento

def test_una_linea_que_menciona_dos_opciones_se_descarta_por_ambigua():
    """«no es rojo, es verde» contiene las dos palabras.

    Quedarse con la primera que aparece es el falso positivo clásico de leer
    salida libre con un `in`. Aquí se prefiere no tener respuesta a tener una
    inventada por el lector.
    """
    preguntas = [P.Pregunta("¿Qué color domina la imagen?",
                            opciones=("rojo", "verde", "azul"))]
    assert P.descifra("1. no es rojo, es verde", preguntas) == {}
    assert P.descifra("1. verde", preguntas) == {
        "¿Qué color domina la imagen?": "verde"}


def test_se_lee_por_numero_y_no_por_orden_de_aparicion():
    preguntas = [P.Pregunta("A", opciones=("sí", "no")),
                 P.Pregunta("B", opciones=("sí", "no"))]
    # El modelo contesta desordenado, que es lo normal.
    assert P.descifra("2. no\n1. sí", preguntas) == {"A": "sí", "B": "no"}


def test_la_baraja_es_determinista_pero_no_deja_los_controles_al_final():
    utiles = [P.Pregunta(f"útil {i}") for i in range(4)]
    control = [P.Pregunta(f"control {i}", esperada="sí") for i in range(3)]

    a = P.baraja(utiles, control, semilla=3)
    b = P.baraja(utiles, control, semilla=3)
    assert [x.texto for x in a] == [x.texto for x in b], (
        "dos tandas del mismo fotograma tienen que ser la misma tanda, o los "
        "dos testimonios no se pueden comparar")

    posiciones = [i for i, p in enumerate(a) if p.es_control]
    assert posiciones != [4, 5, 6], (
        "los controles quedaron todos al final. Un modelo que atiende peor al "
        "final de un prompt largo fallaría por posición y no por alucinación, "
        "y se descartaría un testimonio bueno")


# ============================================================ la degradación

def test_sin_modelo_lo_dice_y_no_se_inventa_nada():
    hay, motivo = P.disponible()
    assert isinstance(hay, bool)
    assert motivo, "ni disponible ni indisponible sin explicar por qué"
    if not hay:
        assert "modelo" in motivo.lower() or "runtime" in motivo.lower()


async def test_sin_modelo_interroga_devuelve_un_testimonio_vacio_con_motivo():
    hay, _ = P.disponible()
    if hay:
        pytest.skip("hay perito en esta máquina: este test cubre la carencia")
    t = await P.interroga("cualquiera.mp4", MedidaEstilo(luma=10.0),
                          [P.Pregunta("¿hay alguien?")])
    assert isinstance(t, P.Testimonio), (
        "sale SIEMPRE el mismo tipo, también cuando no hay testigo. Dos "
        "contratos de salida según el resultado obligan al llamador a "
        "adivinar cuál le ha tocado")
    assert not t.fiable
    assert t.motivo, "un testimonio ausente sin motivo es indistinguible de uno malo"
    assert t.respuestas == []


# ================================================== el fotograma que se mira

@pytest.mark.skipif(not shutil.which("ffmpeg"),
                    reason="hace falta ffmpeg para sacar el fotograma")
async def test_el_fotograma_se_saca_del_instante_pedido_y_no_del_anterior(
        tmp_path):
    """EL TEST QUE PROTEGE EL CONTRAINTERROGATORIO ENTERO.

    `-ss` delante de `-i` es mucho más rápido y salta al fotograma clave
    anterior. Con eso, el perito miraría un fotograma y los controles se
    habrían calculado sobre otro: fallaría los controles por culpa del
    extractor y se descartaría un testimonio bueno, una y otra vez, sin que
    nada dijera por qué.

    Se comprueba con un vídeo que cambia de color a mitad: si los dos
    fotogramas salen iguales, la búsqueda no está buscando.
    """
    fuente = tmp_path / "dos_colores.mp4"
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "color=c=0x1E5C2E:s=160x90:d=2:r=25",
         "-f", "lavfi", "-i", "color=c=0xD24A28:s=160x90:d=2:r=25",
         "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]",
         "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast",
         "-pix_fmt", "yuv420p", str(fuente)],
        capture_output=True, timeout=120)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")[-400:]

    verde = await P.extrae_fotograma(fuente, 0.5, tmp_path / "a.jpg")
    rojo = await P.extrae_fotograma(fuente, 3.0, tmp_path / "b.jpg")
    assert verde and verde.exists() and rojo and rojo.exists()

    def _medio(ruta) -> tuple[float, float]:
        from PIL import Image
        with Image.open(ruta) as im:
            pix = list(im.convert("RGB").getdata())
        n = len(pix)
        return sum(p[0] for p in pix) / n, sum(p[1] for p in pix) / n

    ra, ga = _medio(verde)
    rb, gb = _medio(rojo)
    assert ga > ra and rb > gb, (
        f"los dos instantes dan la misma imagen (verde={ra:.0f}/{ga:.0f}, "
        f"rojo={rb:.0f}/{gb:.0f}): el extractor no está buscando el segundo "
        f"pedido, así que los controles se calculan sobre un fotograma y el "
        f"perito mira otro")


async def test_un_instante_imposible_devuelve_None_en_vez_de_reventar(tmp_path):
    """Pedir el segundo 90 de un vídeo de 2 no es un fallo del programa: es una
    pregunta sin respuesta, y se contesta con None."""
    assert await P.extrae_fotograma(
        tmp_path / "no_existe.mp4", 3.0, tmp_path / "x.jpg") is None


# ==================================================== alcanzable desde el enjambre

def test_el_perito_esta_en_el_registro_del_enjambre():
    """Regla 3. Unos ojos que solo puedo usar yo desde fuera no son los ojos
    del sistema: son los míos otra vez."""
    from vmagi.core.tools.registry import ToolRegistry
    from vmagi.modules.studio.tools import register_studio_tools

    reg = register_studio_tools(ToolRegistry())
    t = reg.get("interrogar_fotograma")
    assert t is not None, "el enjambre no puede preguntarle nada al perito"
    assert t.description and "control" in t.description.lower()
