"""Anonimato absoluto: una sola salida de red, para todo el sistema.

QUE FIJAN ESTOS TESTS
=====================
El principio del sistema es anonimato absoluto en todo sentido, y eso se
rompe de una forma muy concreta y muy facil: el **trafico partido**. Media
aplicacion sale por la VPN y la otra media por la linea de casa, las dos
rutas se correlacionan, y la VPN deja de servir para lo unico que sirve.

VeniceMAGI tenia tres puertas distintas —`/proxy` para la ventana de Edge,
`NOTRACK_PROXY` para el HTTP, `/vpn` para Ritsuko— y ninguna sabia de las
otras. Estos tests fijan que ahora sea una sola, que la gobierne Ritsuko, y
que el modo estricto signifique lo que dice.
"""
from __future__ import annotations

import pytest

from vmagi.modules.infrastructure.ritsuko import (
    FAMILIAS_AUDITADAS,
    FAMILIAS_RITSUKO,
)
from vmagi.modules.infrastructure.ritsuko_red import (
    SALIDAS_CONOCIDAS,
    SalidaDeRed,
    SalidaNoDisponible,
    aplica_a_httpx,
    aplica_a_navegador,
    salida_de_ritsuko,
    variables_de_entorno,
)


@pytest.fixture(autouse=True)
def _sin_entorno_heredado(monkeypatch):
    for v in ("RITSUKO_VPN", "RITSUKO_VPN_ESTRICTA", "NOTRACK_PROXY"):
        monkeypatch.delenv(v, raising=False)
    yield


# ------------------------------------------- una sola salida, para todo

def test_la_misma_salida_llega_a_las_tres_capas(monkeypatch):
    """HTTP, navegador y subprocesos van por la MISMA puerta.

    Tres funciones distintas porque cada capa quiere el mismo dato en un
    formato distinto; un solo origen porque dos origenes es trafico
    partido. Este test es el que impide que una de las tres se quede
    atras en un refactor, que es como se llega al trafico partido sin
    que nadie lo decida.
    """
    monkeypatch.setenv("RITSUKO_VPN", "socks5://127.0.0.1:9050")
    salida_de_ritsuko(recargar=True)

    assert aplica_a_httpx() == {"proxy": "socks5://127.0.0.1:9050"}
    assert aplica_a_navegador() == {"proxy": {"server": "socks5://127.0.0.1:9050"}}
    env = variables_de_entorno()
    assert env["HTTPS_PROXY"] == "socks5://127.0.0.1:9050"
    assert env["ALL_PROXY"] == "socks5://127.0.0.1:9050"
    # minusculas tambien: curl, git y buena parte de Unix solo miran esas
    assert env["https_proxy"] == "socks5://127.0.0.1:9050"


def test_sin_salida_los_subprocesos_no_reciben_variables_vacias(monkeypatch):
    """`HTTPS_PROXY=""` no es «sin proxy»: rompe algunas herramientas."""
    salida_de_ritsuko(recargar=True)
    assert variables_de_entorno() == {}


def test_la_puerta_de_edge_hereda_la_salida_del_sistema(monkeypatch):
    """La ventana del Guest no puede tener ruta propia si hay una global."""
    from vmagi.venice.puerta import Puerta

    monkeypatch.setenv("RITSUKO_VPN", "http://127.0.0.1:8080")
    salida_de_ritsuko(recargar=True)
    kwargs = Puerta._kwargs_lanzamiento()
    assert kwargs["proxy"] == {"server": "http://127.0.0.1:8080"}


def test_el_http_del_sistema_hereda_la_salida(monkeypatch):
    from vmagi.venice.privacidad import NotrackProvider

    monkeypatch.setenv("RITSUKO_VPN", "socks5://127.0.0.1:9050")
    salida_de_ritsuko(recargar=True)
    assert NotrackProvider(obligatorio=False).httpx_kwargs() == {
        "proxy": "socks5://127.0.0.1:9050"}


# ----------------------------------------------------- modo estricto

def test_estricto_sin_salida_no_sale_por_la_linea_directa():
    """«Uso VPN» y «uso VPN salvo cuando falle» no son lo mismo.

    Para el anonimato, la segunda no sirve de nada: basta una peticion
    por la linea directa para deshacer el trabajo de todas las demas.
    """
    s = SalidaDeRed(estricta=True)
    with pytest.raises(SalidaNoDisponible) as e:
        s.httpx_kwargs()
    assert "estricto" in str(e.value)
    assert "/vpn" in str(e.value), "el error tiene que decir como arreglarlo"


def test_estricto_tampoco_abre_la_ventana_del_guest(monkeypatch):
    """Abrir el Edge sin VPN delataria la IP que la VPN oculta al resto."""
    monkeypatch.setenv("RITSUKO_VPN_ESTRICTA", "1")
    salida_de_ritsuko(recargar=True)
    with pytest.raises(SalidaNoDisponible):
        aplica_a_navegador()


