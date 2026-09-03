"""
El adversario: material fabricado para que el medidor lo suspenda.

Un medidor calibrado solo contra los casos que se le ocurrieron a quien lo
escribió está descrito, no medido. Los cuatro fallos que la prueba de extremo
a extremo del 2026-09-02 encontró no los cazó ningún test: los cazó ejecutar
el sistema contra material que no estaba hecho para que pasara.

Estos tests comprueban que esa capacidad ahora vive dentro del sistema.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from vmagi.modules.studio import adversario as A
from vmagi.modules.studio import estilo as E

sin_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="hace falta ffmpeg para fabricar el material")
sin_numpy = pytest.mark.skipif(
    not E.numpy_disponible() or not E.pillow_disponible(),
    reason="hace falta numpy y Pillow")


@pytest.fixture(scope="module")
def referencia(tmp_path_factory) -> Path:
    """Cámara clavada, algo moviéndose delante, con textura y color."""
    d = tmp_path_factory.mktemp("adv")
    destino = d / "ref.mp4"
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i",
         "color=c=0x3E5C43:s=480x270:d=6:r=25",
         "-f", "lavfi", "-i", "color=c=0xE8DCC0:s=48x48:d=6:r=25",
         "-filter_complex",
         "[0:v]drawgrid=w=40:h=40:t=2:c=0x8A6A47@0.9[bg];"
         "[bg][1:v]overlay=x='40+50*t':y=110[v]",
         "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast",
         "-pix_fmt", "yuv420p", str(destino)],
        capture_output=True, timeout=180)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")[-600:]
    return destino


# =========================================================== catálogo

def test_hay_un_ataque_para_cada_eje_que_la_biblia_sabe_poner():
    """Si la biblia puede exigir un eje, el adversario tiene que saber
    atacarlo — o decir que no sabe, que también vale, pero por escrito."""
    m = E.MedidaEstilo(
        aspecto=1.85, duracion_media_plano=8.0, camara_px=0.2,
        fraccion_camara_fija=0.98, saturacion=0.25, luma=90.0, contraste=30.0,
        fraccion_silencio=0.3, escala_plano=0.3, turnos_por_minuto=12.0,
        duracion_media_turno=2.0, pausa_media=1.5)
    m.no_medido = []
    ejes = {t.eje for t in E.BibliaDeEstilo.desde(m).tolerancias}
    cubiertos = ejes & set(A.ATAQUES)
    assert cubiertos, "no hay ni un eje con ataque conocido"
    # Los cuatro que definen la dirección de cámara y la paleta, sí o sí.
    assert {"camara_px", "fraccion_camara_fija", "saturacion",
            "contraste"} <= set(A.ATAQUES)


def test_cada_ataque_dice_que_hace_en_castellano():
    """Un informe que dice «eje camara_px: ESCAPA» y nada más no ayuda: quien
    lo lee necesita saber qué se le puso delante al medidor."""
    for eje, (_, desc) in A.ATAQUES.items():
        assert len(desc) > 25, f"{eje}: descripción demasiado pobre"


# ================================================ el ataque funciona

@sin_ffmpeg
@sin_numpy
async def test_el_adversario_caza_una_camara_que_se_mueve(referencia, tmp_path):
    """El eje que más importa para esta dirección artística.

    Y con la comprobación que da sentido al ejercicio: el ataque de cámara NO
    debe tumbar la paleta. Si un contraejemplo viola cuatro ejes a la vez y el
    veredicto lo suspende, no se ha aprendido nada — no se sabe cuál lo
    detectó ni si los otros habrían pasado desapercibidos.
    """
    medida = await E.medir(referencia, procedencia="obra")
    biblia = E.BibliaDeEstilo.desde(medida, holgura=0.2)
    inf = await A.ataca(biblia, referencia, tmp_path / "ataques")

    assert isinstance(inf, A.InformeAdversario), (
        "el adversario devuelve siempre el mismo tipo, también cuando todo "
        "escapa: dos contratos de salida según el resultado obligan al "
        "llamador a adivinar")
    camara = [a for a in inf.ataques if a.eje == "camara_px"]
    assert camara, inf.render()
    a = camara[0]
    assert isinstance(a, A.Ataque)
    assert a.eje and a.descripcion, "un ataque sin nombre ni motivo no informa"
    assert a.ruta and Path(a.ruta).exists(), a.motivo
    assert a.cazado, (
        f"se le puso delante {a.descripcion} y el medidor no lo suspendió por "
        f"camara_px. Suspendió: {a.suspendidos}")
    # LOS COLATERALES SE DECLARAN, NO SE PROHÍBEN, Y AQUÍ ESTÁ EL PORQUÉ.
    # El primer intento de este test exigía que una panorámica no moviera la
    # paleta. Falló, y con razón: mover la cámara cambia QUÉ SE VE, y por
    # tanto cambia el color medio del cuadro. No es un defecto del ataque, es
    # cómo funciona una cámara. Hay ejes que no son independientes, y fingir
    # que lo son produce tests que solo pasan sobre material irreal.
    # Lo exigible es que el eje atacado caiga y que lo demás quede ANOTADO.
    assert isinstance(a.colaterales, list)
    assert a.eje not in a.colaterales


@sin_ffmpeg
@sin_numpy
async def test_el_adversario_caza_el_color_drenado(referencia, tmp_path):
    medida = await E.medir(referencia, procedencia="obra")
    biblia = E.BibliaDeEstilo.desde(medida, holgura=0.2)
    inf = await A.ataca(biblia, referencia, tmp_path / "at2")

    sat = [a for a in inf.ataques if a.eje == "saturacion"]
    assert sat and sat[0].cazado, (
        f"el color drenado a casi gris se le escapó: {inf.render()}")
    # Y NO debe mover la cámara: es un filtro de color.
    assert "camara_px" not in sat[0].colaterales


@sin_ffmpeg
@sin_numpy
async def test_el_ataque_al_montaje_no_toca_ni_color_ni_camara(referencia,
                                                               tmp_path):
    """El montaje no es una propiedad de la imagen, así que su ataque no puede
    ser un filtro de color. Se pica el material y se reordena: cortes DE
    VERDAD, con la misma paleta, la misma luz y la misma cámara."""
    medida = await E.medir(referencia, procedencia="obra")
    biblia = E.BibliaDeEstilo.desde(medida, holgura=0.2)
    inf = await A.ataca(biblia, referencia, tmp_path / "at3")

    mont = [a for a in inf.ataques if a.eje == "duracion_media_plano"]
    assert mont and mont[0].ruta, inf.render()
    a = mont[0]
    picado = await E.medir(a.ruta, procedencia="generado")

    # UN ATAQUE QUE NO ATACA NO PRUEBA CEGUERA, y esta lección se pagó dos
    # veces. Primero con el color —`eq=saturation=0.08` movía la saturación un
    # 15% pidiendo un 92%— y luego aquí: picar y reordenar un plano homogéneo
    # (fondo verde, un objeto pequeño cruzando) no produce cortes visibles,
    # porque los trozos se parecen entre sí. En los dos casos el informe decía
    # «ESCAPA», que se lee como «el medidor es ciego». Mandar a tocar el
    # medidor por eso es el peor resultado posible de una auditoría.
    if not a.aplicable:
        assert "no movió el eje" in a.motivo
        assert a not in inf.escapados, (
            "un ataque inaplicable se está contando como ceguera del medidor")
    else:
        assert picado.planos is not None and picado.planos > 1
        assert a.cazado, inf.render()

    # Lo que sí es exigible siempre: el ataque de montaje no toca el color.
    assert picado.saturacion == pytest.approx(medida.saturacion, rel=0.15), (
        "picar el montaje cambió la saturación: el ataque no es quirúrgico")


@sin_ffmpeg
@sin_numpy
async def test_el_informe_declara_los_ejes_que_no_sabe_atacar(referencia,
                                                              tmp_path):
    """«Sin ataque conocido» NO es «sólido en ese eje».

    Es la quinta regla del proyecto aplicada al propio auditor: no haberlo
    probado no es haberlo aprobado, y contar un eje sin atacar como si
    estuviera comprobado es exactamente la clase de optimismo que este
    repositorio lleva media docena de sesiones desmontando.
    """
    medida = await E.medir(referencia, procedencia="obra")
    medida.fraccion_silencio = 0.42          # eje sin ataque en el catálogo
    biblia = E.BibliaDeEstilo.desde(medida, holgura=0.2)
    inf = await A.ataca(biblia, referencia, tmp_path / "at4")

    assert "fraccion_silencio" in inf.no_atacados
    assert "SIN COMPROBAR" in inf.render()
    assert "sin ataque" in inf.render()


@sin_ffmpeg
@sin_numpy
async def test_un_medidor_ciego_se_declara_ciego(referencia, tmp_path,
                                                 monkeypatch):
    """La prueba que tumbaría al adversario entero.

    Si se rompe el medidor a propósito —aquí, cegándolo al movimiento de
    cámara— el adversario TIENE que decir que ese eje se le escapa. Un
    auditor que aprueba un instrumento roto es peor que no tener auditor:
    da la firma sin haber mirado.
    """
    medida = await E.medir(referencia, procedencia="obra")
    biblia = E.BibliaDeEstilo.desde(medida, holgura=0.2)

    async def ciego(ruta, *, procedencia="desconocida"):
        m = E.MedidaEstilo(ruta=str(ruta), procedencia=procedencia)
        for t in biblia.tolerancias:            # todo perfecto, siempre
            setattr(m, t.eje, t.objetivo)
        return m

    monkeypatch.setattr(A, "medir", ciego)
    inf = await A.ataca(biblia, referencia, tmp_path / "at5")

    assert not inf.solido, "aprobó un medidor que no mira nada"
    assert inf.escapados
    assert "MEDIDOR CIEGO" in inf.render()


# ============================================ alcanzable desde el enjambre

def test_la_auditoria_esta_en_el_registro_del_enjambre():
    """Regla 3. Y aquí pesa el doble: el objetivo declarado es que el sistema
    haga sin supervisión lo mismo que se hace supervisándolo, y elegir qué
    probar era justo lo que seguía haciendo una persona desde fuera."""
    from vmagi.core.tools.registry import ToolRegistry
    from vmagi.modules.studio.tools import register_studio_tools

    reg = register_studio_tools(ToolRegistry())
    t = reg.get("auditar_medidor")
    assert t is not None, "el enjambre no puede auditar su propio medidor"
    assert t.description
    assert "write" in (t.access or set()), "fabrica ficheros: pasa por journal"
