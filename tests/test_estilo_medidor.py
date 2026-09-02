"""
El medidor de estilo, comprobado contra material de verdad conocida.

POR QUÉ SE GENERA EL MATERIAL EN VEZ DE USAR UN VÍDEO REAL
==========================================================
Un test que mide un vídeo real solo puede afirmar «devolvió un número». Para
afirmar «devolvió el número CORRECTO» hace falta saber la respuesta de
antemano, y de un fragmento de película no se sabe: es justo lo que se quiere
averiguar.

Así que aquí FFmpeg fabrica tres vídeos cuya verdad se conoce por
construcción:

  · uno con la cámara clavada y un objeto moviéndose por delante,
  · uno que es una panorámica pura, sin nada que se mueva dentro,
  · uno con un número exacto de cortes.

Los dos primeros son la pareja que importa. Contando píxeles que cambian —lo
que hace `observe_video`— los dos dan «se mueve», y son lo contrario el uno
del otro para una dirección de cámara fija. Si el medidor no los separa, no
sirve para lo que se construyó.
"""
from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest

from vmagi.modules.studio import estilo as E

# ------------------------------------------------------------------ utilidad

sin_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="hace falta ffmpeg/ffprobe para fabricar el material de prueba")

sin_numpy = pytest.mark.skipif(
    not E.numpy_disponible() or not E.pillow_disponible(),
    reason="hace falta numpy y Pillow para mirar los fotogramas")


def _ffmpeg(args: list[str], destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           *args, "-c:v", "libx264", "-preset", "ultrafast",
           "-pix_fmt", "yuv420p", str(destino)]
    r = subprocess.run(cmd, capture_output=True, timeout=120)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")[-800:]
    assert destino.exists() and destino.stat().st_size > 0
    return destino


#: Fondo con TEXTURA. Un fondo liso no sirve para medir desplazamiento: sin
#: detalle, todos los desplazamientos empatan y el estimador devolvería cero
#: incluso durante una panorámica. La rejilla da esquinas que enganchar.
_FONDO = "color=c=0x2E3B4E:s=320x240:d=4:r=25,drawgrid=w=32:h=32:t=2:c=white@0.7"


@pytest.fixture(scope="module")
def camara_fija(tmp_path_factory) -> Path:
    """Cámara clavada, un objeto cruzando el cuadro."""
    d = tmp_path_factory.mktemp("estilo")
    # DOS TRAMPAS, LAS DOS PAGADAS AL CALIBRAR ESTE FIXTURE
    #
    # 1. El objeto va en BLANCO, no en rojo. El primer intento usaba rojo
    #    puro sobre el azul del fondo y el residual salió 0,013: en
    #    luminancia, `0xFF0000` (54) y `0x2E3B4E` (56) son el mismo gris. El
    #    objeto cruzaba el cuadro y el medidor no lo veía. La medida era
    #    correcta; la pregunta estaba mal hecha.
    # 2. Se mueve con `overlay`, no con `drawbox`. En este FFmpeg (4.4),
    #    `drawbox=x='30+45*t'` NO evalúa la expresión por fotograma:
    #    verificado extrayendo los fotogramas, `mean|a-b| = 0.0` y cero
    #    píxeles por encima de 200 en todo el vídeo. Es decir, el fixture
    #    "con movimiento" era una foto fija — y sin comprobarlo, el test
    #    habría acusado al medidor de no ver un movimiento que no existía.
    return _ffmpeg(
        ["-f", "lavfi", "-i", "color=c=0x2E3B4E:s=320x240:d=4:r=25",
         "-f", "lavfi", "-i", "color=c=white:s=44x44:d=4:r=25",
         "-filter_complex",
         "[0:v]drawgrid=w=32:h=32:t=2:c=white@0.7[bg];"
         "[bg][1:v]overlay=x='30+45*t':y=95[v]",
         "-map", "[v]"],
        d / "fija.mp4")


