from __future__ import annotations

from vmagi.venice import Venice


def test_provider_label_sin_abrir_sesion():
    v = Venice()
    assert v.sesion_activa() is False
    assert "inactivo" in v.etiqueta_provider_chat()
