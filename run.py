"""Lanzador de VeniceMAGI (punto de entrada del exe).

GUI por defecto; --consola para el REPL; --selftest para el CI.
"""
from vmagi.app import arranca

if __name__ == "__main__":
    raise SystemExit(arranca())
