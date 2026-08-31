"""El REPL de consola de VeniceMAGI: `VeniceMAGI.exe --consola`.

POR QUE SIGUE EXISTIENDO
========================
La v2 trae ventana propia, y podria parecer que la consola sobra. No sobra,
por dos motivos que son distintos:

1. **El manifiesto la promete.** «`VeniceMAGI.exe` abre la ventana;
   `--consola` mantiene el REPL», y con ella los comandos `/magi`, `/salud`,
   `/imagen`, `/video`, `/modo`, `/vpn`... Un README que promete una interfaz
   que no arranca es una promesa incumplida.
2. **Es la unica que funciona cuando la GUI no.** Si pywebview no levanta,
   si el frontend no compilo, si la ventana sale en blanco — la consola sigue
   dando salud, historial y galeria. Un diagnostico que necesita la interfaz
   averiada no sirve para diagnosticarla.

Los modulos de aqui son los del REPL de la v1, con sus imports reapuntados al
nucleo `vmagi.venice`. No duplican el enjambre grande de `vmagi.modules.swarm`:
son la ruta corta, cuatro roles sobre un proveedor guest, que es lo que cabe en
una consola.
"""
from __future__ import annotations

__all__ = ["main"]


def main():
    """Arranca el REPL. Import perezoso: la GUI no debe pagar por esto."""
    from .app import main as _main
    return _main()