@pytest.fixture(scope="module")
def camara_panoramica(tmp_path_factory) -> Path:
    """Panorámica pura: nada se mueve dentro, se mueve la cámara."""
    d = tmp_path_factory.mktemp("estilo")
    return _ffmpeg(
        ["-f", "lavfi", "-i",
         "color=c=0x2E3B4E:s=960x240:d=4:r=25,"
         "drawgrid=w=32:h=32:t=2:c=white@0.7,"
         "crop=320:240:x='70*t':y=0"],
        d / "pan.mp4")


@pytest.fixture(scope="module")
def cuatro_planos(tmp_path_factory) -> Path:
    """Cuatro colores de 2 s: tres cortes exactos, cuatro planos."""
    d = tmp_path_factory.mktemp("estilo")
    partes = []
    for i, c in enumerate(("0x802020", "0x208020", "0x202080", "0xE0E0A0")):
        partes += ["-f", "lavfi", "-i",
                   f"color=c={c}:s=320x240:d=2:r=25,"
                   f"drawgrid=w=40:h=40:t={i + 1}:c=black@0.8"]
    partes += ["-filter_complex",
               "[0:v][1:v][2:v][3:v]concat=n=4:v=1:a=0[v]", "-map", "[v]"]
    return _ffmpeg(partes, d / "cortes.mp4")


# =============================================================== los ojos

@sin_ffmpeg
@sin_numpy
async def test_separa_camara_fija_de_panoramica(camara_fija, camara_panoramica):
    """La prueba que tumba el medidor entero si falla.

    Los dos vídeos tienen movimiento. Uno lo tiene DELANTE de la cámara y el
    otro EN la cámara. Si el instrumento no los distingue, no puede juzgar una
    dirección de cámara fija y todo lo que se construya encima es decorado.
    """
    fija = await E.medir(camara_fija, procedencia="generado")
    pan = await E.medir(camara_panoramica, procedencia="generado")

    assert fija.camara_px is not None, f"no midió: {fija.no_medido}"
    assert pan.camara_px is not None, f"no midió: {pan.no_medido}"

    # La cámara clavada tiene que dar prácticamente cero.
    assert fija.camara_px <= E.UMBRAL_CAMARA_FIJA, (
        f"cámara clavada medida como {fija.camara_px}px, umbral "
        f"{E.UMBRAL_CAMARA_FIJA}")
    # La panorámica, claramente por encima.
    assert pan.camara_px > E.UMBRAL_CAMARA_FIJA, (
        f"panorámica medida como {pan.camara_px}px: el estimador no la vio")
    assert pan.camara_px > fija.camara_px * 2 + 1, (
        f"fija={fija.camara_px} pan={pan.camara_px}: no las separa lo "
        f"bastante para poder decidir con esto")

    # Y la fracción de planos fijos tiene que ordenarlas igual.
    assert fija.fraccion_camara_fija > pan.fraccion_camara_fija


@sin_ffmpeg
@sin_numpy
async def test_camara_fija_no_se_confunde_con_congelado(camara_fija):
    """Cámara quieta NO es imagen congelada, y el residual lo demuestra.

    `observe_video` caza el congelado contando píxeles. Aquí hace falta lo
    contrario: confirmar que hay VIDA delante de una cámara que no se mueve.
    Sin el residual de sujeto, «cámara fija» y «foto fija de cuatro segundos»
    darían la misma medida.
    """
    m = await E.medir(camara_fija, procedencia="generado")
    assert m.camara_px is not None and m.sujeto_residual is not None
    assert m.camara_px <= E.UMBRAL_CAMARA_FIJA
    assert m.sujeto_residual > 0.5, (
        f"residual de sujeto {m.sujeto_residual}: el objeto rojo cruza el "
        f"cuadro y el medidor no lo ve")


@sin_ffmpeg
@sin_numpy
async def test_cuenta_los_cortes_que_hay(cuatro_planos):
    m = await E.medir(cuatro_planos, procedencia="obra")
    assert m.planos == 4, f"se fabricaron 4 planos y contó {m.planos}"
    assert m.duracion_media_plano is not None
    assert 1.6 <= m.duracion_media_plano <= 2.4, m.duracion_media_plano


