"""Una ronda dialéctica completa: Naoko → Melchior → Balthasar → Casper.

Todos son Venice. El mismo modelo construye, ataca y decide, con contratos
que se contradicen a propósito: la evidencia de Balthasar no es la opinión
de otro modelo, es el STDOUT de haber ejecutado lo de Melchior.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from ..venice.cliente import Venice
from . import roles
from .tools import Ejecutor, parsea_herramientas


@dataclass
class Ronda:
    peticion: str
    tesis: str = ""
    evidencia: str = ""          # salida de las herramientas de Melchior
    antitesis: str = ""
    sintesis: str = ""
    artefactos: list[str] = field(default_factory=list)
    nota_naoko: str = ""


class Orquestador:
    def __init__(self, venice: Venice, workspace, kernel=None):
        self.v = venice
        #: el kernel permite a las herramientas pedir aprobación (shell)
        self.ejecutor = Ejecutor(venice, workspace, kernel=kernel)

    # ---------------------------------------------------------- naoko

    async def clasifica(self, peticion: str) -> dict:
        """Naoko decide qué es la petición. Siempre en JSON."""
        try:
            r = await self.v.chat(roles.NAOKO, peticion,
                                  temperature=0.0, json_mode=True)
            d = json.loads(r.texto)
            if d.get("tipo") in ("construccion", "consulta", "estado"):
                return d
        except (json.JSONDecodeError, KeyError):
            pass
        # Naoko es Venice; si su JSON llega roto, no se cae nada: se
        # construye. Es la opción por defecto y la que más puede hacer.
        return {"tipo": "construccion", "estilo": "tecnico", "nota": ""}

    # ---------------------------------------------------------- ronda

    async def ronda(self, peticion: str, *,
                    feedback: str = "",
                    previa: Ronda | None = None) -> Ronda:
        r = Ronda(peticion=peticion)

        naoko = await self.clasifica(peticion)
        r.nota_naoko = (naoko.get("nota") or "").strip()
        if naoko["tipo"] == "estado":
            # Naoko responde directamente: no hay nada que construir.
            r.sintesis = await self._estado()
            return r
        if naoko["tipo"] == "consulta":
            r.sintesis = (await self.v.chat(
                roles.CASPER,
                self._usuario(peticion, feedback, previa),
                temperature=0.3)).texto
            return r

        # ---- MELCHIOR (tesis): construye con herramientas de verdad
        prompt_m = self._usuario(peticion, feedback, previa)
        if previa:
            prompt_m = (f"PETICIÓN ORIGINAL:\n{peticion}\n\n"
                        f"SÍNTESIS ANTERIOR:\n{previa.sintesis}\n\n"
                        f"ANTÍTESIS ANTERIOR:\n{previa.antitesis}\n\n"
                        f"FEEDBACK DEL USUARIO:\n{feedback}")
        resp = await self.v.chat(roles.MELCHIOR, prompt_m, temperature=0.3)
        r.tesis = resp.texto
        r.evidencia = await self._ejecuta(resp.texto, "MELCHIOR", r)

        # ---- BALTHASAR (antítesis): refuta ejecutando
        prompt_b = (f"PETICIÓN DEL USUARIO:\n{peticion}\n\n"
                    f"TESIS DE MELCHIOR:\n{r.tesis}\n\n"
                    f"LO QUE SUS HERRAMIENTAS PRODUJERON:\n{r.evidencia}\n\n"
                    "Ejecuta lo que haga falta con run_python y refuta con "
                    "la evidencia. Si no encuentras ningún fallo real, "
                    "dilo con la prueba que lo demuestra.")
        resp = await self.v.chat(roles.BALTHASAR, prompt_b, temperature=0.2)
        r.antitesis = resp.texto
        extra = await self._ejecuta(resp.texto, "BALTHASAR", r)
        if extra:
            r.antitesis += f"\n\n[ejecutado por Balthasar]\n{extra}"

        # ---- CASPER (síntesis): decide y entrega
        prompt_c = (f"PETICIÓN DEL USUARIO:\n{peticion}\n\n"
                    f"TESIS DE MELCHIOR:\n{r.tesis}\n\n"
                    f"ANTÍTESIS DE BALTHASAR:\n{r.antitesis}\n\n"
                    "Integra y entrega la respuesta definitiva en español: "
                    "qué se hizo, rutas de los artefactos, qué falló y qué "
                    "queda pendiente. Si hay que corregir un fichero, "
                    "corrígelo con write_file.")
        resp = await self.v.chat(roles.CASPER, prompt_c, temperature=0.3)
        r.sintesis = resp.texto
        await self._ejecuta(resp.texto, "CASPER", r)
        return r

    # ---------------------------------------------------------- piezas

    async def _ejecuta(self, texto: str, quien: str, r: Ronda) -> str:
        """Ejecuta los bloques ```tool``` y devuelve la evidencia."""
        llamadas = parsea_herramientas(texto)
        if not llamadas:
            return "(sin herramientas)"
        partes = []
        for linea in llamadas:
            res = await self.ejecutor.ejecuta(linea)
            partes.append(f"· {linea.herramienta}({', '.join(linea.args)}) → "
                          f"{res.render()}")
            if res.ruta:
                r.artefactos.append(str(res.ruta))
        return "\n".join(partes)

    def _usuario(self, peticion: str, feedback: str,
                 previa: Ronda | None) -> str:
        base = f"PETICIÓN DEL USUARIO:\n{peticion}"
        if previa and feedback:
            base += (f"\n\nSÍNTESIS ANTERIOR:\n{previa.sintesis}\n\n"
                     f"FEEDBACK DEL USUARIO:\n{feedback}")
        return base

    async def _estado(self) -> str:
        try:
            modelos = await self.v.modelos()
            n = len(modelos)
        except Exception as e:                           # noqa: BLE001
            return f"Venice no respondió al listar modelos: {e}"
        return (f"Sistema: VeniceMAGI opera solo con Venice. "
                f"{n} modelos disponibles; enjambre monocultivo "
                f"(Melchior, Balthasar, Casper y Naoko son el mismo modelo).")
