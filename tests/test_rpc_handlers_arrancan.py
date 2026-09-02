"""
Test de humo de TODOS los handlers RPC, y del bus que no debe bloquear.

POR QUÉ EXISTE
==============
Se añadió el handler `sys.config` con su panel, sus tests de la lógica y su
componente de interfaz... y nadie lo invocó nunca de extremo a extremo. Dentro
hacía:

    from vmagi.core.tools import ALL_DOMAINS

y `ALL_DOMAINS` no estaba reexportado en `vmagi/core/tools/__init__.py`. El
handler lanzaba ImportError en CADA llamada.

Y de ahí, un fallo tonto tumbó la aplicación entera:

    ImportError -> log ERROR -> evento error.critical -> Naoko diagnostica con
    inferencia -> su cola se llena -> el bus BLOQUEA al productor -> el
    productor era el logging -> se para todo.

El usuario escribió «crea un documento de word en mi escritorio» y no ocurrió
nada, porque ya no quedaba nadie libre para atenderle.

La lección no es «acuérdate de exportar el nombre». Es que un handler que
nadie invoca en los tests es un handler que no existe hasta que un usuario lo
pulsa. Este fichero recorre el registro de handlers REAL: cuando se añada el
siguiente, entra solo.
"""
from __future__ import annotations

import asyncio
import logging

import pytest

from vmagi.core.bus import BusEvent, MagiBus

# ============================================ todos los handlers arrancan

def _kernel_handlers() -> dict:
    """
    Los handlers que el kernel registra DE VERDAD, leídos del registro.

    Se construye el kernel con dependencias mínimas; lo que importa aquí no es
    que hagan su trabajo, sino que se puedan invocar sin reventar al importar.
    """
    from vmagi.core.blackboard import Blackboard
    from vmagi.core.kernel import Kernel

    bus = MagiBus()
    _BUSES_ABIERTOS.append(bus)
    try:
        k = Kernel(bus=bus, blackboard=Blackboard())
    except TypeError:
        k = Kernel(bus)
    return k, dict(k.rpc.handlers)


#: Cada kernel que se construye aquí arranca un `MagiBus._worker()` de fondo, y
#: nadie los paraba. Al cerrarse el bucle del test quedaban tareas pendientes y
#: pytest lo reportaba como ERROR *en el teardown* — cuatro por corrida,
#: mientras las aserciones pasaban todas. Un error de teardown es peor que uno
#: normal: no señala a la línea que falla, se lee como ruido, y se aprende a
#: ignorar. Y aquí además escondía una fuga de verdad, en el mismo bus cuyo
#: bloqueo tumbó la aplicación entera y por el que existe este fichero.
#:
#: `MagiBus.shutdown()` ya estaba escrito. Solo faltaba llamarlo.
_BUSES_ABIERTOS: list[MagiBus] = []


@pytest.fixture(autouse=True)
def _limpia_buses_de_tests_sincronos():
    """Los tests SÍNCRONOS no tienen bucle, así que sus buses no llegan a
    crear tareas — pero sí dejan colas y trabajadores pendientes apuntados.
    Se vacían aquí; las tareas de verdad las recoge la fixture de abajo."""
    yield
    for bus in _BUSES_ABIERTOS:
        for t in list(getattr(bus, "_worker_tasks", [])):
            if not t.done():
                t.cancel()
        try:
            bus._worker_tasks.clear()
            bus._pending_workers.clear()
        except Exception:          # pragma: no cover
            pass                   # limpiar no puede hacer fallar un test
    _BUSES_ABIERTOS.clear()


