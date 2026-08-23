from __future__ import annotations

from vmagi import health


def test_health_ok_basico(monkeypatch, tmp_path):
    monkeypatch.setenv("VENICE_MAGI_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("NOTRACK_PROXY", "http://127.0.0.1:8080")
    monkeypatch.setenv("NOTRACK_REQUIRED", "1")
    monkeypatch.setenv("CLOUD_ONLY_MODE", "1")
    s = health.estado_salud()
    assert s["notrack_configurado"]
    assert s["backend_imagen_ok"]
    assert s["cloud_only_mode"] is True


def test_health_detecta_backend_invalido(monkeypatch, tmp_path):
    monkeypatch.setenv("VENICE_MAGI_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("CLOUD_ONLY_MODE", "0")
    monkeypatch.setenv("IMAGE_BACKEND", "otro")
    s = health.estado_salud()
    assert not s["backend_imagen_ok"]