def test_el_etalonaje_entra_en_el_grafo_de_filtros():
    """La palanca de paleta tiene que llegar a FFmpeg, con y sin Ken Burns.

    Función pura, así que se comprueba sin arrancar FFmpeg — el mismo motivo
    por el que `build_filtergraph` está separada de la ejecución. Y las dos
    ramas, porque son dos cadenas de filtros distintas y es exactamente el
    sitio donde una se arregla y la otra se olvida.
    """
    from vmagi.modules.studio.video import Slide, VideoSpec, build_filtergraph

    diapos = [Slide("a.png", 2.0), Slide("b.png", 2.0)]
    for ken in (True, False):
        sin = build_filtergraph(VideoSpec(slides=diapos, ken_burns=ken))
        con = build_filtergraph(VideoSpec(slides=diapos, ken_burns=ken,
                                          grado="saturation=0.700"))
        assert "eq=" not in sin, f"ken_burns={ken}: metió eq sin pedirlo"
        assert con.count("eq=saturation=0.700") == len(diapos), (
            f"ken_burns={ken}: el etalonaje no llegó a todas las diapositivas")
        # Va al final de la cadena de cada una, después del escalado.
        assert "eq=saturation=0.700[v0]" in con, con[:200]


def test_un_encadenado_es_un_corte_y_no_tres():
    """La función pura, con los casos que importan.

    Un corte seco es un pico aislado. Un encadenado de medio segundo, a 5
    muestras por segundo, son dos o tres pares seguidos por encima del umbral.
    Contarlos sueltos multiplica los planos y divide su duración.
    """
    assert E._une_transiciones([]) == []
    # tres cortes secos, separados
    assert E._une_transiciones([4, 19, 33]) == [4, 19, 33]
    # un encadenado de tres muestras seguidas -> un solo corte
    assert len(E._une_transiciones([10, 11, 12])) == 1
    # mezcla: seco, encadenado, seco
    assert len(E._une_transiciones([3, 20, 21, 22, 40])) == 3


@sin_ffmpeg
@sin_numpy
async def test_una_animatica_encadenada_no_duplica_los_planos(
        tmp_path_factory):
    """EL FALLO QUE ESTE TEST FIJA, MEDIDO DE VERDAD.

    Una animática de TRES imágenes con encadenados salía con SEIS planos, y la
    duración media de plano a la mitad de la real. Eso no se quedó en un
    número feo: el bucle de autocorrección leyó «los planos duran poco,
    SÚBELOS» y subió de 6 a 15,36 segundos por plano persiguiendo un objetivo
    inalcanzable, porque el error estaba en el recuento y no en la duración.

    Una medida mal hecha no da un informe peor: da un sistema que corrige en
    la dirección equivocada con toda la autoridad de un dato.
    """
    d = tmp_path_factory.mktemp("encadenado")
    imgs = []
    for i, c in enumerate(("0x802020", "0x208020", "0x202080")):
        p = d / f"i{i}.png"
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i",
             f"color=c={c}:s=320x240,drawgrid=w=40:h=40:t=3:c=white@0.6",
             "-frames:v", "1", str(p)], capture_output=True, timeout=60)
        assert r.returncode == 0
        imgs.append(p)

    from vmagi.modules.studio.video import Slide, VideoSpec, render_slideshow
    salida = d / "animatica.mp4"
    obs = await render_slideshow(
        VideoSpec(slides=[Slide(str(p), 3.0) for p in imgs],
                  width=640, height=360, ken_burns=False, crossfade=0.5),
        salida)
    assert salida.exists(), obs.problems

    m = await E.medir(salida, procedencia="generado")
    assert m.planos == 3, (
        f"tres imágenes encadenadas midieron {m.planos} planos. Cada "
        f"transición gradual se está contando como varios cortes.")


