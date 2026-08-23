from __future__ import annotations

from vmagi import health


def test_health_ok_basico(monkeypatch, tmp_path):
    monkeypatch.setenv("VENICE_MAGI_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("NOTRACK_PROXY", "http://127.0.0.1:8080")
    monkeypatch.setenv("NOTRACK_REQUIRED", "1")
    monkeypatch.setenv("IMAGE_BACKEND", "automatic1111")
    monkeypatch.setenv("SEEDANCE_MODEL", "seedance-2.5-text-to-video")
    s = health.estado_salud()
    assert s["notrack_configurado"]
    assert s["backend_imagen_ok"]
    assert s["seedance_ok"]


def test_health_detecta_backend_invalido(monkeypatch, tmp_path):
    monkeypatch.setenv("VENICE_MAGI_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("IMAGE_BACKEND", "otro")
    s = health.estado_salud()
    assert not s["backend_imagen_ok"]