@pytest.fixture(autouse=True)
async def _no_dejar_tareas_colgando():
    """Guarda general: ninguna tarea creada por un test sobrevive al test.

    POR QUÉ GENERAL Y NO UNA POR FUGA
    =================================
    El primer arreglo cancelaba los buses que registra `_kernel_handlers`, y
    bajó los errores de teardown de 4 a 1. Al mirar QUÉ seguía colgando en vez
    de suponerlo aparecieron dos cosas distintas:

      · tres `MagiBus._worker()` de buses que otros tests construyen
        directamente, sin pasar por `_kernel_handlers`;
      · un `SwarmOrchestrator._orchestrate_loop()`, que arranca al invocar
        uno de los handlers y no lo para nadie.

    Perseguirlas de una en una arregla estas dos y deja abierta la tercera,
    la que se añada mañana. Este fichero invoca **todos** los handlers
    registrados a propósito —para eso existe—, así que cualquiera de ellos
    puede arrancar trabajo de fondo. La responsabilidad de recogerlo es del
    arnés, no de cada handler.

    Se cancela lo que quede vivo y se espera a que muera. `gather` con
    `return_exceptions=True` porque una `CancelledError` es lo esperado aquí,
    no un fallo: si no se esperase, la tarea se destruiría igual «pendiente» y
    el error de teardown seguiría saliendo.
    """
    antes = {t for t in asyncio.all_tasks()}
    yield
    pendientes = [t for t in asyncio.all_tasks()
                  if t not in antes and t is not asyncio.current_task()
                  and not t.done()]
    for t in pendientes:
        t.cancel()
    if pendientes:
        await asyncio.gather(*pendientes, return_exceptions=True)


def test_el_kernel_registra_handlers():
    _, handlers = _kernel_handlers()
    assert handlers, "el kernel no registró ningún handler RPC"
    # Los que la interfaz necesita para pintar sus pestañas.
    for imprescindible in ("sys.config", "artifacts.list", "obs.metrics"):
        assert imprescindible in handlers, f"falta el handler {imprescindible}"


@pytest.mark.asyncio
async def test_ningun_handler_falla_por_un_import():
    """
    Se invoca CADA handler registrado y se exige que no muera por un
    ImportError, AttributeError o NameError: los tres fallos que significan
    «este código nunca se ejecutó».

    Un fallo de lógica o de red es aceptable aquí (no hay proveedores ni
    ficheros); un fallo de importación no, porque significa que el handler
    está roto para siempre y nadie lo sabía.
    """
    _, handlers = _kernel_handlers()
    rotos: list[str] = []

    for nombre, fn in handlers.items():
        try:
            await asyncio.wait_for(fn({}, None), timeout=25)
        except (ImportError, AttributeError, NameError) as e:
            rotos.append(f"{nombre}: {type(e).__name__}: {e}")
        except Exception:
            pass          # lógica, red o falta de datos: no es lo que se mide

    assert not rotos, ("estos handlers están rotos de raíz y la interfaz los "
                       "llama: " + " | ".join(rotos))


@pytest.mark.asyncio
async def test_sys_config_devuelve_lo_que_la_interfaz_pinta():
    """
    El contrato concreto del panel de Configuración. Si cambia una clave, la
    pestaña se queda a medias sin que nada avise.
    """
    _, handlers = _kernel_handlers()
    cfg = await asyncio.wait_for(handlers["sys.config"]({}, None), timeout=30)

    for clave in ("enjambre", "familias", "inferencia", "herramientas",
                  "dominios", "rutas", "cortafuegos"):
        assert clave in cfg, f"sys.config ya no devuelve '{clave}'"
    assert "reparto" in cfg["enjambre"] and "diversidad" in cfg["enjambre"]
    assert isinstance(cfg["familias"], list) and cfg["familias"]
    assert {"MELCHIOR", "BALTHASAR", "CASPER"} <= set(cfg["herramientas"])


def test_all_domains_se_puede_importar_del_paquete():
    """El import exacto que hacía el kernel y que lanzaba ImportError."""
    from vmagi.core.tools import ALL_DOMAINS, registry_for_role  # noqa: F401
    assert ALL_DOMAINS and "core" in ALL_DOMAINS


def test_lo_que_el_paquete_promete_existe():
    """
    `__all__` no puede prometer nombres que no están. Es la comprobación
    genérica del fallo concreto: alguien importa del paquete y no está.
    """
    import vmagi.core.tools as t
    faltan = [n for n in t.__all__ if not hasattr(t, n)]
    assert not faltan, f"__all__ promete nombres inexistentes: {faltan}"


# ==================================================== el bus no bloquea