@sin_ffmpeg
@sin_numpy
async def test_bajar_el_contraste_no_borra_los_cortes(cuatro_planos,
                                                      tmp_path_factory):
    """Un corte es un cambio de CONTENIDO, no de EXPOSICIÓN.

    EL ACOPLAMIENTO QUE ESTE TEST FIJA, ENCONTRADO EJECUTANDO EL SISTEMA.
    En cuanto el bucle de autocorrección aprendió a etalonar para acercar la
    paleta a la biblia, empezó a aplanar el contraste, y al aplanarlo los
    histogramas de dos planos distintos se parecían lo bastante como para
    caer por debajo del umbral: los cortes desaparecían.

    Medido: el mismo montaje pasaba de 3 planos a 2, la duración media de
    plano se disparaba de 5,7 s a 13,9 s, y el bucle se ponía a corregir la
    duración por un cambio que había hecho él mismo en el color. Corregir un
    eje rompía la medición de otro, y el sistema perseguía su propio reflejo.
    """
    d = tmp_path_factory.mktemp("etalonado")
    plano = _ffmpeg(["-i", str(cuatro_planos),
                     "-vf", "eq=contrast=0.42:brightness=-0.1:saturation=0.37"],
                    d / "aplanado.mp4")

    original = await E.medir(cuatro_planos, procedencia="obra")
    grisaceo = await E.medir(plano, procedencia="generado")

    assert original.planos == 4, original.planos
    assert grisaceo.planos == original.planos, (
        f"el mismo montaje con el contraste bajado midió "
        f"{grisaceo.planos} planos en vez de {original.planos}. El detector "
        f"de cortes está midiendo exposición, no contenido.")
    # Y el contraste sí tiene que haber bajado: si no, el test no probó nada.
    assert grisaceo.contraste < original.contraste * 0.75, (
        f"el etalonaje no llegó a aplicarse ({grisaceo.contraste} vs "
        f"{original.contraste}), así que este test no comprobó nada")


@sin_ffmpeg
@sin_numpy
async def test_mide_el_aspecto_de_la_imagen_no_el_del_contenedor(
        tmp_path_factory):
    """Un 16:9 metido en un contenedor 4:3 con barras negras.

    Es exactamente cómo llegan los tráileres antiguos. `ffprobe` diría 1.333;
    la imagen es 1.778. Comparar encuadres con el número del contenedor
    compara envases.
    """
    d = tmp_path_factory.mktemp("estilo_ar")
    v = _ffmpeg(
        ["-f", "lavfi", "-i",
         "color=c=0x40608A:s=320x180:d=2:r=25,"
         "drawgrid=w=32:h=32:t=2:c=white@0.8,"
         "pad=320:240:0:30:black"],
        d / "buzon.mp4")
    m = await E.medir(v, procedencia="obra")
    assert m.aspecto_contenedor == pytest.approx(320 / 240, abs=0.01)
    assert m.aspecto is not None, m.no_medido
    assert m.aspecto == pytest.approx(320 / 180, rel=0.06), (
        f"aspecto de imagen {m.aspecto}, se esperaba ~1.778 (leyó el "
        f"contenedor en vez de los píxeles)")


# ============================================================== los oídos

@sin_ffmpeg
@sin_numpy
async def test_mide_silencio_y_banda_de_voz(tmp_path_factory):
    """Un tono en la banda de la voz, con la mitad del tiempo en silencio."""
    d = tmp_path_factory.mktemp("estilo_audio")
    v = _ffmpeg(
        ["-f", "lavfi", "-i", "color=c=gray:s=160x120:d=4:r=25",
         "-f", "lavfi", "-i",
         "sine=frequency=900:duration=4:sample_rate=16000,"
         "volume='if(lt(t,2),1,0)':eval=frame",
         "-shortest", "-c:a", "aac"],
        d / "sonido.mp4")
    m = await E.medir(v, procedencia="generado")
    assert m.tiene_audio is True, m.no_medido
    assert m.rms_medio is not None and m.rms_medio > 0
    assert m.fraccion_silencio is not None
    assert 0.3 <= m.fraccion_silencio <= 0.7, (
        f"la mitad del audio es silencio y midió {m.fraccion_silencio:.0%}")
    assert m.fraccion_banda_voz is not None
    assert m.fraccion_banda_voz > 0.8, (
        f"un tono de 900 Hz está de lleno en la banda 300-3400 y midió "
        f"{m.fraccion_banda_voz:.0%}")


