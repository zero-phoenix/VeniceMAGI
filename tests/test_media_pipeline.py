from __future__ import annotations

import json

import pytest

from vmagi import config
from vmagi.media_pipeline import (ImagePipelineService, SeedanceVideoService,
                                  VideoSeedanceError, lee_metadata,
                                  metadata_path)
from vmagi.privacy import NotrackNoDisponible, NotrackProvider


def test_notrack_obligatorio_falla_sin_proxy(monkeypatch, tmp_path):
    monkeypatch.setenv("VENICE_MAGI_DIR", str(tmp_path / "d"))
    monkeypatch.delenv("NOTRACK_PROXY", raising=False)
    monkeypatch.setenv("NOTRACK_REQUIRED", "1")
    p = NotrackProvider()
    with pytest.raises(NotrackNoDisponible):
        p.httpx_kwargs()


def test_notrack_proxy_desde_entorno(monkeypatch, tmp_path):
    monkeypatch.setenv("VENICE_MAGI_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("NOTRACK_PROXY", "http://127.0.0.1:8080")
    monkeypatch.setenv("NOTRACK_REQUIRED", "1")
    p = NotrackProvider()
    assert p.httpx_kwargs()["proxy"] == "http://127.0.0.1:8080"


def test_prompt_hq_inyecta_lora(monkeypatch, tmp_path):
    monkeypatch.setenv("VENICE_MAGI_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("LORAS_JSON", '[{"name":"portrait","weight":0.7}]')
    p = config.prompt_hq("retrato en estudio")
    assert "<lora:portrait:0.7>" in p
    assert "retrato en estudio" in p


@pytest.mark.asyncio
async def test_video_seedance_exige_api_key(monkeypatch, tmp_path):
    monkeypatch.setenv("VENICE_MAGI_DIR", str(tmp_path / "d"))
    monkeypatch.delenv("VENICE_API_KEY", raising=False)
    monkeypatch.setenv("NOTRACK_PROXY", "http://127.0.0.1:8080")
    s = SeedanceVideoService(NotrackProvider())
    with pytest.raises(VideoSeedanceError):
        await s.generar("un paisaje")


@pytest.mark.asyncio
async def test_pipeline_rechaza_backend_invalido(monkeypatch, tmp_path):
    monkeypatch.setenv("VENICE_MAGI_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("NOTRACK_PROXY", "http://127.0.0.1:8080")
    p = ImagePipelineService(NotrackProvider())
    with pytest.raises(ValueError):
        await p.generar("retrato", backend="foo")


@pytest.mark.asyncio
async def test_video_rechaza_duration_invalida(monkeypatch, tmp_path):
    monkeypatch.setenv("VENICE_MAGI_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("NOTRACK_PROXY", "http://127.0.0.1:8080")
    s = SeedanceVideoService(NotrackProvider())
    with pytest.raises(ValueError):
        await s.generar("un paisaje", duration="xx")


def test_lee_metadata_sidecar(tmp_path):
    img = tmp_path / "img_1.png"
    img.write_bytes(b"\x89PNG fake")
    sidecar = metadata_path(img)
    sidecar.write_text(json.dumps({"backend": "automatic1111"}),
                       encoding="utf-8")
    m = lee_metadata(img)
    assert m and m["backend"] == "automatic1111"
