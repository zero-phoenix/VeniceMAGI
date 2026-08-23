"""Configuración de VeniceMAGI: clave, modelos y directorios."""
from __future__ import annotations

import json
import os
from pathlib import Path

NOMBRE = "VeniceMAGI"
VERSION = "2.0.0"

BASE_URL = "https://api.venice.ai/api/v1"

#: Modelos por defecto. Los tres roles son el MISMO modelo — la dialéctica
#: está en los contratos, no en la diversidad. Cambiar el modelo aquí cambia
#: a los cuatro (enjambre + Naoko) a la vez: monocultivo deliberado.
MODELO_TEXTO = "zai-org-glm-5"          # default de la documentación
MODELO_IMAGEN = "flux-dev"              # el de la web, sin cuenta
MODELO_VIDEO = "seedance-2-0-text-to-video-basic"  # puede exigir cuenta

#: Consensos que exige /video/queue para modelos seedance. Sin los tres
#: `true` responde 409 needs_consent y el vídeo no entra en cola.
CONSENTS_SEEDANCE = {
    "seedance": {
        "acceptProhibitedContentPolicy": True,
        "acceptThirdPartyLicensingPolicy": True,
        "acceptDeathOrHarmPolicy": True,
    }
}


def data_dir() -> Path:
    """Directorio de datos del usuario. Nunca el CWD del exe."""
    d = Path(os.environ.get("VENICE_MAGI_DIR")
             or Path(os.environ.get("LOCALAPPDATA", Path.home())) / NOMBRE)
    d.mkdir(parents=True, exist_ok=True)
    return d


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
    f = _ruta_config()
    datos: dict = {}
    if f.exists():
        try:
            datos = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            datos = {}
    valor = (valor or "").strip()
    if valor:
        datos["proxy"] = valor
    else:
        datos.pop("proxy", None)
    f.write_text(json.dumps(datos, indent=1), encoding="utf-8")


def _ruta_config() -> Path:
    return data_dir() / "config.json"


def _leer_config() -> dict:
    f = _ruta_config()
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _escribir_config(datos: dict) -> None:
    _ruta_config().write_text(json.dumps(datos, indent=1), encoding="utf-8")


def puerta_visible() -> bool:
    """Modo de la puerta de Edge. Aparcada (off-screen) por defecto."""
    import os
    if os.environ.get("VENICE_PUERTA_VISIBLE", "").strip() in ("1", "true"):
        return True
    return bool(_leer_config().get("puerta_visible", False))


def fijar_puerta_visible(valor: bool) -> None:
    d = _leer_config()
    d["puerta_visible"] = bool(valor)
    _escribir_config(d)


def permitir_shell() -> bool:
    import os
    if os.environ.get("VENICE_PERMITIR_SHELL", "").strip() in ("1", "true"):
        return True
    return bool(_leer_config().get("permitir_shell", False))


def fijar_permitir_shell(valor: bool) -> None:
    d = _leer_config()
    d["permitir_shell"] = bool(valor)
    _escribir_config(d)


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
