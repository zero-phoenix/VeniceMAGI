"""
El minero de corpus: una película entra, material etiquetado sale.

El informe de Open-Sora 2.0 —el único modelo de vídeo de nivel comercial que
publica lo que costó— atribuye su eficiencia sobre todo a la curación de
datos. Es la parte que todos los planes se saltan porque no es vistosa, y la
que decide si el resto sirve de algo.

Estos tests comprueban lo que hace que un corpus sea un corpus y no una
carpeta con vídeos: que el criterio se aplique, que lo rechazado se declare,
y que dos pasadas den lo mismo.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from vmagi.modules.studio import corpus as C
from vmagi.modules.studio import estilo as E

sin_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="hace falta ffmpeg para fabricar el material")
sin_numpy = pytest.mark.skipif(
    not E.numpy_disponible() or not E.pillow_disponible(),
    reason="hace falta numpy y Pillow")


def _ffmpeg(args: list[str], destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args,
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
         str(destino)], capture_output=True, timeout=180)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")[-600:]
    return destino


@pytest.fixture(scope="module")
def del_genero(tmp_path_factory) -> Path:
    """Cámara clavada, un sujeto cruzando: esto ES el género."""
    d = tmp_path_factory.mktemp("corpus_ok")
    return _ffmpeg(
        ["-f", "lavfi", "-i", "color=c=0x3E5C43:s=480x270:d=9:r=25",
         "-f", "lavfi", "-i", "color=c=0xE8DCC0:s=52x52:d=9:r=25",
         "-filter_complex",
         "[0:v]drawgrid=w=40:h=40:t=2:c=0x8A6A47@0.9[bg];"
         "[bg][1:v]overlay=x='30+42*t':y=110[v]", "-map", "[v]"],
        d / "obra.mp4")


@pytest.fixture(scope="module")
def de_otro_genero(tmp_path_factory) -> Path:
    """Panorámica pura: material correcto, género equivocado."""
    d = tmp_path_factory.mktemp("corpus_no")
    return _ffmpeg(
        ["-f", "lavfi", "-i",
         "color=c=0x3E5C43:s=1600x270:d=9:r=25,"
         "drawgrid=w=40:h=40:t=2:c=0x8A6A47@0.9,"
         "crop=480:270:x='90*t':y=0"],
        d / "pan.mp4")


# ================================================= el criterio

def test_el_criterio_se_puede_leer_y_discutir():
    """Umbrales explícitos, no «los buenos».

    Un criterio que no se puede escribir tampoco se puede discutir, y el
    mismo minero tiene que servir para otro género cambiando los números.
    """
    c = C.CriterioDeGenero()
    assert c.camara_maxima_px > 0
    assert c.plano_minimo_s > 0
    assert 0 < c.fija_minima <= 1
    assert c.sujeto_minimo > 0


def test_una_panoramica_no_es_del_genero():
    m = E.MedidaEstilo(camara_px=6.0, fraccion_camara_fija=0.1,
                       duracion=5.0, sujeto_residual=2.0)
    ok, motivo = C.CriterioDeGenero().juzga(m)
    assert not ok
    assert "cámara se mueve" in motivo


def test_una_foto_larga_tampoco_es_del_genero():
    """Un plano donde NADA se mueve no es cine de cámara fija: es una foto.

    Y enseñarle fotos a un modelo de vídeo es la forma más eficiente de que
    aprenda a no mover nada — el fallo se vería al final del entrenamiento,
    que es el peor momento posible para descubrirlo.
    """
    m = E.MedidaEstilo(camara_px=0.0, fraccion_camara_fija=1.0,
                       duracion=8.0, sujeto_residual=0.01)
    ok, motivo = C.CriterioDeGenero().juzga(m)
    assert not ok
    assert "foto larga" in motivo


def test_un_plano_corto_no_entra():
    m = E.MedidaEstilo(camara_px=0.1, fraccion_camara_fija=1.0,
                       duracion=0.9, sujeto_residual=1.0)
    ok, motivo = C.CriterioDeGenero().juzga(m)
    assert not ok and "dura" in motivo


def test_un_plano_que_empieza_fijo_y_acaba_moviendose_se_caza():
    """La mediana engaña; la fracción de pares quietos no.

    Es justo el caso que un umbral solo sobre `camara_px` dejaría pasar: la
    mitad del plano quieta arrastra la mediana hacia abajo aunque la otra
    mitad sea una panorámica.
    """
    m = E.MedidaEstilo(camara_px=0.9, fraccion_camara_fija=0.5,
                       duracion=6.0, sujeto_residual=1.0)
    ok, motivo = C.CriterioDeGenero().juzga(m)
    assert not ok
    assert "quieto" in motivo


def test_sin_medida_de_camara_no_se_acepta_por_omision():
    """La quinta regla del proyecto, también aquí: «no lo he podido medir»
    no es «cumple». Un clip que entra sin haberse mirado envenena el corpus
    exactamente igual que uno que se midió y estaba mal."""
    m = E.MedidaEstilo(camara_px=None, duracion=6.0)
    ok, motivo = C.CriterioDeGenero().juzga(m)
    assert not ok
    assert "no se pudo medir" in motivo


# ================================================= el minado

@sin_ffmpeg
@sin_numpy
async def test_mina_material_del_genero(del_genero, tmp_path):
    c = await C.mina(del_genero, tmp_path / "corpus")
    assert isinstance(c, C.Corpus), (
        "el minero devuelve siempre el mismo tipo, también cuando no acepta "
        "nada: dos contratos de salida según el resultado obligan al llamador "
        "a adivinar")
    assert c.aceptados, c.render()
    assert c.segundos > 0
    for clip in c.aceptados:
        assert isinstance(clip, C.Clip)
        assert Path(clip.ruta).exists()
        assert clip.duracion >= C.CLIP_MINIMO_S
        # La etiqueta ES la medida. Sin ella el clip es un fichero suelto.
        assert clip.medida.get("camara_px") is not None
        assert clip.medida.get("aspecto") is not None


@sin_ffmpeg
@sin_numpy
async def test_el_material_de_otro_genero_se_rechaza_entero(de_otro_genero,
                                                            tmp_path):
    """Y esto es lo que hace que sea un corpus y no una carpeta.

    Un plano con panorámica no es un ejemplo malo del género: es un ejemplo
    de OTRO género, y meterlo enseña justamente lo que no se quiere.
    """
    c = await C.mina(de_otro_genero, tmp_path / "corpus2")
    assert not c.aceptados, (
        f"aceptó material de panorámica en un corpus de cámara fija: "
        f"{c.render()}")
    assert c.rechazados
    assert any("cámara" in r.motivo for r in c.rechazados)
    # Y lo dice, en vez de dejar una carpeta vacía sin explicación.
    assert "CERO clips aceptados" in c.render()


@sin_ffmpeg
@sin_numpy
async def test_lo_rechazado_se_declara_con_su_motivo(de_otro_genero, tmp_path):
    """Un corpus que no dice qué tiró es un corpus del que no se puede
    aprender por qué salió mal el modelo."""
    c = await C.mina(de_otro_genero, tmp_path / "corpus3")
    texto = c.render()
    assert "rechazados, por qué" in texto
    # Y la medida del rechazado se conserva aunque el fichero se borre: es la
    # única prueba de por qué se tiró.
    for r in c.rechazados:
        assert r.motivo
        if r.medida:
            assert not Path(r.ruta or "no-existe").exists()


@sin_ffmpeg
@sin_numpy
async def test_el_manifiesto_es_jsonl_legible(del_genero, tmp_path):
    """Una línea por clip, no un JSON único.

    Un corpus de miles de clips se lee en streaming durante el
    entrenamiento, y cargar el fichero entero para sacar el ejemplo 4.312 es
    el detalle que convierte «entrenar» en «esperar».
    """
    c = await C.mina(del_genero, tmp_path / "corpus4")
    man = Path(c.manifiesto)
    assert man.exists()
    lineas = [x for x in man.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(lineas) == c.total
    for linea in lineas:
        d = json.loads(linea)          # cada línea, JSON válida por sí sola
        assert "aceptado" in d and "medida" in d

    releido = C.lee_manifiesto(man)
    assert len(releido) == c.total
    assert sum(1 for x in releido if x.aceptado) == len(c.aceptados)


@sin_ffmpeg
@sin_numpy
async def test_dos_pasadas_dan_el_mismo_corpus(del_genero, tmp_path):
    """Lo mínimo exigible a un conjunto de entrenamiento.

    Uno que cambia entre corridas hace que ninguna comparación entre modelos
    signifique nada: no se sabría si mejoró el modelo o cambió el examen. Es
    la misma exigencia que el proyecto ya le pone al troceo de subagentes y
    al propio medidor.
    """
    a = await C.mina(del_genero, tmp_path / "c_a")
    b = await C.mina(del_genero, tmp_path / "c_b")
    assert len(a.aceptados) == len(b.aceptados)
    assert len(a.rechazados) == len(b.rechazados)
    # `strict=True` y no por complacer al linter: si las dos pasadas dieran
    # listas de distinta longitud, un `zip` normal recorrería la corta y el
    # test pasaría habiendo comprobado la mitad. Justo el determinismo que
    # este test existe para vigilar se escaparía en silencio.
    for x, y in zip(a.aceptados, b.aceptados, strict=True):
        assert (x.inicio, x.fin) == (y.inicio, y.fin)
        assert x.medida.get("camara_px") == y.medida.get("camara_px")
        assert x.medida.get("saturacion") == y.medida.get("saturacion")


@sin_ffmpeg
async def test_un_fichero_que_no_existe_no_revienta(tmp_path):
    c = await C.mina(tmp_path / "no-existe.mp4", tmp_path / "c")
    assert not c.aceptados and c.aviso
    assert "no existe" in c.aviso[0]


@sin_ffmpeg
@sin_numpy
async def test_el_tope_se_respeta_y_se_avisa(del_genero, tmp_path):
    c = await C.mina(del_genero, tmp_path / "c_tope", tope=1)
    assert len(c.aceptados) + len(c.rechazados) <= 1
    if c.aviso:
        assert any("tope" in a for a in c.aviso)


# ================================================= alcanzable

def test_el_minero_esta_en_el_registro_del_enjambre():
    from vmagi.core.tools.registry import ToolRegistry
    from vmagi.modules.studio.tools import register_studio_tools

    reg = register_studio_tools(ToolRegistry())
    t = reg.get("minar_corpus")
    assert t is not None, "el enjambre no puede curar su propio corpus"
    assert "write" in (t.access or set())
    assert t.dangerous is True
