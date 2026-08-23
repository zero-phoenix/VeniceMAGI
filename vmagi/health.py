"""Healthchecks de providers y configuración activa."""
from __future__ import annotations

from . import config, sesion


def estado_salud() -> dict:
    cloud_only = config.cloud_only_mode()
    backend = "venice-guest-free" if cloud_only else config.backend_imagen()
    modelo_video = config.modelo_video_seedance()
    notrack = config.notrack_proxy()
    checks = {
        "cloud_only_mode": cloud_only,
        "edge_disponible": sesion.edge_disponible(),
        "notrack_configurado": bool(notrack),
        "notrack_obligatorio": config.notrack_obligatorio(),
        "backend_imagen": backend,
        "backend_imagen_ok": (backend == "venice-guest-free"
                              if cloud_only else backend in ("automatic1111", "comfyui")),
        "seedance_modelo": modelo_video,
        "seedance_ok": ("seedance-2.5" in modelo_video or "seedance-3" in modelo_video),
        "venice_api_key": bool(config.venice_api_key()),
        "video_guest_free": False if cloud_only else None,
    }
    checks["ok_global"] = (
        checks["edge_disponible"]
        and (checks["notrack_configurado"] or not checks["notrack_obligatorio"])
        and checks["backend_imagen_ok"]
        and (True if cloud_only else checks["seedance_ok"])
    )
    return checks
