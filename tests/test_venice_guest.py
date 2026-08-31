"""El nucleo cloud-first: sitios guest, racion y contenedor virtual.

Estos tests fijan las promesas del manifiesto de VeniceMAGI que un
refactor puede romper sin que nada explote:

  · «Sin cuenta ni key obligatoria en modo cloud»  -> ningun sitio del
    camino principal puede exigir credenciales.
  · «Ración visible ... y cache LRU para que repetir no gaste cupo»  ->
    la cache SE CONSULTA (la v1 nunca la consultaba) y el contador cuenta
    solo llamadas reales.
  · «Sin evasion de cuotas»                        -> ver test_ritsuko_vpn.
  · Transparencia                                  -> un sitio que no sabe
    hacer algo lo dice, no lo intenta y falla tarde.
"""
from __future__ import annotations

import pytest

import vmagi.venice.racion as mod_racion
from vmagi.venice.cliente import Venice, VeniceError
from vmagi.venice.contenedor import CloudModelContainer
from vmagi.venice.puerta import Puerta, perfil_dir
from vmagi.venice.sitios import NOTRACK, SITIOS, VENICE, sitio, sitios_con


@pytest.fixture(autouse=True)
def _racion_limpia():
    mod_racion.reinicia()
    yield
    mod_racion.reinicia()


# --------------------------------------------------------------- sitios

def test_ningun_sitio_del_camino_principal_pide_credenciales():
    """La promesa central: sin cuenta y sin clave.

    No se comprueba leyendo la documentacion: se comprueba que ningun
    sitio declare una URL de login ni un campo de credenciales. Si
    alguien anade un proveedor que exige cuenta, este test lo para antes
    de que llegue al camino principal —que es donde el README promete que
    no hay login.
    """
    for s in SITIOS.values():
        texto = " ".join([s.url, s.nombre, s.nota]).lower()
        assert "login" not in s.url.lower()
        assert "api_key" not in texto and "apikey" not in texto
        assert not any(x in texto for x in ("necesita cuenta", "requiere clave"))


def test_cada_sitio_aporta_una_familia_distinta():
    """Dos autores con la misma familia no se critican: se hacen eco."""
    familias = [s.familia for s in SITIOS.values()]
    assert len(familias) == len(set(familias)), familias


def test_capacidades_declaradas_no_se_inventan():
    assert "imagen" in VENICE.capacidades()
    assert "imagen" not in NOTRACK.capacidades(), (
        "notrack.ai es un chat: declarar imagen aqui haria que el sistema "
        "lo intentase y fallase cuatro minutos despues")
    assert [s.nombre for s in sitios_con("imagen")] == ["venice"]
    assert sitios_con("video") == ()


def test_todo_sitio_del_camino_principal_lleva_su_fecha_de_medida():
    """«Nadie lo ha medido» no es «funciona».

    La fecha vive en `sitios.py` y no solo en el catálogo JSON porque el
    catálogo se cae a su respaldo de Python cuando el fichero falta —y en
    ese momento la medida desaparecía, dejando a un test decidir sobre la
    verificación de una familia según un fichero que no es el suyo.
    """
    for s in SITIOS.values():
        assert s.verificada, (
            f"{s.nombre} entra en el camino principal sin fecha de medida")
        assert s.verificado.count("-") == 2, (
            f"{s.nombre}: la fecha {s.verificado!r} no tiene forma de fecha")


def test_sitio_desconocido_dice_cuales_hay():
    with pytest.raises(ValueError) as e:
        sitio("no-existe")
    assert "venice" in str(e.value) and "notrack" in str(e.value)


def test_cada_sitio_tiene_perfil_de_edge_propio(tmp_path, monkeypatch):
    """Compartir perfil mezclaba las sesiones de los dos sitios."""
    a = perfil_dir(VENICE)
    b = perfil_dir(NOTRACK)
    assert a != b, "un perfil comun tumba la sesion de un sitio al abrir el otro"


# --------------------------------------------------------------- racion

