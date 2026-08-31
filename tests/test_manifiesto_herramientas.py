"""El README promete herramientas por su nombre. Este test las cobra.

Un README que promete `patch_file` mientras el registro solo conoce
`edit_file` no tiene un problema de documentacion: tiene una promesa
incumplida. Quien lea el documento escribira `patch_file`, recibira
«herramienta desconocida» y concluira, con razon, que el documento miente.
"""
from __future__ import annotations

import pytest

from vmagi.core.tools.builtin import build_registry
from vmagi.core.tools.manifiesto import ALIAS, hardware_info

#: Exactamente los nombres que el README de VeniceMAGI enumera en
#: «IDE real». Si el README cambia, este tuple cambia con el.
PROMETIDAS = ("read_file", "list_dir", "patch_file", "delete_file",
              "hardware_info", "run_python", "shell")


@pytest.fixture(scope="module")
def reg():
    return build_registry()


@pytest.mark.parametrize("nombre", PROMETIDAS)
def test_la_herramienta_prometida_existe(reg, nombre):
    assert reg.get(nombre) is not None, (
        f"el README promete `{nombre}` y el registro no lo conoce")


@pytest.mark.parametrize("alias,original", sorted(ALIAS.items()))
def test_el_alias_es_la_misma_implementacion_no_una_copia(reg, alias, original):
    """Si `edit_file` mejora, `patch_file` mejora con el."""
    a, o = reg.get(alias), reg.get(original)
    assert a is not None and o is not None
    assert a.handler is o.handler


@pytest.mark.parametrize("alias,original", sorted(ALIAS.items()))
def test_el_alias_no_relaja_los_permisos(reg, alias, original):
    """Llamar `shell` en vez de `run_command` no salta la aprobacion.

    Este es el test que importa de verdad: un alias es una comodidad, y
    una comodidad que abre un agujero de permisos deja de serlo.
    """
    a, o = reg.get(alias), reg.get(original)
    assert a.access == o.access
    assert a.dangerous == o.dangerous


def test_shell_sigue_siendo_peligroso(reg):
    """«shell solo con tu aprobacion clic a clic», dice el README."""
    assert reg.get("shell").dangerous is True


def test_delete_file_es_reversible(reg):
    """«delete_file a papelera con journal»: si no es reversible, miente."""
    d = reg.get("delete_file")
    assert d.dangerous is True
    assert "revers" in d.description.lower()


def test_hardware_info_no_inventa_lo_que_no_puede_medir():
    """«No he podido comprobarlo» no es «esta bien», tampoco con el hardware.

    Un dato vago sobre la maquina es peor que ninguno: el enjambre lo usa
    para decidir si un trabajo cabe.
    """
    d = hardware_info()
    assert set(d) >= {"cpu", "ram_total_gb", "gpu", "discos", "no_verificado"}
    assert isinstance(d["no_verificado"], list)
    if d["ram_total_gb"] is None:
        assert any("RAM" in x for x in d["no_verificado"])
    if not d["gpu"]:
        assert any("GPU" in x for x in d["no_verificado"])
    assert d["cpu"]["nucleos_logicos"] is None or d["cpu"]["nucleos_logicos"] > 0


def test_hardware_info_sale_por_la_herramienta_con_su_evidencia(reg):
    r = reg.get("hardware_info").handler()
    assert r.ok
    assert "CPU:" in r.content
    assert "no_verificado" in r.meta
