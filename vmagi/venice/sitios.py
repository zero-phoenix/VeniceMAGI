"""Los sitios guest que VeniceMAGI sabe operar: sin cuenta y sin clave.

POR QUE ESTO ES UNA TABLA Y NO CONSTANTES SUELTAS
=================================================
La v1 traia el Guest de Venice hardcodeado en la puerta: la URL, el texto
del enlace de entrada, las marcas del modal y las del cupo vivian
esparcidas por `sesion.py` y `venice.py`. Anadir un segundo sitio guest
exigia tocar las dos, y cualquier cambio en la web de uno se llevaba por
delante al otro.

Aqui cada sitio declara lo suyo. La puerta es la misma para todos y no
sabe de ninguno en concreto: recibe un `SitioGuest` y lo opera. Anadir un
proveedor guest nuevo es anadir una fila, no reescribir el navegador.

EL PRINCIPIO QUE ESTA TABLA NO PUEDE ROMPER
===========================================
Ninguna fila puede exigir cuenta, clave o login en el camino principal.
Un sitio que pida credenciales no entra aqui: entra en `hybrid`, que es
opcional y el usuario activa a mano. `test_sitios_sin_credenciales` lo
comprueba.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SitioGuest:
    """Todo lo que la puerta necesita saber de un sitio guest."""

    #: identificador interno, y prefijo de la familia de proveedor
    nombre: str
    #: familia de modelo que este sitio aporta al enjambre. Es EL eje de la
    #: independencia: dos nodos con la misma familia no se critican, se
    #: hacen eco. Ver `vmagi/core/providers/registry.py`.
    familia: str
    #: la pagina de chat sin cuenta
    url: str
    #: textos del enlace/boton que entra como invitado (se prueban en orden;
    #: si ninguno aparece, el sitio ya entra sin pedir nada)
    entradas_guest: tuple[str, ...] = ()
    #: textos que delatan el modal de login. Verlos NO es pedir credenciales
    #: al usuario: es reentrar como invitado y repetir.
    marcas_modal: tuple[str, ...] = ()
    #: textos con los que el sitio dice que hoy se acabo la racion
    marcas_cupo: tuple[str, ...] = ()
    #: adornos de la interfaz que se recortan de la respuesta
    marcas_ui: tuple[str, ...] = ()
    #: selector del campo donde se escribe
    selector_entrada: str = "textarea"
    #: capacidades declaradas. `False` no se disimula: se dice.
    chat: bool = True
    imagen: bool = False
    video: bool = False
    #: FECHA en que se midio que este sitio contesta de verdad. Vacio
    #: significa «nadie lo ha medido», y eso NO es lo mismo que «funciona».
    #:
    #: Vive aqui y no solo en el catalogo JSON porque el catalogo se cae a
    #: su respaldo de Python cuando el fichero falta o no valida, y en ese
    #: momento la fecha desaparecia: un test que preguntase «esta esta
    #: familia verificada?» pasaba o fallaba segun un fichero que ni
    #: siquiera es el suyo. La medida vive donde vive el sitio.
    verificado: str = ""
    #: nota honesta que la GUI y `/salud` muestran tal cual
    nota: str = ""
    etiquetas: tuple[str, ...] = field(default_factory=tuple)

    @property
    def verificada(self) -> bool:
        return bool(self.verificado)

    def capacidades(self) -> tuple[str, ...]:
        return tuple(n for n, v in (("chat", self.chat), ("imagen", self.imagen),
                                    ("video", self.video)) if v)


#: Venice Guest. Medido el 2026-08-16: la API oficial exige clave y el
#: flujo anonimo legacy esta muerto, pero el Guest de la web funciona
#: desde un Edge REAL — con Chromium headless devuelve 403 (atestacion de
#: cliente), con el Edge de la maquina devuelve 200. Por eso la puerta usa
#: el navegador del usuario y no uno propio.
VENICE = SitioGuest(
    nombre="venice",
    familia="venice",
    url="https://venice.ai/chat/classic",
    entradas_guest=("sin una cuenta", "without an account"),
    marcas_modal=("Inicia sesion en tu cuenta", "Inicia sesión en tu cuenta",
                  "Email address", "Sign in to your account"),
    marcas_cupo=("Has superado el numero de solicitudes",
                 "Has superado el número de solicitudes",
                 "solicitudes de Chat", "couldn't be sent"),
    marcas_ui=("Ask anything privately", "Pregunte cualquier cosa",
               "Automatico", "Automático", "Auto\n",
               "Get Pro Access", "Obtener acceso a Pro"),
    chat=True, imagen=True, video=False,
    verificado="2026-08-16",
    nota="Racion diaria por IP. Agotada, toca volver manana: el sistema no "
         "rota IP ni perfiles para esquivarla.",
    etiquetas=("guest", "sin-clave", "imagen"),
)

#: NoTrack. Chat gratuito sin cuenta ni registro, con modelo propio e
#: independiente de las familias de Venice — que es justo lo que hace que
#: valga como segundo motor: un critico que comparte modelo con el autor
#: no critica, confirma.
NOTRACK = SitioGuest(
    nombre="notrack",
    familia="notrack",
    url="https://notrack.ai/chat",
    entradas_guest=(),
    marcas_modal=("Sign in", "Create account"),
    marcas_cupo=("rate limit", "too many requests", "limite alcanzado"),
    marcas_ui=("Open full chat", "Powered by NoTrack", "Shuffle",
               "Try asking"),
    chat=True, imagen=False, video=False,
    verificado="2026-08-30",
    nota="Chat sin cuenta y sin perfil. No genera imagen: para arte entra "
         "como director y critico del plano, no como pincel.",
    etiquetas=("guest", "sin-clave", "sin-perfil"),
)

#: El registro. El orden importa: el primero es el camino principal.
SITIOS: dict[str, SitioGuest] = {s.nombre: s for s in (VENICE, NOTRACK)}


def sitio(nombre: str) -> SitioGuest:
    try:
        return SITIOS[nombre.strip().lower()]
    except KeyError:
        disponibles = ", ".join(SITIOS)
        raise ValueError(
            f"sitio guest desconocido: {nombre!r}. Hay: {disponibles}"
        ) from None


def sitios_con(capacidad: str) -> tuple[SitioGuest, ...]:
    """Los sitios que declaran una capacidad. Vacio es una respuesta valida."""
    return tuple(s for s in SITIOS.values() if capacidad in s.capacidades())