def test_la_cache_se_consulta_y_repetir_no_gasta_cupo():
    """EL FALLO DE LA v1, fijado.

    `venice.py` llamaba a `cache_guarda(clave, ...)` con `clave` sin
    definir y no consultaba la cache jamas: cada chat correcto moria con
    NameError DESPUES de gastar la racion. La cache que el README anuncia
    no se usaba ni una vez.
    """
    r = mod_racion.racion_de("venice")
    clave = ("venice", "sistema", "dime algo")
    assert r.consulta(clave) is None

    r.guarda(clave, "respuesta")
    r.apunta_llamada()
    assert r.estado()["llamadas_hoy"] == 1

    assert r.consulta(clave) == "respuesta"
    assert r.estado()["llamadas_hoy"] == 1, (
        "servir desde cache NO puede contar como llamada: si contara, el "
        "contador dejaria de medir lo que gasta la racion")
    assert r.estado()["servidas_por_cache"] == 1


def test_la_cache_es_lru_y_tiene_techo():
    r = mod_racion.racion_de("venice")
    for i in range(mod_racion.CACHE_MAX + 10):
        r.guarda((i,), f"v{i}")
    assert r.estado()["entradas_en_cache"] == mod_racion.CACHE_MAX
    assert r.consulta((0,)) is None, "la mas vieja se cae primero"
    assert r.consulta((mod_racion.CACHE_MAX + 9,)) is not None


def test_cada_sitio_tiene_su_propia_racion():
    """Gastar el cupo de Venice no gasta el de notrack."""
    mod_racion.racion_de("venice").apunta_llamada()
    assert mod_racion.racion_de("notrack").estado()["llamadas_hoy"] == 0


def test_el_contador_vuelve_a_cero_al_cambiar_de_dia():
    r = mod_racion.racion_de("venice")
    r.apunta_llamada()
    r.dia = "1999-01-01"              # simula que el proceso lleva abierto
    assert r.estado()["llamadas_hoy"] == 0


# ----------------------------------------------------------- contenedor

class _ClienteFalso:
    sitio = VENICE

    def _error_video_cloud_only(self):
        return VeniceError(
            "Modo cloud-only activo: video gratis sin key/login no esta "
            "disponible en el proveedor guest actual. El sistema no usa "
            "modelos locales ni bypass de cuotas.")


def test_el_contenedor_declara_lo_que_hay_y_lo_que_no():
    c = CloudModelContainer(_ClienteFalso())
    inv = {p["proveedor"]: p["capacidades"] for p in c.inventario()}
    assert inv["venice-guest-free"] == ["chat", "imagen"]
    assert inv["notrack-guest-free"] == ["chat"]
    assert c.proveedor_para("video") is None, (
        "ningun guest hace video: decirlo es la unica respuesta honesta")


def test_el_contenedor_prefiere_el_sitio_del_cliente():
    c = CloudModelContainer(_ClienteFalso())
    assert c.proveedor_activo().nombre.startswith("venice")


async def test_pedir_video_en_cloud_dice_el_motivo():
    c = CloudModelContainer(_ClienteFalso())
    with pytest.raises(VeniceError) as e:
        await c.video("lo que sea")
    assert "bypass" in str(e.value).lower() or "cloud-only" in str(e.value).lower()


# -------------------------------------------------------------- cliente

async def test_imagen_en_un_sitio_sin_imagen_falla_rapido_y_con_nombre():
    """Antes se intentaba igual y el error salia 240 s despues."""
    c = Venice(sitio=NOTRACK)
    with pytest.raises(VeniceError) as e:
        await c._imagen_guest("un dragon")
    assert "notrack" in str(e.value)


def test_el_cliente_limpia_los_adornos_de_SU_sitio():
    """Las marcas de UI eran constantes de Venice en un @staticmethod:
    aplicadas a notrack no recortaban nada y su pie se colaba dentro de
    la respuesta."""
    v = Venice(sitio=VENICE)
    n = Venice(sitio=NOTRACK)
    assert v._limpia("respuesta real Get Pro Access") == "respuesta real"
    assert n._limpia("respuesta real Powered by NoTrack") == "respuesta real"
    assert n._limpia("respuesta real Get Pro Access").endswith("Get Pro Access")


def test_estado_del_cliente_no_interpreta():
    e = Venice(sitio=NOTRACK).estado()
    assert e["sitio"] == "notrack"
    assert e["familia"] == "notrack"
    assert e["sesion_activa"] is False
    assert "racion" in e and "nota" in e
