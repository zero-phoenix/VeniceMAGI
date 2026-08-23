"""Pipeline de imagen HQ (A1111/ComfyUI) y vídeo Seedance 2.5+."""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import httpx

from . import config
from .privacy import NotrackProvider


class BackendImagenError(RuntimeError):
    """Error al generar imagen en backend local/remoto."""


class VideoSeedanceError(RuntimeError):
    """Error de generación de vídeo con Seedance."""


def metadata_path(ruta: Path) -> Path:
    return ruta.with_suffix(ruta.suffix + ".json")


def lee_metadata(ruta: Path) -> dict | None:
    m = metadata_path(ruta)
    if not m.exists():
        return None
    try:
        return json.loads(m.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _guarda_metadata(ruta: Path, payload: dict) -> Path:
    m = metadata_path(ruta)
    data = {"ts": time.time(), **payload}
    m.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return m


def _tamano_por_aspecto(aspect_ratio: str) -> tuple[int, int]:
    aspect_ratio = config.normaliza_aspect_ratio(aspect_ratio)
    mapa = {
        "1:1": (1024, 1024),
        "16:9": (1344, 768),
        "9:16": (768, 1344),
        "4:3": (1152, 896),
        "3:4": (896, 1152),
    }
    return mapa.get((aspect_ratio or "").strip(), (1024, 1024))


def _preset_calidad(quality: str | None = None) -> dict:
    preset = config.normaliza_calidad_imagen(quality or config.calidad_imagen())
    if preset == "draft":
        return {"steps": 22, "cfg": 5.0, "sampler": "DPM++ 2M Karras"}
    if preset == "ultra":
        return {"steps": 42, "cfg": 6.0, "sampler": "DPM++ SDE Karras"}
    return {"steps": 32, "cfg": 5.5, "sampler": "DPM++ 2M Karras"}


class Automatic1111Adapter:
    def __init__(self, privacy: NotrackProvider):
        self._privacy = privacy

    async def generar(self, prompt: str, *, refs: list[Path] | None = None,
                      aspect_ratio: str = "1:1", seed: int | None = None,
                      quality: str | None = None) -> Path:
        w, h = _tamano_por_aspecto(aspect_ratio)
        q = _preset_calidad(quality)
        prompt_final = config.prompt_hq(prompt)
        payload = {
            "prompt": prompt_final,
            "negative_prompt": config.negative_prompt_hq(),
            "steps": q["steps"],
            "cfg_scale": q["cfg"],
            "sampler_name": q["sampler"],
            "width": w,
            "height": h,
            "seed": seed if seed is not None else -1,
            "override_settings": {
                "sd_model_checkpoint": config.sdxl_checkpoint(),
            },
        }
        controlnet = config.controlnet_payload(refs or [])
        if controlnet:
            payload["alwayson_scripts"] = {"controlnet": {"args": controlnet}}
        face_swap = config.faceswap_payload(refs or [])
        if face_swap:
            payload.setdefault("alwayson_scripts", {})
            payload["alwayson_scripts"]["reactor"] = {"args": face_swap}

        url = config.automatic1111_url().rstrip("/") + "/sdapi/v1/txt2img"
        async with httpx.AsyncClient(timeout=180,
                                     **self._privacy.httpx_kwargs()) as c:
            r = await c.post(url, json=payload)
        if r.status_code >= 400:
            raise BackendImagenError(
                f"A1111 devolvió {r.status_code}: {r.text[:500]}",
                estado=r.status_code,
            )
        data = r.json()
        imgs = data.get("images") or []
        if not imgs:
            raise BackendImagenError("A1111 no devolvió imágenes")
        destino = config.media_dir() / f"img_{int(time.time())}.png"
        destino.write_bytes(base64.b64decode(imgs[0]))
        _guarda_metadata(destino, {
            "kind": "image",
            "backend": "automatic1111",
            "model": config.sdxl_checkpoint(),
            "prompt": prompt_final,
            "negative_prompt": config.negative_prompt_hq(),
            "aspect_ratio": aspect_ratio,
            "seed": seed,
            "settings": q,
            "quality": (quality or config.calidad_imagen()).lower(),
            "has_controlnet": bool(controlnet),
            "has_faceswap": bool(face_swap),
        })
        return destino


class ComfyUIAdapter:
    def __init__(self, privacy: NotrackProvider):
        self._privacy = privacy

    async def generar(self, prompt: str, *, refs: list[Path] | None = None,
                      aspect_ratio: str = "1:1", seed: int | None = None,
                      quality: str | None = None) -> Path:
        base = config.comfyui_url().rstrip("/")
        plantilla = config.comfyui_workflow()
        if not plantilla.exists():
            raise BackendImagenError(
                "Falta workflow de ComfyUI. Define COMFYUI_WORKFLOW con "
                "un JSON válido."
            )
        flujo = json.loads(plantilla.read_text(encoding="utf-8"))
        flujo = config.injectar_prompt_comfyui(
            flujo=flujo,
            prompt=config.prompt_hq(prompt),
            aspect_ratio=aspect_ratio,
            seed=seed,
            quality=quality,
        )
        async with httpx.AsyncClient(timeout=300,
                                     **self._privacy.httpx_kwargs()) as c:
            rq = await c.post(base + "/prompt", json={"prompt": flujo})
            if rq.status_code >= 400:
                raise BackendImagenError(
                    f"ComfyUI /prompt {rq.status_code}: {rq.text[:500]}",
                    estado=rq.status_code,
                )
            pid = rq.json().get("prompt_id")
            if not pid:
                raise BackendImagenError("ComfyUI no devolvió prompt_id")
            for _ in range(90):
                await c.get(base + "/queue")
                rh = await c.get(base + f"/history/{pid}")
                if rh.status_code < 400 and rh.text and rh.text != "{}":
                    hist = rh.json().get(pid, {})
                    out = hist.get("outputs", {})
                    for nodo in out.values():
                        imgs = nodo.get("images", [])
                        if imgs:
                            img = imgs[0]
                            rv = await c.get(base + "/view", params={
                                "filename": img.get("filename"),
                                "subfolder": img.get("subfolder", ""),
                                "type": img.get("type", "output"),
                            })
                            rv.raise_for_status()
                            destino = config.media_dir() / f"img_{int(time.time())}.png"
                            destino.write_bytes(rv.content)
                            _guarda_metadata(destino, {
                                "kind": "image",
                                "backend": "comfyui",
                                "workflow": str(plantilla),
                                "prompt": config.prompt_hq(prompt),
                                "aspect_ratio": aspect_ratio,
                                "seed": seed,
                                "quality": (quality or config.calidad_imagen()).lower(),
                            })
                            return destino
                await c.get(base + "/system_stats")
                await __import__("asyncio").sleep(2.0)
        raise BackendImagenError("ComfyUI no produjo imagen en el plazo")


class ImagePipelineService:
    """Selector de backend de imagen y enforcement de pipeline HQ."""

    def __init__(self, privacy: NotrackProvider):
        self._privacy = privacy
        self._a1111 = Automatic1111Adapter(privacy)
        self._comfy = ComfyUIAdapter(privacy)

    async def generar(self, prompt: str, *, refs: list[Path] | None = None,
                      aspect_ratio: str = "1:1", seed: int | None = None,
                      quality: str | None = None,
                      backend: str | None = None) -> Path:
        backend = config.normaliza_backend_imagen(backend or config.backend_imagen())
        if backend == "automatic1111":
            return await self._a1111.generar(prompt, refs=refs,
                                             aspect_ratio=aspect_ratio, seed=seed,
                                             quality=quality)
        if backend == "comfyui":
            return await self._comfy.generar(prompt, refs=refs,
                                             aspect_ratio=aspect_ratio, seed=seed,
                                             quality=quality)
        raise BackendImagenError(
            f"backend de imagen no soportado: {backend}. Usa automatic1111 o comfyui."
        )


class SeedanceVideoService:
    """Vídeo exclusivamente con Seedance 2.5+."""

    def __init__(self, privacy: NotrackProvider):
        self._privacy = privacy

    async def generar(self, prompt: str, *, duration: str = "10s",
                      ref_urls: list[str] | None = None) -> Path:
        duration = config.normaliza_duration(duration)
        api_key = config.venice_api_key()
        if not api_key:
            raise VideoSeedanceError(
                "Para vídeo con Seedance 2.5+ necesitas VENICE_API_KEY."
            )
        model = config.modelo_video_seedance()
        if "seedance-2.5" not in model and "seedance-3" not in model:
            raise VideoSeedanceError(
                f"Modelo de vídeo no permitido: {model}. Debe ser Seedance 2.5+."
            )
        payload = {
            "model": model,
            "prompt": prompt,
            "duration": duration,
            "ref_urls": ref_urls or [],
            "consents": config.CONSENTS_SEEDANCE.get("seedance", {}),
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=240,
                                     **self._privacy.httpx_kwargs()) as c:
            r = await c.post(config.BASE_URL.rstrip("/") + "/video/generations",
                             json=payload, headers=headers)
        if r.status_code >= 400:
            raise VideoSeedanceError(
                f"Seedance error {r.status_code}: {r.text[:500]}",
                estado=r.status_code,
            )
        data = r.json()
        src = data.get("url") or data.get("video_url")
        if not src:
            raise VideoSeedanceError(
                "Seedance no devolvió URL de vídeo utilizable."
            )
        async with httpx.AsyncClient(timeout=240,
                                     **self._privacy.httpx_kwargs()) as c:
            rv = await c.get(src, follow_redirects=True)
        rv.raise_for_status()
        destino = config.media_dir() / f"video_{int(time.time())}.mp4"
        destino.write_bytes(rv.content)
        _guarda_metadata(destino, {
            "kind": "video",
            "backend": "seedance",
            "model": model,
            "prompt": prompt,
            "duration": duration,
            "ref_urls": ref_urls or [],
        })
        return destino
