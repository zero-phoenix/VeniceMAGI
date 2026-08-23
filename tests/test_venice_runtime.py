from __future__ import annotations

from vmagi.venice import Venice
import pytest


def test_provider_label_sin_abrir_sesion():
    v = Venice()
    assert v.sesion_activa() is False
    assert "inactivo" in v.etiqueta_provider_chat()


def test_container_cloud_label(monkeypatch):
    monkeypatch.setenv("CLOUD_ONLY_MODE", "1")
    v = Venice()
    assert "cloud-virtual" in v.etiqueta_container()


@pytest.mark.asyncio
async def test_video_cloud_only_error(monkeypatch):
    monkeypatch.setenv("CLOUD_ONLY_MODE", "1")
    v = Venice()
    with pytest.raises(Exception) as e:
        await v.video("prueba")
    assert "cloud-only" in str(e.value)