def _con_audio(expr: str, dur: float, destino: Path) -> Path:
    """Vídeo mudo con un tono al que se le enciende y apaga el volumen.

    La cadencia queda fijada por la expresión, así que el número de turnos y
    la longitud de cada pausa se conocen de antemano — que es lo único que
    permite decir si el medidor acertó, y no solo si devolvió algo.
    """
    return _ffmpeg(
        ["-f", "lavfi", "-i", f"color=c=gray:s=160x120:d={dur}:r=25",
         "-f", "lavfi", "-i",
         f"sine=frequency=700:duration={dur}:sample_rate=16000,"
         f"volume='{expr}':eval=frame",
         "-shortest", "-c:a", "aac"],
        destino)


@sin_ffmpeg
@sin_numpy
async def test_cuenta_los_turnos_de_dialogo_que_hay(tmp_path_factory):
    """Seis turnos de 1 s separados por pausas de 0,5 s. Se sabe la respuesta.

    Es la medida que sustituye a la diarización sin fingir que lo es: no dice
    quién habla, dice a qué ritmo se habla. Para una dirección donde lo
    importante es lo que no se dice, esa es la cifra que gobierna.
    """
    d = tmp_path_factory.mktemp("turnos")
    v = _con_audio("if(lt(mod(t,1.5),1.0),1,0)", 9.0, d / "ritmo.mp4")
    m = await E.medir(v, procedencia="obra")

    assert m.turnos_por_minuto is not None, m.no_medido
    # 6 turnos en 9 s = 40 por minuto.
    assert 33 <= m.turnos_por_minuto <= 47, (
        f"6 turnos en 9 s son 40/min y midió {m.turnos_por_minuto}")
    assert m.duracion_media_turno == pytest.approx(1.0, abs=0.18)
    assert m.pausa_media == pytest.approx(0.5, abs=0.15)


@sin_ffmpeg
@sin_numpy
async def test_la_pausa_larga_no_se_diluye_en_la_media(tmp_path_factory):
    """Tres turnos, una pausa de 0,4 s y otra de 3 s.

    POR QUÉ VAN SEPARADAS `pausa_media` Y `pausa_maxima`. Un silencio de tres
    segundos en mitad de una conversación es una decisión de dirección. La
    media lo entierra: 1,7 s no se parece ni a 0,4 ni a 3, y describe una
    escena que no existe.
    """
    d = tmp_path_factory.mktemp("pausa")
    v = _con_audio(
        "if(lt(t,1),1,if(between(t,1.4,2.4),1,if(between(t,5.4,6.4),1,0)))",
        7.0, d / "pausa.mp4")
    m = await E.medir(v, procedencia="obra")

    assert m.pausa_maxima is not None, m.no_medido
    assert m.pausa_maxima == pytest.approx(3.0, abs=0.3), m.pausa_maxima
    assert m.pausa_media == pytest.approx(1.7, abs=0.35), m.pausa_media
    assert m.pausa_maxima > m.pausa_media * 1.4, (
        "la pausa larga quedó diluida: el eje no distingue una decisión de "
        "dirección de un hueco corriente")


