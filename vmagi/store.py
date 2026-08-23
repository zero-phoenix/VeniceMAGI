"""Historial de sesiones: sqlite mínimo, solo-append.

Existe para que el feedback de segunda ronda tenga contexto y para que
puedas releer qué se construyó ayer. Nada más.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path


class Historial:
    def __init__(self, ruta: Path):
        self._c = sqlite3.connect(ruta)
        self._c.execute(
            "CREATE TABLE IF NOT EXISTS rondas ("
            " id INTEGER PRIMARY KEY,"
            " ts REAL, peticion TEXT, sintesis TEXT,"
            " artefactos TEXT)")
        self._c.execute(
            "CREATE TABLE IF NOT EXISTS renders ("
            " id INTEGER PRIMARY KEY,"
            " ts REAL, kind TEXT, prompt TEXT, ruta TEXT, metadata TEXT)")

    def anota(self, peticion: str, sintesis: str, artefactos: list[str]):
        self._c.execute(
            "INSERT INTO rondas (ts, peticion, sintesis, artefactos) "
            "VALUES (?,?,?,?)",
            (time.time(), peticion, sintesis, "\n".join(artefactos)))
        self._c.commit()

    def ultimas(self, n: int = 10) -> list[dict]:
        filas = self._c.execute(
            "SELECT ts, peticion, sintesis, artefactos FROM rondas "
            "ORDER BY id DESC LIMIT ?", (n,)).fetchall()
        return [{"ts": f[0], "peticion": f[1], "sintesis": f[2],
                 "artefactos": (f[3] or "").splitlines()} for f in filas]

    def anota_render(self, *, kind: str, prompt: str, ruta: str,
                     metadata: str = "") -> None:
        self._c.execute(
            "INSERT INTO renders (ts, kind, prompt, ruta, metadata) "
            "VALUES (?,?,?,?,?)",
            (time.time(), kind, prompt, ruta, metadata))
        self._c.commit()

    def ultimos_renders(self, n: int = 10) -> list[dict]:
        filas = self._c.execute(
            "SELECT ts, kind, prompt, ruta, metadata FROM renders "
            "ORDER BY id DESC LIMIT ?", (n,)).fetchall()
        return [{
            "ts": f[0], "kind": f[1], "prompt": f[2],
            "ruta": f[3], "metadata": f[4],
        } for f in filas]

    def close(self):
        self._c.close()
