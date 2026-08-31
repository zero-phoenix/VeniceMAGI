"""Configuración de VeniceMAGI: clave, modelos y directorios."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

NOMBRE = "VeniceMAGI"
VERSION = "2.0.0"

BASE_URL = "https://api.venice.ai/api/v1"

#: Modelos por defecto. Los tres roles son el MISMO modelo — la dialéctica
#: está en los contratos, no en la diversidad. Cambiar el modelo aquí cambia
#: a los cuatro (enjambre + Naoko) a la vez: monocultivo deliberado.
MODELO_TEXTO = "zai-org-glm-5"          # default de la documentación
MODELO_IMAGEN = "flux-dev"              # el de la web, sin cuenta
MODELO_VIDEO = "seedance-2.5-text-to-video"

#: Consensos que exige /video/queue para modelos seedance. Sin los tres
#: `true` responde 409 needs_consent y el vídeo no entra en cola.
CONSENTS_SEEDANCE = {
    "seedance": {
        "acceptProhibitedContentPolicy": True,
        "acceptThirdPartyLicensingPolicy": True,
        "acceptDeathOrHarmPolicy": True,
    }
}

ASPECTOS_VALIDOS = ("1:1", "16:9", "9:16", "4:3", "3:4")
BACKENDS_IMAGEN = ("automatic1111", "comfyui")
CALIDADES_IMAGEN = ("draft", "standard", "ultra")
MODOS_SISTEMA = ("cloud", "hybrid")


def data_dir() -> Path:
    """Directorio de datos del usuario. Nunca el CWD del exe.

    UNA SOLA FUENTE DE VERDAD. Este modulo resolvia la ruta por su cuenta
    y `vmagi/core/paths.py` la resolvia por la suya. Coincidian por
    casualidad en Windows y divergian en todo lo demas: en Linux el
    nucleo escribia en `~/.local/share` y el REPL en `~/VeniceMAGI`, asi
    que el historial que grababa uno no lo leia el otro. Ahora manda
    `core.paths` y aqui solo queda el override propio del REPL.
    """
    override = os.environ.get("VENICE_MAGI_DIR")
    if override:
        d = Path(override).expanduser().resolve()
        d.mkdir(parents=True, exist_ok=True)
        return d
    from vmagi.core.paths import data_dir as _nucleo
    return _nucleo()


def proxy() -> str | None:
    """Proxy/VPN del usuario para la ventana del Guest (opcional).

    Formato: scheme://host:port (socks5://..., http://...). Va SOLO a la
    ventana de la puerta: el resto del tráfico del sistema no se toca.
    Del entorno VENICE_PROXY o del config.json local.
    """
    p_ = os.environ.get("VENICE_PROXY", "").strip()
    if p_:
        return p_
    f = _ruta_config()
    if f.exists():
        try:
            return (json.loads(f.read_text(encoding="utf-8"))
                    .get("proxy") or None)
        except (OSError, json.JSONDecodeError):
            return None
    return None


def guardar_proxy(valor: str | None) -> None:
    """Fija (o borra con None/'') el proxy en config.json."""
    datos = _lee_config()
    valor = (valor or "").strip()
    if valor:
        datos["proxy"] = valor
    else:
        datos.pop("proxy", None)
    _escribe_config(datos)


def _ruta_config() -> Path:
    return data_dir() / "config.json"


def _lee_config() -> dict:
    f = _ruta_config()
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _escribe_config(datos: dict) -> None:
    _ruta_config().write_text(
        json.dumps(datos, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )


#: alias por si alguien llegó a usar los nombres de la v2 a secas
_leer_config = _lee_config
_escribir_config = _escribe_config


def puerta_visible() -> bool:
    """Modo de la puerta de Edge. Aparcada (off-screen) por defecto."""
    import os
    if os.environ.get("VENICE_PUERTA_VISIBLE", "").strip() in ("1", "true"):
        return True
    return bool(_lee_config().get("puerta_visible", False))


def fijar_puerta_visible(valor: bool) -> None:
    d = _lee_config()
    d["puerta_visible"] = bool(valor)
    _escribe_config(d)


def permitir_shell() -> bool:
    import os
    if os.environ.get("VENICE_PERMITIR_SHELL", "").strip() in ("1", "true"):
        return True
    return bool(_lee_config().get("permitir_shell", False))


def fijar_permitir_shell(valor: bool) -> None:
    d = _lee_config()
    d["permitir_shell"] = bool(valor)
    _escribe_config(d)


def papelera_dir() -> Path:
    p = data_dir() / "papelera"
    p.mkdir(parents=True, exist_ok=True)
    return p


def journal_path() -> Path:
    return data_dir() / "journal.jsonl"


def workspace() -> Path:
    w = data_dir() / "workspace"
    w.mkdir(parents=True, exist_ok=True)
    return w


def media_dir() -> Path:
    m = data_dir() / "media"
    m.mkdir(parents=True, exist_ok=True)
    return m


def notrack_proxy() -> str | None:
    """Proxy notrack.ai obligatorio para tráfico HTTP compatible."""
    p_ = os.environ.get("NOTRACK_PROXY", "").strip()
    if p_:
        return p_
    return (_lee_config().get("notrack_proxy") or "").strip() or None


def guardar_notrack_proxy(valor: str | None) -> str | None:
    d = _lee_config()
    v = (valor or "").strip()
    if v:
        d["notrack_proxy"] = v
    else:
        d.pop("notrack_proxy", None)
    _escribe_config(d)
    return v or None


def notrack_obligatorio() -> bool:
    v = (os.environ.get("NOTRACK_REQUIRED", "").strip()
         or str(_lee_config().get("notrack_required", "1")))
    v = v.lower()
    return v not in ("0", "false", "no", "off")


def guardar_notrack_obligatorio(valor: bool) -> bool:
    d = _lee_config()
    d["notrack_required"] = bool(valor)
    _escribe_config(d)
    return bool(valor)


def cloud_only_mode() -> bool:
    m = (os.environ.get("CLOUD_ONLY_MODE", "").strip().lower()
         or str(_lee_config().get("system_mode", "cloud")).strip().lower())
    if m in ("1", "true", "on", "cloud"):
        return True
    if m in ("0", "false", "off", "hybrid"):
        return False
    return True


def system_mode() -> str:
    return "cloud" if cloud_only_mode() else "hybrid"


def guardar_system_mode(valor: str) -> str:
    m = (valor or "").strip().lower()
    if m not in MODOS_SISTEMA:
        raise ValueError("modo inválido: usa cloud o hybrid")
    d = _lee_config()
    d["system_mode"] = m
    _escribe_config(d)
    return m


def backend_imagen() -> str:
    b = os.environ.get("IMAGE_BACKEND", "").strip().lower()
    if b:
        return b
    return normaliza_backend_imagen(
        (_lee_config().get("image_backend") or "automatic1111").strip().lower()
    )


def guardar_backend_imagen(valor: str) -> str:
    b = normaliza_backend_imagen(valor)
    d = _lee_config()
    d["image_backend"] = b
    _escribe_config(d)
    return b


def automatic1111_url() -> str:
    return (os.environ.get("AUTOMATIC1111_URL", "").strip()
            or _lee_config().get("automatic1111_url")
            or "http://127.0.0.1:7860")


def comfyui_url() -> str:
    return (os.environ.get("COMFYUI_URL", "").strip()
            or _lee_config().get("comfyui_url")
            or "http://127.0.0.1:8188")


def comfyui_workflow() -> Path:
    p = (os.environ.get("COMFYUI_WORKFLOW", "").strip()
         or _lee_config().get("comfyui_workflow")
         or str(data_dir() / "comfyui-workflow.json"))
    return Path(p)


def sdxl_checkpoint() -> str:
    return (os.environ.get("SDXL_CHECKPOINT", "").strip()
            or _lee_config().get("sdxl_checkpoint")
            or "Realism Engine SDXL")


def loras() -> list[dict]:
    raw = os.environ.get("LORAS_JSON", "").strip()
    if raw:
        try:
            v = json.loads(raw)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        except json.JSONDecodeError:
            pass
    v = _lee_config().get("loras")
    if isinstance(v, list):
        return [x for x in v if isinstance(x, dict)]
    return []


def prompt_hq(prompt: str) -> str:
    base = prompt.strip()
    extras = []
    for lora in loras():
        nombre = str(lora.get("name") or "").strip()
        peso = lora.get("weight", 1.0)
        if nombre:
            extras.append(f"<lora:{nombre}:{peso}>")
    hdr = "photorealistic, ultra detailed, high quality, RAW, cinematic lighting"
    return ", ".join([hdr, base] + extras)


def negative_prompt_hq() -> str:
    return ("lowres, blurry, worst quality, bad anatomy, deformed, "
            "watermark, text, logo")


def calidad_imagen() -> str:
    return normaliza_calidad_imagen(
        os.environ.get("IMAGE_QUALITY", "").strip()
        or _lee_config().get("image_quality")
        or "ultra"
    )


def guardar_calidad_imagen(valor: str) -> str:
    q = normaliza_calidad_imagen(valor)
    d = _lee_config()
    d["image_quality"] = q
    _escribe_config(d)
    return q


def normaliza_backend_imagen(valor: str) -> str:
    b = (valor or "").strip().lower()
    if b not in BACKENDS_IMAGEN:
        raise ValueError("backend inválido: usa automatic1111 o comfyui")
    return b


def normaliza_calidad_imagen(valor: str) -> str:
    q = (valor or "").strip().lower()
    if q not in CALIDADES_IMAGEN:
        raise ValueError("calidad inválida: usa draft, standard o ultra")
    return q


def normaliza_aspect_ratio(valor: str) -> str:
    ar = (valor or "").strip()
    if ar not in ASPECTOS_VALIDOS:
        raise ValueError("aspect ratio inválido: usa 1:1, 16:9, 9:16, 4:3 o 3:4")
    return ar


def normaliza_duration(valor: str) -> str:
    d = (valor or "").strip().lower()
    if not re.match(r"^\d+(s|m)$", d):
        raise ValueError("duration inválida: usa formatos como 10s o 1m")
    if d.startswith("0"):
        raise ValueError("duration inválida: debe ser mayor que cero")
    return d


def controlnet_payload(refs: list[Path]) -> list[dict]:
    if not refs:
        return []
    img = refs[0]
    if not img.exists():
        return []
    return [{
        "enabled": True,
        "module": os.environ.get("CONTROLNET_MODULE", "canny"),
        "model": os.environ.get("CONTROLNET_MODEL", "controlnet-sdxl-canny"),
        "weight": float(os.environ.get("CONTROLNET_WEIGHT", "0.75")),
        "image": _to_b64(img),
        "resize_mode": "Just Resize",
        "guidance_start": 0.0,
        "guidance_end": 1.0,
        "control_mode": "Balanced",
        "pixel_perfect": True,
    }]


def faceswap_payload(refs: list[Path]) -> list:
    modo = (os.environ.get("FACESWAP_MODE", "").strip().lower()
            or str(_lee_config().get("faceswap_mode") or "").strip().lower())
    if modo not in ("reactor", "netcut"):
        return []
    if not refs:
        return []
    img = refs[0]
    if not img.exists():
        return []
    return [
        _to_b64(img),  # source face
        True,          # enabled
        "0",           # source index
        "0",           # target index
        "inswapper_128.onnx",
    ]


def _to_b64(p: Path) -> str:
    import base64
    return base64.b64encode(p.read_bytes()).decode("ascii")


def inyectar_prompt_comfyui(*, flujo: dict, prompt: str,
                            aspect_ratio: str, seed: int | None,
                            quality: str | None = None) -> dict:
    """Inyección mínima: busca nodos CLIPTextEncode/KSampler/EmptyLatentImage."""
    w, h = {
        "1:1": (1024, 1024), "16:9": (1344, 768),
        "9:16": (768, 1344), "4:3": (1152, 896),
        "3:4": (896, 1152),
    }.get(aspect_ratio, (1024, 1024))
    for _, node in (flujo or {}).items():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type")
        inp = node.get("inputs")
        if not isinstance(inp, dict):
            continue
        if ct == "CLIPTextEncode" and "text" in inp:
            inp["text"] = prompt
        if ct == "KSampler":
            if seed is not None:
                inp["seed"] = seed
            q = (quality or calidad_imagen()).lower()
            inp["steps"] = 22 if q == "draft" else 42 if q == "ultra" else 32
            inp["cfg"] = 5.0 if q == "draft" else 6.0 if q == "ultra" else 5.5
        if ct == "EmptyLatentImage":
            inp["width"] = w
            inp["height"] = h
    return flujo


def venice_api_key() -> str:
    return os.environ.get("VENICE_API_KEY", "").strip()


def modelo_video_seedance() -> str:
    return (os.environ.get("SEEDANCE_MODEL", "").strip()
            or _lee_config().get("seedance_model")
            or MODELO_VIDEO)
