"""
El bucle de autocorrección, con medición real en vez del mock.

`loop.py`, `spec.py` y `rights.py` llevaban desde su creación sin un solo
llamador —el trinquete de huérfanos los señalaba— y el propio docstring de
`loop.py` decía que su función de medida «es un mock». `bucle.py` es el cable
que los une al medidor de estilo. Estos tests comprueban el cable, no las
piezas: que la convergencia venga de medir un fichero, que la meseta corte
antes de gastar la ración, y que los derechos se miren ANTES de generar.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from vmagi.modules.studio import bucle as B
from vmagi.modules.studio import estilo as E

sin_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="hace falta ffmpeg para fabricar el material")
sin_numpy = pytest.mark.skipif(
    not E.numpy_disponible() or not E.pillow_disponible(),
    reason="hace falta numpy y Pillow")


def _video(destino: Path, *, panoramica: bool) -> Path:
    """Dos vídeos: uno de cámara clavada y otro de panorámica pura."""
    if panoramica:
        entrada = ("color=c=0x2E3B4E:s=960x240:d=3:r=25,"
                   "drawgrid=w=32:h=32:t=2:c=white@0.7,crop=320:240:x='70*t':y=0")
    else:
        entrada = ("color=c=0x2E3B4E:s=320x240:d=3:r=25,"
                   "drawgrid=w=32:h=32:t=2:c=white@0.7")
    destino.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", entrada, "-c:v", "libx264",
         "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(destino)],
        capture_output=True, timeout=120)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")[-500:]
    return destino


def _biblia(**kw) -> E.BibliaDeEstilo:
    base = dict(aspecto=1.333, camara_px=0.2, fraccion_camara_fija=0.98,
                saturacion=0.30, luma=70.0, contraste=40.0)
    base.update(kw)
    m = E.MedidaEstilo(**base)
    m.no_medido = []
    return E.BibliaDeEstilo.desde(m, nombre="prueba")


# ================================================= derechos, antes de nada

async def test_los_derechos_se_miran_antes_de_generar_nada():
    """Comprobar después de generar es comprobar cuando el daño ya está hecho.

    Y aquí «el daño» no es abstracto: generar gasta la ración diaria de un
    proveedor guest, que es por IP y por día y no se recupera.
    """
    llamadas = []

    async def generar(v, correcciones):
        llamadas.append(v)
        return None

    r = await B.rueda_hasta_cumplir(
        "un corto protagonizado por una persona famosa", _biblia(), generar)
    assert isinstance(r, B.ResultadoBucle), (
        "el bucle devuelve siempre el mismo tipo, también al bloquear: dos "
        "contratos de salida según por dónde falle es lo que obliga al "
        "llamador a adivinar")
    assert r.estado == "bloqueado"
    assert not llamadas, "generó antes de comprobar los derechos"
    assert "derechos" in r.motivo.lower() or "bloqueado" in r.motivo.lower()


async def test_una_biblia_vacia_no_deja_rodar_un_bucle_sin_juez():
    """`MediaSpec` exige criterios duros, y por buen motivo: un bucle sin
    forma de suspender converge en la primera pasada por definición."""
    vacia = E.BibliaDeEstilo(nombre="vacía")

    async def generar(v, c):                    # pragma: no cover
        raise AssertionError("no debería llegar a generar")

    r = await B.rueda_hasta_cumplir("un corto cualquiera", vacia, generar)
    assert r.estado == "bloqueado"
    assert "hard" in r.motivo or "criterios" in r.motivo.lower()


def test_las_tolerancias_se_vuelven_criterios_duros():
    crit = B.criterios_desde_biblia(_biblia())
    assert crit, "una biblia con ejes produjo cero criterios"
    assert all(c["hard"] for c in crit), (
        "un criterio blando no se puede suspender, y el bucle necesita poder "
        "suspender para poder converger")


# ====================================================== convergencia real

@sin_ffmpeg
@sin_numpy
async def test_converge_cuando_lo_generado_cumple(tmp_path):
    """Y la medida sale de un fichero, no de un doble."""
    fijo = _video(tmp_path / "fijo.mp4", panoramica=False)
    biblia = E.BibliaDeEstilo.desde(
        await E.medir(fijo, procedencia="obra"), holgura=0.25)

    async def generar(v, correcciones):
        return fijo

    r = await B.rueda_hasta_cumplir("plano fijo de un patio", biblia, generar)
    assert r.ok, r.render()
    assert r.version == 1, "gastó pasadas de más sobre algo que ya cumplía"
    assert r.medida is not None and r.medida.camara_px is not None


@sin_ffmpeg
@sin_numpy
async def test_la_meseta_corta_antes_de_gastar_todas_las_pasadas(tmp_path):
    """Un bucle que solo sabe parar al ganar no para nunca al perder.

    Gastaría las cuatro pasadas —y la ración— para entregar lo mismo que tenía
    en la primera. La meseta es la mitad del mecanismo que siempre se olvida.
    """
    fijo = _video(tmp_path / "f.mp4", panoramica=False)
    pan = _video(tmp_path / "p.mp4", panoramica=True)
    biblia = E.BibliaDeEstilo.desde(
        await E.medir(fijo, procedencia="obra"), holgura=0.10)

    pasadas = []

    async def generar(v, correcciones):
        pasadas.append(v)
        return pan                     # siempre lo mismo: no mejora nunca

    r = await B.rueda_hasta_cumplir("plano fijo", biblia, generar,
                                    max_versiones=4)
    assert r.estado == "meseta", r.render()
    assert len(pasadas) < 4, (
        f"gastó {len(pasadas)} pasadas sobre algo que no mejoraba")
    assert "ración" in r.motivo or "mejorar" in r.motivo


@sin_ffmpeg
@sin_numpy
async def test_la_correccion_viaja_a_la_siguiente_pasada(tmp_path):
    """Un veredicto negativo manda la lista concreta, no «hazlo mejor».

    Misma regla que el reintento dirigido del taller de arte. Sin la lista, la
    siguiente pasada solo puede pedir suerte.
    """
    fijo = _video(tmp_path / "f2.mp4", panoramica=False)
    pan = _video(tmp_path / "p2.mp4", panoramica=True)
    biblia = E.BibliaDeEstilo.desde(
        await E.medir(fijo, procedencia="obra"), holgura=0.10)

    recibidas: list[list[str]] = []

    async def generar(v, correcciones):
        recibidas.append(list(correcciones))
        return pan if v == 1 else fijo

    r = await B.rueda_hasta_cumplir("plano fijo", biblia, generar)
    assert recibidas[0] == [], "la primera pasada no tiene nada que corregir"
    assert recibidas[1], "la segunda pasada no recibió qué corregir"
    assert any("camara_px" in c for c in recibidas[1]), recibidas[1]
    assert any("BAJARLO" in c for c in recibidas[1]), recibidas[1]
    assert r.ok, r.render()


@sin_ffmpeg
@sin_numpy
async def test_un_eje_del_contrato_sin_medir_impide_converger(tmp_path):
    """Un corte que el instrumento no supo mirar NO puede converger.

    No tendría ningún desvío en contra precisamente porque nadie lo miró. Es
    la quinta regla del proyecto: «no he podido comprobarlo» no es «está
    bien». Quien la hace cumplir es `compara()`, convirtiendo un eje de la
    biblia que salió `None` en un incumplido.
    """
    fijo = _video(tmp_path / "f3.mp4", panoramica=False)
    biblia = E.BibliaDeEstilo.desde(
        await E.medir(fijo, procedencia="obra"), holgura=0.5)

    async def generar(v, c):
        return tmp_path / "no-existe.mp4"

    r = await B.rueda_hasta_cumplir("plano fijo", biblia, generar)
    assert not r.ok
    assert r.estado in ("meseta", "agotado")


@sin_ffmpeg
@sin_numpy
async def test_no_suspende_por_ejes_que_no_estan_en_el_contrato(tmp_path):
    """EL FALLO DE DISEÑO QUE ESTE TEST FIJA.

    La primera versión sumaba `incumplidos` + `sin_juzgar`, razonando que «no
    he podido comprobarlo» no es «está bien». El razonamiento es correcto; la
    aplicación estaba mal. `sin_juzgar` recoge TODO lo no medido, incluido lo
    que ni siquiera está en el contrato: que el fichero no tenga pista de
    audio cuando la biblia no habla de audio, o que falte el detector de
    rostros cuando la biblia no pide escala de plano.

    Medido: un vídeo comparado contra la biblia sacada de ÉL MISMO daba 3
    incumplidos y entraba en meseta. Un bucle que suspende a su propia
    referencia no converge nunca — y entonces la meseta deja de proteger la
    ración y pasa a garantizar que se gasta entera.
    """
    fijo = _video(tmp_path / "f5.mp4", panoramica=False)
    medida = await E.medir(fijo, procedencia="obra")
    assert medida.no_medido, (
        "este test necesita un fichero con cosas sin medir; si no las hay, "
        "ya no comprueba nada")
    biblia = E.BibliaDeEstilo.desde(medida, holgura=0.25)

    async def generar(v, c):
        return fijo

    r = await B.rueda_hasta_cumplir("plano fijo de un patio", biblia, generar)
    assert r.ok, r.render()
    # Y lo no medido no se pierde: viaja para que se lea.
    assert r.medida is not None and r.medida.no_medido


async def test_un_generador_roto_no_se_diagnostica_como_fallo_de_estilo():
    """«No se generó nada» y «lo generado no cumple» llevan a sitios distintos.

    EL FALLO QUE ESTE TEST FIJA, VISTO EN LA PRUEBA DE EXTREMO A EXTREMO. La
    primera versión metía «la generación no produjo ningún fichero» en la
    lista de correcciones de estilo y devolvía el peor conteo posible. El
    bucle informaba entonces:

        meseta: dos pasadas seguidas sin mejorar ningún eje medible

    ...cuando lo que pasaba es que no se había generado nada las dos veces. El
    diagnóstico correcto —el generador está roto— quedaba enterrado bajo uno
    de dirección artística, y quien leyera el informe se pondría a tocar la
    biblia. Una avería mal nombrada manda a arreglar el sitio equivocado.
    """
    async def generar(v, c):
        return None

    r = await B.rueda_hasta_cumplir("plano fijo", _biblia(), generar)
    assert r.estado == "sin_generar", r.render()
    assert r.fallos_de_generacion >= 2
    assert not r.genero_algo
    assert "generador" in r.motivo, "no señala al generador"
    assert "biblia" in r.motivo, "no dice qué NO hay que tocar"
    assert r.historial, "no dejó rastro de las pasadas perdidas"
    assert "generación no produjo" in r.render()


@sin_ffmpeg
@sin_numpy
async def test_el_informe_dice_que_paso_en_cada_pasada(tmp_path):
    pan = _video(tmp_path / "p3.mp4", panoramica=True)
    fijo = _video(tmp_path / "f4.mp4", panoramica=False)
    biblia = E.BibliaDeEstilo.desde(
        await E.medir(fijo, procedencia="obra"), holgura=0.10)

    async def generar(v, c):
        return pan

    texto = (await B.rueda_hasta_cumplir("x", biblia, generar)).render()
    assert "v1:" in texto and "incumplidos" in texto
    assert "qué seguía fallando" in texto
