from __future__ import annotations

import pytest

from vmagi import config


def test_guardar_backend_imagen(monkeypatch, tmp_path):
    monkeypatch.setenv("VENICE_MAGI_DIR", str(tmp_path / "d"))
    config.guardar_backend_imagen("comfyui")
    assert config.backend_imagen() == "comfyui"


def test_guardar_calidad_imagen(monkeypatch, tmp_path):
    monkeypatch.setenv("VENICE_MAGI_DIR", str(tmp_path / "d"))
    config.guardar_calidad_imagen("standard")
    assert config.calidad_imagen() == "standard"


def test_guardar_backend_invalido(monkeypatch, tmp_path):
    monkeypatch.setenv("VENICE_MAGI_DIR", str(tmp_path / "d"))
    with pytest.raises(ValueError):
        config.guardar_backend_imagen("foo")


def test_guardar_notrack_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("VENICE_MAGI_DIR", str(tmp_path / "d"))
    monkeypatch.delenv("NOTRACK_PROXY", raising=False)
    monkeypatch.delenv("NOTRACK_REQUIRED", raising=False)
    config.guardar_notrack_proxy("http://127.0.0.1:8080")
    assert config.notrack_proxy() == "http://127.0.0.1:8080"
    config.guardar_notrack_obligatorio(False)
    assert config.notrack_obligatorio() is False


def test_normaliza_aspect_duration():
    assert config.normaliza_aspect_ratio("16:9") == "16:9"
    assert config.normaliza_duration("10s") == "10s"
    with pytest.raises(ValueError):
        config.normaliza_aspect_ratio("2:1")
    with pytest.raises(ValueError):
        config.normaliza_duration("abc")


def test_cloud_only_default_y_modo_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("VENICE_MAGI_DIR", str(tmp_path / "d"))
    monkeypatch.delenv("CLOUD_ONLY_MODE", raising=False)
    assert config.cloud_only_mode() is True
    config.guardar_system_mode("hybrid")
    assert config.system_mode() == "hybrid"