@pytest.mark.asyncio
async def test_el_bus_no_bloquea_al_productor_con_la_cola_llena():
    """
    LA REGRESIÓN QUE CONGELÓ EL SISTEMA.

    `publish` hacía `await q.put(event)` cuando la cola estaba llena. Con un
    consumidor lento —Naoko diagnosticando con inferencia real— eso bloqueaba
    a quien publicaba, que era el propio logging. Todo se paraba.
    """
    bus = MagiBus()

    async def consumidor_lento(_e):
        await asyncio.sleep(3600)      # no consume nunca

    # Cola pequeña a propósito: el punto es qué pasa AL LLENARSE, no cuánto
    # cabe. Con la de por defecto (1024) harían falta miles de eventos para
    # provocar lo mismo y el test tardaría en balde.
    bus.subscribe("error.critical", consumidor_lento, maxsize=8)
    bus.start_pending_workers()

    await asyncio.wait_for(
        asyncio.gather(*(bus.publish(BusEvent(topic="error.critical",
                                              payload={"n": i}))
                         for i in range(200))),
        timeout=10)          # antes: se colgaba aquí para siempre

    assert bus.dropped_report().get("error.critical", 0) > 0, \
        "con la cola llena hay que descartar, no esperar"


@pytest.mark.asyncio
async def test_publicar_sin_nadie_escuchando_no_revienta():
    bus = MagiBus()
    await asyncio.wait_for(
        bus.publish(BusEvent(topic="nadie.escucha", payload={})), timeout=5)


# ============================================ el log no se realimenta

class _BusEspia(MagiBus):
    """Anota los tópicos publicados en vez de repartirlos."""

    def __init__(self, eco: bool = False):
        super().__init__()
        self.topicos: list[str] = []
        self._eco = eco

    async def publish(self, event):            # type: ignore[override]
        self.topicos.append(event.topic)
        if self._eco:
            # Publicar genera un log, igual que hace el bus real al descartar.
            logging.getLogger("vmagi.core.bus").warning("cola llena")


async def _emitir(logger_name: str, nivel: int, mensaje: str, veces: int = 1,
                  eco: bool = False):
    """
    Emite registros con el handler puesto, DENTRO de un bucle en marcha.

    El bucle importa: `BusLogHandler` publica con `asyncio.create_task`, que
    necesita un bucle corriendo. Sin él no publica nada y el test mediría el
    vacío en vez de la conducta.
    """
    from vmagi.core.obs.bus_log_handler import BusLogHandler

    bus = _BusEspia(eco=eco)
    h = BusLogHandler(bus)
    log = logging.getLogger(logger_name)
    log.addHandler(h)
    try:
        for _ in range(veces):
            log.log(nivel, mensaje)
        await asyncio.sleep(0.05)      # que corran las tareas creadas
    finally:
        log.removeHandler(h)
    return bus, h


@pytest.mark.asyncio
async def test_el_handler_de_log_no_reentra():
    """
    El aviso de «cola llena» era un WARNING, y ese WARNING volvía a pasar por
    el handler generando otro evento. El sistema se ahogaba con sus propios
    mensajes de que se estaba ahogando: cientos de líneas idénticas.
    """
    bus, _ = await _emitir("prueba.reentrada", logging.ERROR, "algo falló",
                           eco=True)
    assert len(bus.topicos) <= 2, \
        f"el handler se realimentó: {len(bus.topicos)} publicaciones"


@pytest.mark.asyncio
async def test_el_handler_de_log_no_repite_el_mismo_error():
    """Doscientas copias del mismo ImportError no informan más que una."""
    _, h = await _emitir("prueba.repetidos", logging.ERROR,
                         "cannot import name 'ALL_DOMAINS'", veces=200)
    assert h.suprimidos >= 190, \
        f"solo se suprimieron {h.suprimidos} de 200 repeticiones"


@pytest.mark.asyncio
async def test_un_panel_roto_no_es_una_emergencia_del_sistema():
    """
    Que falle un handler RPC degrada un panel; no es una avería que merezca
    gastar inferencia del enjambre en diagnosticarla. Antes, cada uno de esos
    errores despertaba a Naoko.
    """
    bus, _ = await _emitir("vmagi.core.rpc.ws_server", logging.ERROR,
                           "el handler 'sys.config' falló")
    assert "error.critical" not in bus.topicos, \
        "un handler RPC roto no debe despertar el diagnóstico del enjambre"
    assert "TERMINAL_OUT" in bus.topicos, "pero sí debe verse en la terminal"


@pytest.mark.asyncio
async def test_un_fallo_de_verdad_SI_despierta_a_naoko():
    """
    Contraprueba: filtrar de más sería peor que no filtrar. Un error del
    núcleo tiene que seguir llegando al diagnóstico.
    """
    bus, _ = await _emitir("vmagi.modules.swarm.orchestrator", logging.ERROR,
                           "error catastrófico durante la orquestación")
    assert "error.critical" in bus.topicos