@sin_ffmpeg
@sin_numpy
async def test_la_respiracion_dentro_de_una_frase_no_cuenta_como_turno(
        tmp_path_factory):
    """Cuatro bloques de sonido separados por huecos de 0,15 s: UNA réplica.

    Sin coser los huecos cortos, cada respiración partiría el turno y la
    cadencia medida sería la de las sílabas, no la de la conversación. Es el
    modo de fallo obvio de contar tramos de energía a pelo, y por eso hay un
    test que lo fija.
    """
    d = tmp_path_factory.mktemp("respira")
    v = _con_audio("if(lt(mod(t,1.15),1.0),1,0)", 4.6, d / "respira.mp4")
    m = await E.medir(v, procedencia="obra")

    assert m.turnos_por_minuto is not None, m.no_medido
    turnos = m.turnos_por_minuto * (4.6 / 60.0)
    assert turnos <= 2.4, (
        f"cosió mal: {turnos:.1f} turnos donde hay una sola réplica con "
        f"respiraciones de 0,15 s")


@sin_ffmpeg
@sin_numpy
async def test_el_ritmo_de_un_trailer_no_entra_en_la_biblia(tmp_path_factory):
    """Un tráiler corta el diálogo en frases sueltas con música encima.

    Su cadencia es la del departamento de marketing. Si entrara en la biblia,
    el sistema perseguiría ese ritmo creyendo que persigue el del director.
    """
    d = tmp_path_factory.mktemp("trailer_ritmo")
    v = _con_audio("if(lt(mod(t,1.5),1.0),1,0)", 9.0, d / "tr.mp4")
    m = await E.medir(v, procedencia="trailer")
    assert m.turnos_por_minuto is not None, "medirlo sí; usarlo de objetivo no"

    ejes = {t.eje for t in E.BibliaDeEstilo.desde(m).tolerancias}
    assert not ({"turnos_por_minuto", "duracion_media_turno", "pausa_media"}
                & ejes), f"el ritmo del tráiler se coló en la biblia: {ejes}"


@sin_ffmpeg
async def test_sin_pista_de_audio_lo_dice_y_no_inventa(tmp_path_factory):
    d = tmp_path_factory.mktemp("estilo_mudo")
    v = _ffmpeg(["-f", "lavfi", "-i", "color=c=gray:s=160x120:d=1:r=25"],
                d / "mudo.mp4")
    m = await E.medir(v, procedencia="generado")
    assert m.tiene_audio is False
    assert m.rms_medio is None, "inventó un RMS sobre un fichero sin audio"
    assert any("audio" in s for s in m.no_medido)


# ========================================================== honestidad

async def test_sin_ffmpeg_no_devuelve_ceros(tmp_path, monkeypatch):
    """Sin instrumento no hay medida, y eso NO son ceros.

    El agujero equivalente ya se pagó en `observe_video`: sin Pillow devolvía
    `ok=True` sobre una captura que no llegó a abrir. Un cero en un eje de
    estilo es peor: «movimiento de cámara 0» es exactamente lo que se busca,
    así que un cero por no haber medido APRUEBA el corte.
    """
    f = tmp_path / "x.mp4"
    f.write_bytes(b"no soy un video")
    monkeypatch.setattr(E, "ffmpeg_disponible", lambda: False)
    m = await E.medir(f)
    assert m.camara_px is None and m.aspecto is None
    assert m.no_medido and "ffmpeg" in m.no_medido[0]
    assert not m.completa


async def test_un_binario_que_no_existe_da_EstiloError_con_el_motivo():
    """Nunca un `FileNotFoundError` pelado subiendo por la pila.

    `_corre` es la única puerta a subprocesos de este módulo. Si deja escapar
    el error del sistema operativo, el llamador recibe un mensaje que habla de
    ficheros cuando el problema es que falta una herramienta — y ese es el
    tipo de diagnóstico que hace perder una tarde.
    """
    with pytest.raises(E.EstiloError) as exc:
        await E._corre(["binario-que-no-existe-en-ninguna-parte"])
    assert "no está instalado" in str(exc.value)


async def test_fichero_inexistente_no_revienta(tmp_path):
    m = await E.medir(tmp_path / "no-existe.mp4")
    assert not m.completa
    assert any("no existe" in s for s in m.no_medido)


# ====================================================== biblia y veredicto

