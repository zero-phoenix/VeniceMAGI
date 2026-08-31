"""La salida de red de Ritsuko: independiente, pero no evasiva.

LA LINEA QUE ESTOS TESTS DEFIENDEN
==================================
El manifiesto de VeniceMAGI dice «sin evasion de cuotas (no rotacion
automatica de IP/VPN)». Una auditora con salida de red propia es
compatible con eso —comparte ración con el auditado si sale por su misma
IP, y se queda muda el dia que hace falta—; rotarla cuando el proveedor
dice «hoy no» NO lo es.

La diferencia no puede quedarse en una nota del README. Aqui esta el
codigo que la hace cumplir, y estos tests son lo que impide que alguien
la relaje «solo para este caso».
"""
from __future__ import annotations

import pytest

from vmagi.modules.infrastructure.ritsuko import FAMILIAS_AUDITADAS, FAMILIAS_RITSUKO
from vmagi.modules.infrastructure.ritsuko_red import (
    MOTIVOS_PROHIBIDOS,
    RotacionProhibida,
    SalidaDeRed,
    salida_de_ritsuko,
)


# ----------------------------------------------------- no se evade nada

@pytest.mark.parametrize("motivo", [
    "cuota agotada",
    "cupo diario del guest",
    "rate limit del proveedor",
    "HTTP 429 Too Many Requests",
    "la IP quedo bloqueada",
    "captcha",
    "403 por atestacion",
    "limite alcanzado",
])
def test_no_se_rota_la_salida_por_ningun_motivo_de_cuota(motivo):
    """La regla, aplicada a los motivos reales que aparecen en el log."""
    s = SalidaDeRed()
    with pytest.raises(RotacionProhibida) as e:
        s.rota_por(motivo, "socks5://127.0.0.1:9050")
    assert "no rota" in str(e.value).lower() or "esquiv" in str(e.value).lower()
    assert s.url == "", "la salida no puede haber cambiado"


def test_el_intento_rechazado_queda_apuntado():
    """Una medida antievasion que nadie puede leer es una intencion."""
    s = SalidaDeRed()
    with pytest.raises(RotacionProhibida):
        s.rota_por("cuota agotada", "http://127.0.0.1:8080")
    assert s.estado()["rotaciones_rechazadas"] == 1
    apunte = s.bitacora[-1]
    assert apunte["permitida"] is False and apunte["regla"] in MOTIVOS_PROHIBIDOS


def test_no_hay_parametro_para_saltarse_la_prohibicion():
    """Si `rota_por` aceptara un `forzar=True`, la regla seria un consejo."""
    import inspect
    firma = inspect.signature(SalidaDeRed.rota_por)
    assert set(firma.parameters) == {"self", "motivo", "url"}


def test_un_motivo_legitimo_si_puede_cambiar_la_salida():
    """No es una prohibicion de cambiar: es una prohibicion de evadir."""
    s = SalidaDeRed()
    s.rota_por("el usuario cambio de VPN", "socks5://127.0.0.1:9050")
    assert s.url == "socks5://127.0.0.1:9050"


# ------------------------------------------------------ configuracion

def test_la_salida_se_fija_a_mano_y_arranca_vacia(monkeypatch):
    monkeypatch.delenv("RITSUKO_VPN", raising=False)
    monkeypatch.delenv("NOTRACK_PROXY", raising=False)
    s = salida_de_ritsuko(recargar=True)
    assert s.configurada is False
    assert s.httpx_kwargs() == {}, (
        "sin salida propia, Ritsuko sale por donde salga el sistema: es el "
        "modo por defecto, no un error")


def test_el_entorno_manda_sobre_la_config(monkeypatch):
    monkeypatch.setenv("RITSUKO_VPN", "socks5://127.0.0.1:9050")
    s = salida_de_ritsuko(recargar=True)
    assert s.url == "socks5://127.0.0.1:9050"
    assert "RITSUKO_VPN" in s.origen
    assert s.httpx_kwargs() == {"proxy": "socks5://127.0.0.1:9050"}


def test_heredar_el_proxy_de_notrack_se_declara_como_no_independiente(monkeypatch):
    """Tener algo es mejor que nada; venderlo como independencia, no."""
    monkeypatch.delenv("RITSUKO_VPN", raising=False)
    monkeypatch.setenv("NOTRACK_PROXY", "http://127.0.0.1:8080")
    s = salida_de_ritsuko(recargar=True)
    assert s.configurada
    assert "NO independiente" in s.origen


@pytest.mark.parametrize("mala", [
    "127.0.0.1:9050",            # sin esquema
    "ftp://host:21",             # esquema no admitido
    "socks5:/malformada",
])
def test_una_salida_mal_escrita_se_rechaza_al_fijarla(mala):
    """Un proxy roto que solo falla en la primera auditoria es un fallo
    que aparece justo cuando no puedes depurarlo."""
    with pytest.raises(ValueError) as e:
        SalidaDeRed().fija(mala)
    assert "socks5://127.0.0.1:9050" in str(e.value), (
        "el error tiene que traer un ejemplo que funcione")


def test_las_credenciales_no_salen_en_el_informe():
    """El informe existe para que el usuario lo descargue y lo comparta."""
    s = SalidaDeRed()
    s.fija("http://usuario:secreto@proxy.local:8080")
    assert "secreto" not in s.estado()["salida"]
    assert "***" in s.estado()["salida"]


# ------------------------------------------------------ independencia

def test_ritsuko_sigue_sin_compartir_familia_tras_entrar_venice_y_notrack():
    """Las dos familias nuevas son auditadas: no pueden auditar.

    Este es el test que impide que alguien «arregle» a Ritsuko poniendole
    la familia que mejor va hoy — que en VeniceMAGI seria venice, la del
    camino principal, y por tanto la peor eleccion posible.
    """
    assert "venice" in FAMILIAS_AUDITADAS
    assert "notrack" in FAMILIAS_AUDITADAS
    assert set(FAMILIAS_RITSUKO).isdisjoint(set(FAMILIAS_AUDITADAS))


def test_la_politica_se_declara_en_el_estado():
    """`/salud` y el informe lo enseñan: la regla es visible, no tacita."""
    politica = SalidaDeRed().estado()["politica"]
    assert "no rota" in politica and "cuota" in politica
