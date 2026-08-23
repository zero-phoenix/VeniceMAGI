"""Historial de sesiones: sqlite mínimo, solo-append.

Existe para que el feedback de segunda ronda tenga contexto y para que
puedas releer qué se construyó ayer. Nada más.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path


class Historial:
    def __init__(self, ruta: Path):
        # check_same_thread=False + lock: la GUI consulta el historial
        # desde sus hilos HTTP mientras el kernel escribe en el suyo.
        self._c = sqlite3.connect(ruta, check_same_thread=False)
        self._lock = threading.Lock()
        self._c.execute(
            "CREATE TABLE IF NOT EXISTS rondas ("
            " id INTEGER PRIMARY KEY,"
            " ts REAL, peticion TEXT, sintesis TEXT,"
            " artefactos TEXT)")

    def anota(self, peticion: str, sintesis: str, artefactos: list[str]):
        with self._lock:
            self._anota(peticion, sintesis, artefactos)

    def _anota(self, peticion: str, sintesis: str, artefactos: list[str]):
        self._c.execute(
            "INSERT INTO rondas (ts, peticion, sintesis, artefactos) "
            "VALUES (?,?,?,?)",
            (time.time(), peticion, sintesis, "\n".join(artefactos)))
        self._c.commit()

    def ultimas(self, n: int = 10) -> list[dict]:
        with self._lock:
            return self._ultimas(n)

    def _ultimas(self, n: int = 10) -> list[dict]:
        filas = self._c.execute(
            "SELECT ts, peticion, sintesis, artefactos FROM rondas "
            "ORDER BY id DESC LIMIT ?", (n,)).fetchall()
        return [{"ts": f[0], "peticion": f[1], "sintesis": f[2],
                 "artefactos": (f[3] or "").splitlines()} for f in filas]

    def close(self):
        self._c.close()