def _medida(**kw) -> E.MedidaEstilo:
    base = dict(aspecto=1.85, duracion_media_plano=18.0, camara_px=0.3,
                fraccion_camara_fija=0.97, saturacion=0.21, luma=118.0,
                contraste=44.0, fraccion_silencio=0.34)
    base.update(kw)
    return E.MedidaEstilo(**base)


def test_biblia_de_un_trailer_no_dicta_el_montaje():
    """De un tráiler no se puede sacar la duración de plano de la película.

    La corta el montador del tráiler. Si esa cifra entrase en la biblia, el
    sistema perseguiría el ritmo del departamento de marketing creyendo que
    persigue el del director — y lo haría con toda la autoridad de un número.
    """
    b_obra = E.BibliaDeEstilo.desde(
        _medida(), nombre="obra")
    m_trailer = _medida()
    m_trailer.procedencia = "trailer"
    b_trailer = E.BibliaDeEstilo.desde(m_trailer, nombre="trailer")

    ejes_obra = {t.eje for t in b_obra.tolerancias}
    ejes_trailer = {t.eje for t in b_trailer.tolerancias}

    assert "duracion_media_plano" in ejes_obra
    assert "duracion_media_plano" not in ejes_trailer
    # Lo que SÍ sobrevive a un tráiler, porque los planos son de la película.
    assert {"aspecto", "camara_px", "saturacion"} <= ejes_trailer


def test_camara_es_tope_no_objetivo():
    """Moverse MENOS de lo permitido nunca es un incumplimiento."""
    biblia = E.BibliaDeEstilo.desde(_medida(camara_px=0.8))
    quieta = _medida(camara_px=0.0)
    quieta.no_medido = []
    v = E.compara(quieta, biblia)
    fallo = [d for d in v.incumplidos if d.eje == "camara_px"]
    assert not fallo, "penalizó una cámara MÁS quieta que la referencia"


def test_una_panoramica_no_aprueba_contra_una_biblia_de_camara_fija():
    biblia = E.BibliaDeEstilo.desde(_medida(camara_px=0.3))
    pan = _medida(camara_px=6.4, fraccion_camara_fija=0.10)
    pan.no_medido = []
    v = E.compara(pan, biblia)
    assert not v.aprueba
    ejes = {d.eje for d in v.incumplidos}
    assert "camara_px" in ejes and "fraccion_camara_fija" in ejes
    # Y el reintento tiene que decir en qué dirección corregir.
    frases = v.lista_para_reintento()
    assert any("BAJARLO" in f for f in frases), frases


def test_un_eje_sin_medir_no_aprueba_por_omision():
    """La quinta regla del proyecto, aplicada al veredicto.

    Un corte cuyo movimiento de cámara no se pudo medir NO puede aprobar: no
    tiene ningún desvío en contra precisamente porque nadie lo miró.
    """
    biblia = E.BibliaDeEstilo.desde(_medida())
    ciego = _medida(camara_px=None)
    ciego.no_medido = ["Pillow no instalado: los fotogramas no se han mirado"]
    v = E.compara(ciego, biblia)
    assert not v.aprueba
    assert v.sin_juzgar
    assert any(d.eje == "camara_px" and not d.cumple for d in v.desvios)


def test_medida_limpia_contra_su_propia_biblia_aprueba():
    """Compuerta de cordura: el instrumento no puede suspender a la referencia.

    Si medir la referencia y compararla contra la biblia sacada de ella misma
    no aprueba, el instrumento no es determinista y ninguna otra comparación
    significa nada.
    """
    m = _medida()
    m.no_medido = []
    v = E.compara(m, E.BibliaDeEstilo.desde(m))
    assert v.aprueba, v.render()


