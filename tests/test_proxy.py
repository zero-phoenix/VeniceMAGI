"""El proxy del usuario: su red, su privacidad — y nada de evasión.

El soporte de proxy enruta la ventana del Guest por la VPN/proxy que EL
USUARIO posee y configura. No hay rotación automática, ni reconexión al
agotarse el cupo, ni VPN integrada: eso sería saltarse la ración del
servicio gratuito, y este test también fija que no exista.
"""
from __future__ import annotations

from vmagi import config, sesion


def test_el_proxy_se_guarda_y_se_borra(monkeypatch, tmp_path):
    monkeypatch.setenv("VENICE_MAGI_DIR", str(tmp_path / "d"))
    assert config.proxy() is None
    config.guardar_proxy("socks5://127.0.0.1:9050")
    assert config.proxy() == "socks5://127.0.0.1:9050"
    config.guardar_proxy(None)
    assert config.proxy() is None


def test_el_entorno_manda_sobre_el_fichero(monkeypatch, tmp_path):
    monkeypatch.setenv("VENICE_MAGI_DIR", str(tmp_path / "d"))
    config.guardar_proxy("http://del-fichero:8080")
    monkeypatch.setenv("VENICE_PROXY", "socks5://del-entorno:1080")
    assert config.proxy() == "socks5://del-entorno:1080"


def test_el_lanzamiento_lleva_el_proxy_solo_si_existe(monkeypatch, tmp_path):
    monkeypatch.setenv("VENICE_MAGI_DIR", str(tmp_path / "d"))
    sin = sesion.Puerta._kwargs_lanzamiento()
    assert "proxy" not in sin
    config.guardar_proxy("socks5://mi-vpn:1080")
    con = sesion.Puerta._kwargs_lanzamiento()
    assert con["proxy"] == {"server": "socks5://mi-vpn:1080"}
    # y lo demás del lanzamiento no se tocó
    assert con["channel"] == "msedge" and con["headless"] is False


def test_no_hay_evasion_de_cupo_en_el_codigo():
    """El sistema NO reconecta ni rota nada al agotarse la ración.

    La promesa documentada es respetar el cupo y explicarlo. Si alguien
    añade 'vpn', 'reconnect on quota' o similar a este paquete, este test
    se pone en rojo para que la decisión pase por aquí, a la vista.
    """
    import inspect
    fuente = inspect.getsource(sesion)
    for palabra in ("vpn", "rotate_ip", "rotar_ip"):
        assert palabra.lower() not in fuente.lower(), (
            f"«{palabra}» apareció en sesion.py: la evasión de cuota no es "
            "una funcionalidad de este sistema")
