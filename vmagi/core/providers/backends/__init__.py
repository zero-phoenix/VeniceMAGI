"""
Backends de inferencia.

RESTRICCIÓN DEL PROYECTO: **solo IA de nube gratuita, sin claves de API y sin
modelos locales**. No hay backend de Ollama, ni de OpenRouter con clave, ni de
CLIs de suscripción.

DOS CAMINOS, NINGUNO CON CLAVE
==============================
1. `guest_web` — la página viva de un sitio guest, operada desde el Edge real
   del usuario. Es el CAMINO PRINCIPAL de VeniceMAGI: Venice y notrack.ai no
   tienen API sin clave (Venice mide la atestación del cliente y devuelve 403
   a todo lo que no sea un navegador de verdad), pero su web sí atiende sin
   cuenta.
2. `g4f` — proveedores gratuitos por HTTP. Aportan las familias que los sitios
   guest no cubren, y son la red que sostiene la diversidad cuando Venice
   agota su ración del día.

La diversidad del enjambre se consigue fijando la familia por nodo, no
dejando el auto-router. Ver g4f_backend.py y venice/sitios.py.
"""
from .echo import EchoProvider
from .g4f_backend import (
    DEFAULT_SWARM_FAMILIES,
    FAMILY_SPECS,
    G4FProvider,
    build_swarm_providers,
)
from .guest_web import GuestWebProvider, proveedores_guest

__all__ = [
    "EchoProvider", "G4FProvider", "FAMILY_SPECS", "DEFAULT_SWARM_FAMILIES",
    "GuestWebProvider", "proveedores_guest",
    "build_swarm_providers", "build_default_registry",
]

# Orden de preferencia entre familias.
#
# El orden anterior (deepseek 10, claude 15, qwen 20, ...) reflejaba qué
# familias razonan mejor EN TEORÍA. El problema es que `select_for_swarm`
# reparte los tres nodos por este orden, así que Melchior, Balthasar y Casper
# acababan en deepseek, claude y qwen: las tres familias que en la verificación
# empírica del 2026-08-06 no tienen ni un solo candidato vivo. El registro
# anunciaba "diversidad=full" con tres proveedores que no responden.
#
# Ahora manda lo verificado. Delante van las familias con al menos un candidato
# que contestó de verdad, ordenadas por latencia medida; detrás, las que hoy
# están agotadas —siguen registradas, porque pueden revivir, pero no se llevan
# los puestos del enjambre.
_PRIORITY = {
    # EL CAMINO PRINCIPAL de VeniceMAGI. Van delante de todo porque es lo
    # que el proyecto promete: sin cuenta y sin clave, en la web del
    # proveedor. Son más lentas que un endpoint HTTP —hay un navegador de
    # por medio— y aun así ganan el puesto: la promesa es la operación
    # guest, no el milisegundo.
    "venice": 1,        # Venice Guest: chat + imagen, ración diaria por IP
    "notrack": 2,       # notrack.ai: chat sin cuenta ni perfil, familia propia
    # verificadas: responden por HTTP, sin navegador (ms medidos)
    "gpt": 10,          # Yqcloud 2000ms · WeWordle 2389ms · CopilotApp 1156ms
    "gemini": 15,       # Gemini/gemini-3.5-flash 3421ms
    "command": 20,      # CohereForAI command-a-03-2025 1078ms
    "llama": 25,        # Groq 922ms
    "hf": 30,           # HuggingSpace 890ms
    "perplexity": 35,   # Perplexity/auto 7921ms (respuesta pobre)
    # sin candidato vivo hoy: se registran, pero al final
    "deepseek": 60, "claude": 65, "qwen": 70, "glm": 75,
    # red de seguridad
    "auto": 99,
}


async def build_default_registry(*, probe: bool = True, families=None,
                                 guest: bool = True):
    """
    Registra una familia por backend para que ProviderRegistry pueda repartir
    familias distintas entre Melchior, Balthasar y Casper.

    Primero los sitios guest (el camino principal: Venice y notrack.ai, sin
    cuenta ni clave), luego las familias de g4f. `auto` queda en última
    posición: sigue siendo la red de seguridad, no el camino principal.

    `guest=False` deja el registro solo con g4f. Es lo que usan los tests y
    cualquier entorno sin Edge — un registro que exige navegador donde no lo
    hay no arranca, y un sistema que no arranca no se puede diagnosticar.
    """
    from ..registry import ProviderRegistry

    reg = ProviderRegistry()
    if guest:
        for p in proveedores_guest():
            reg.register(p, priority=_PRIORITY.get(p.family, 5))
    for family in (families or FAMILY_SPECS.keys()):
        reg.register(G4FProvider(family=family), priority=_PRIORITY.get(family, 80))
    if probe:
        await reg.probe_all()
    return reg