def test_sin_estricto_no_tener_salida_es_valido():
    """El modo por defecto no obliga a nadie a montar una VPN."""
    assert SalidaDeRed().httpx_kwargs() == {}


# ------------------------------------------------------ configuracion

def test_el_entorno_manda_sobre_la_config(monkeypatch):
    monkeypatch.setenv("RITSUKO_VPN", "socks5://127.0.0.1:9050")
    s = salida_de_ritsuko(recargar=True)
    assert s.url == "socks5://127.0.0.1:9050"
    assert "RITSUKO_VPN" in s.origen


def test_notrack_proxy_sigue_valiendo_como_fuente(monkeypatch):
    """Una configuracion que ya funcionaba tiene que seguir funcionando."""
    monkeypatch.setenv("NOTRACK_PROXY", "http://127.0.0.1:8080")
    s = salida_de_ritsuko(recargar=True)
    assert s.url == "http://127.0.0.1:8080"


@pytest.mark.parametrize("mala", [
    "127.0.0.1:9050",            # sin esquema
    "ftp://host:21",             # esquema no admitido
    "socks5:/malformada",
])
def test_una_salida_mal_escrita_se_rechaza_al_fijarla(mala):
    """Un proxy roto que solo falla en la primera llamada real es un fallo
    que aparece justo cuando no puedes depurarlo."""
    with pytest.raises(ValueError) as e:
        SalidaDeRed().fija(mala)
    assert "socks5://127.0.0.1:9050" in str(e.value), (
        "el error tiene que traer un ejemplo que funcione")


def test_el_error_ofrece_salidas_gratuitas_de_verdad():
    """Decir «configura una VPN» sin decir cual no ayuda a nadie."""
    with pytest.raises(ValueError) as e:
        SalidaDeRed().fija("no-vale")
    texto = str(e.value)
    assert "Tor" in texto
    assert any(u in texto for _n, u, _q in SALIDAS_CONOCIDAS if u != "(ninguna)")


def test_las_credenciales_no_salen_en_el_informe():
    """El informe existe para que el usuario lo descargue y lo comparta."""
    s = SalidaDeRed()
    s.fija("http://usuario:secreto@proxy.local:8080")
    assert "secreto" not in s.estado()["salida"]
    assert "***" in s.estado()["salida"]


def test_el_alcance_se_declara_en_el_estado():
    """`/salud` lo enseña: la salida es del sistema, no de un modulo."""
    alcance = SalidaDeRed().estado()["alcance"]
    assert "todo el sistema" in alcance


# ------------------------------------------------ auditoria de anonimato

def test_ritsuko_senala_las_fugas_por_su_nombre(monkeypatch):
    """Un informe de privacidad que solo sabe decir «ok» no lo ha mirado."""
    from vmagi.core.bus import MagiBus
    from vmagi.modules.infrastructure.ritsuko import RitsukoAgent

    salida_de_ritsuko(recargar=True)
    r = RitsukoAgent(MagiBus())
    a = r.anonimato()
    assert a["limpio"] is False
    assert any("IP real" in f for f in a["fugas"])


def test_con_vpn_estricta_no_queda_fuga(monkeypatch):
    from vmagi.core.bus import MagiBus
    from vmagi.modules.infrastructure.ritsuko import RitsukoAgent

    monkeypatch.setenv("RITSUKO_VPN", "socks5://127.0.0.1:9050")
    monkeypatch.setenv("RITSUKO_VPN_ESTRICTA", "1")
    salida_de_ritsuko(recargar=True)
    r = RitsukoAgent(MagiBus())
    r.red = salida_de_ritsuko(recargar=True)
    a = r.anonimato()
    assert a["fugas"] == [], a["fugas"]
    assert a["limpio"] is True


def test_ritsuko_solo_mira_no_toca():
    """Las funciones nuevas son de LECTURA. Un auditor con permiso para
    arreglar acaba revisandose a si mismo."""
    from vmagi.modules.infrastructure.ritsuko import RitsukoAgent

    for nombre in ("anonimato", "inventario_proveedores", "racion_del_dia"):
        assert hasattr(RitsukoAgent, nombre)
    for prohibido in ("escribir_fichero", "aplicar_parche", "cancelar_tarea",
                      "reasignar_reparto"):
        assert not hasattr(RitsukoAgent, prohibido)


# ------------------------------------------------------ independencia

def test_ritsuko_sigue_sin_compartir_familia_con_lo_que_audita():
    """venice y notrack son el camino principal: no pueden auditarse solas."""
    assert "venice" in FAMILIAS_AUDITADAS
    assert "notrack" in FAMILIAS_AUDITADAS
    assert set(FAMILIAS_RITSUKO).isdisjoint(set(FAMILIAS_AUDITADAS))