@sin_ffmpeg
@sin_numpy
async def test_el_instrumento_es_determinista(camara_fija):
    """Dos pasadas sobre el mismo fichero dan lo mismo.

    Sin esto no hay compuerta medible: una diferencia entre referencia y
    salida podría ser del instrumento. Es la misma exigencia que el proyecto
    ya le pone al troceo de subagentes.
    """
    a = await E.medir(camara_fija, procedencia="generado")
    b = await E.medir(camara_fija, procedencia="generado")
    for eje in ("aspecto", "planos", "camara_px", "fraccion_camara_fija",
                "saturacion", "luma", "contraste", "sujeto_residual"):
        assert getattr(a, eje) == getattr(b, eje), (
            f"{eje} cambió entre dos pasadas: {getattr(a, eje)} -> "
            f"{getattr(b, eje)}")


# ============================================ el enjambre alcanza el instrumento

def _registro():
    from vmagi.core.tools.registry import ToolRegistry
    from vmagi.modules.studio.tools import register_studio_tools
    return register_studio_tools(ToolRegistry())


def test_las_tres_herramientas_de_estilo_estan_registradas():
    """Regla 3: cada capacidad tiene que poder invocarse desde la interfaz.

    Un medidor que solo puede llamar quien supervisa desde fuera no acerca al
    sistema a ser autónomo ni un paso. El objetivo declarado es que MAGI haga
    sin supervisión lo mismo que se hace supervisándolo, y para eso los ojos
    tienen que estar donde el enjambre los alcanza.
    """
    reg = _registro()
    for nombre in ("medir_estilo", "biblia_de_estilo", "juzgar_estilo"):
        t = reg.get(nombre)
        assert t is not None, f"'{nombre}' no está en el registro del enjambre"
        assert t.description, f"'{nombre}' sin descripción: el modelo no sabe cuándo usarla"


def test_la_biblia_declara_que_escribe_en_disco():
    """Escribir un fichero pasa por el panel de aprobación, no por detrás."""
    t = _registro().get("biblia_de_estilo")
    assert "write" in (t.access or set())
    assert t.dangerous is True


def test_juzgar_no_pide_permiso_de_escritura():
    """Juzgar solo lee y mide. Si pidiera escritura, un juicio podría tocar
    el artefacto que juzga — que es la razón por la que Ritsuko tampoco
    escribe: un auditor con permiso para arreglar deja de ser auditor."""
    t = _registro().get("juzgar_estilo")
    assert "write" not in (t.access or set())


@sin_ffmpeg
@sin_numpy
async def test_el_bucle_completo_referencia_biblia_juicio(
        camara_fija, camara_panoramica, tmp_path):
    """El circuito entero, de punta a punta, sin modelo por medio.

    Referencia de cámara fija -> biblia -> se juzga una panorámica. Tiene que
    suspenderla Y decir en qué dirección corregir. Es el bucle de
    autocorrección de `loop.py`, que hasta ahora corría contra un mock.
    """
    reg = _registro()
    biblia = tmp_path / "biblia.json"

    r = await reg.get("biblia_de_estilo").handler(
        referencia=str(camara_fija), out_path=str(biblia),
        nombre="kore-eda-sintetico", procedencia="obra")
    assert r.ok, r.error
    assert biblia.exists()

    bueno = await reg.get("juzgar_estilo").handler(
        path=str(camara_fija), biblia=str(biblia))
    malo = await reg.get("juzgar_estilo").handler(
        path=str(camara_panoramica), biblia=str(biblia))

    assert malo.meta["aprueba"] is False
    assert "camara_px" in malo.meta["incumplidos"]
    assert malo.meta["reintento"], "suspendió sin decir qué corregir"
    assert any("BAJARLO" in f for f in malo.meta["reintento"])
    # La referencia contra su propia biblia no puede salir peor que la
    # panorámica: si sale peor, el instrumento no es una vara de medir.
    assert len(bueno.meta["incumplidos"]) < len(malo.meta["incumplidos"])


def test_informe_del_instrumento_no_miente():
    inf = E.informe_instrumento()
    assert set(inf) == {"ffmpeg", "ffprobe", "numpy", "pillow"}
    assert inf["ffmpeg"] == (shutil.which("ffmpeg") is not None)
    assert all(isinstance(v, bool) for v in inf.values())
