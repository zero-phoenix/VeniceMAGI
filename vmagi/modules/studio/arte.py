"""El taller de arte: dos IAs que crean por separado y una tercera que juzga.

QUE PROBLEMA RESUELVE
=====================
Pedirle una imagen a un modelo y quedarse con lo que salga tiene dos
fallos que no se ven hasta que se miran juntos:

1. **Un solo autor no tiene con quien contrastar.** Si el modelo entiende
   mal el encargo, el resultado es coherente consigo mismo y no hay nada
   que lo delate. Es el mismo problema que el enjambre resuelve para el
   codigo con tesis y antitesis, y no habia equivalente para el arte.
2. **Nadie comprueba que lo entregado es lo pedido.** «Salio una imagen»
   se confunde con «salio LA imagen». Un encargo de cuatro promesas
   («vertical», «sin texto», «dos personajes», «de noche») se entrega con
   dos cumplidas y nadie las cuenta.

EL TALLER, EN TRES PIEZAS
=========================
- **Dos autores separados.** Venice y notrack reciben el MISMO encargo y
  no se ven entre ellos. Cada uno redacta su propia lectura y su propio
  prompt. Que sean familias de modelo distintas es lo que hace que la
  discrepancia signifique algo: dos lecturas del mismo modelo son una
  lectura repetida.
- **Un critico mas estricto, en una TERCERA familia.** No participa en la
  creacion. Su unico trabajo es contar promesas cumplidas contra el
  contrato, y su sesgo por diseno es el contrario del de un autor: donde
  el autor quiere entregar, el critico quiere encontrar el fallo.
- **Reintento dirigido.** Un veredicto negativo no manda «hazlo mejor»:
  manda la lista concreta de promesas incumplidas, para que la siguiente
  pasada arregle ESO.

LO QUE ESTE MODULO NO FINGE
===========================
notrack.ai **no genera imagenes**: es un chat. Entra como autor de pleno
derecho —redacta su lectura del encargo y su prompt, en paralelo y sin
ver al otro— y el pincel lo pone Venice (o, en `hybrid`, el backend local
del usuario). Decirlo asi es la quinta regla del proyecto: «no he podido
comprobarlo» no es «esta bien», y «notrack pinto esto» seria falso.

Y los modelos guest **no tienen vision**: no pueden mirar el PNG. Por eso
el critico separa lo que MIDE una maquina (existe, abre, dimensiones,
proporcion, no esta en blanco) de lo que juzga leyendo (si el prompt
recoge el encargo entero), y declara explicitamente lo que no ha podido
verificar en vez de aprobarlo por omision.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = [
    "Encargo", "Criterio", "Propuesta", "Medida", "Veredicto", "Obra",
    "TallerDeArte", "FAMILIA_CRITICO", "AUTORES",
]

#: Los dos autores, por familia. Separados a proposito: el taller nunca
#: les pasa el trabajo del otro antes de que ambos hayan entregado.
AUTORES: tuple[str, ...] = ("venice", "notrack")

#: La familia del critico, en orden de preferencia. NINGUNA puede estar en
#: AUTORES: un critico que corre el mismo modelo que el autor no critica,
#: confirma. `test_critico_no_comparte_familia` lo exige.
FAMILIA_CRITICO: tuple[str, ...] = ("gemini", "command", "gpt")

#: Cuantas pasadas antes de rendirse. Cuatro no es un numero magico: es lo
#: que el bucle de autocorreccion del studio ya usaba, y subirlo solo
#: gasta racion cuando el problema es que el encargo es imposible.
MAX_PASADAS = 4

_PROPORCIONES = {
    "1:1": 1.0, "16:9": 16 / 9, "9:16": 9 / 16, "4:3": 4 / 3, "3:4": 3 / 4,
}


# ---------------------------------------------------------------- contrato

@dataclass
class Criterio:
    """Una promesa del encargo, con como se comprueba.

    `medible=True` significa que lo decide una maquina y no un modelo. Esa
    distincion es todo el valor del contrato: un criterio medible no
    admite opinion, y un criterio no medible se declara como juzgado por
    lectura, nunca como verificado.
    """

    texto: str
    medible: bool = False
    clave: str = ""          # que se mide: "proporcion", "existe", "no_vacia"
    esperado: str = ""

    def __str__(self) -> str:
        marca = "medible" if self.medible else "leido"
        return f"[{marca}] {self.texto}"


@dataclass
class Encargo:
    """Lo que el usuario pidio, desmenuzado en promesas separables."""

    peticion: str
    criterios: list[Criterio] = field(default_factory=list)
    aspect_ratio: str = "1:1"
    seed: int | None = None

    @classmethod
    def desde_peticion(cls, peticion: str, *, aspect_ratio: str = "1:1",
                       seed: int | None = None) -> "Encargo":
        """Extrae el contrato SIN llamar a ningun modelo.

        Se hace aqui y no preguntandole a una IA porque las promesas
        medibles (proporcion, «sin texto», «vertical») son deterministas:
        pedirselas a un modelo introduce una variable donde no hacia
        falta, y encima gasta racion.
        """
        c = [
            Criterio("el archivo existe y se abre como imagen",
                     medible=True, clave="existe"),
            Criterio("la imagen no esta en blanco ni es un color plano",
                     medible=True, clave="no_vacia"),
            Criterio(f"la proporcion es {aspect_ratio}",
                     medible=True, clave="proporcion", esperado=aspect_ratio),
        ]
        bajo = peticion.lower()
        if "sin texto" in bajo or "no text" in bajo:
            c.append(Criterio("no lleva texto ni letras", medible=False))
        for frase in cls._promesas_del_enunciado(peticion):
            c.append(Criterio(frase, medible=False))
        return cls(peticion=peticion.strip(), criterios=c,
                   aspect_ratio=aspect_ratio, seed=seed)

    @staticmethod
    def _promesas_del_enunciado(peticion: str) -> list[str]:
        """Trocea el enunciado por comas y conjunciones.

        «Un dragon rojo, de noche, sobre una montana nevada» son TRES
        promesas separables, no un tema. Contarlas al empezar es lo que
        permite decir al final cuales quedaron sin cubrir — la primera
        regla del proyecto, aplicada al arte.
        """
        trozos = re.split(r",| y | con | sobre | en la | en el ", peticion)
        return [t.strip() for t in trozos if len(t.strip()) >= 4][:8]

    def texto_contrato(self) -> str:
        return "\n".join(f"{i}. {c}" for i, c in enumerate(self.criterios, 1))


# ---------------------------------------------------------------- piezas

@dataclass
class Propuesta:
    """La lectura del encargo que hace UN autor, y su prompt."""

    autor: str                 # familia: "venice" | "notrack"
    lectura: str               # como entiende el encargo, en sus palabras
    prompt: str                # lo que mandaria a pintar
    ms: float = 0.0
    error: str = ""

    @property
    def util(self) -> bool:
        return bool(self.prompt.strip()) and not self.error


@dataclass
class Medida:
    """Lo que una maquina puede decir del archivo. Sin interpretar."""

    ruta: Path | None = None
    existe: bool = False
    abre: bool = False
    ancho: int = 0
    alto: int = 0
    proporcion: float = 0.0
    entropia: float = 0.0
    no_verificado: list[str] = field(default_factory=list)

    def resumen(self) -> str:
        if not self.existe:
            return "el archivo no existe"
        if not self.abre:
            return f"{self.ruta} existe pero no se abre como imagen"
        return (f"{self.ancho}x{self.alto} px, proporcion "
                f"{self.proporcion:.3f}, entropia {self.entropia:.2f} bits")


@dataclass
class Veredicto:
    """Lo que el critico concluye, con la cuenta que lo sostiene."""

    cumple: bool
    cumplidos: list[str] = field(default_factory=list)
    incumplidos: list[str] = field(default_factory=list)
    no_verificables: list[str] = field(default_factory=list)
    texto: str = ""
    familia: str = ""

    def correccion(self) -> str:
        """Lo que hay que arreglar, en una orden concreta. Vacio si cumple."""
        if self.cumple or not self.incumplidos:
            return ""
        pendientes = "\n".join(f"- {x}" for x in self.incumplidos)
        return ("La version anterior NO cumplio estas promesas del encargo. "
                "Corrige EXACTAMENTE estas y no cambies lo demas:\n"
                f"{pendientes}")


@dataclass
class Obra:
    """El resultado del taller, con todo lo que lo produjo."""

    encargo: Encargo
    ruta: Path | None = None
    propuestas: list[Propuesta] = field(default_factory=list)
    elegida: str = ""
    pasadas: int = 0
    veredictos: list[Veredicto] = field(default_factory=list)
    medida: Medida | None = None
    estado: str = "sin_empezar"       # entregada | no_converge | fallo

    def metadata(self) -> dict:
        """Lo que se guarda junto al artefacto: reproducible y honesto."""
        v = self.veredictos[-1] if self.veredictos else None
        return {
            "peticion": self.encargo.peticion,
            "aspect_ratio": self.encargo.aspect_ratio,
            "seed": self.encargo.seed,
            "contrato": [str(c) for c in self.encargo.criterios],
            "autores": [
                {"autor": p.autor, "lectura": p.lectura[:600],
                 "prompt": p.prompt, "ms": round(p.ms, 1),
                 "error": p.error}
                for p in self.propuestas
            ],
            "prompt_elegido": self.elegida,
            "pasadas": self.pasadas,
            "medida": (self.medida.resumen() if self.medida else ""),
            "veredicto": {
                "cumple": v.cumple if v else None,
                "familia_critico": v.familia if v else "",
                "cumplidos": v.cumplidos if v else [],
                "incumplidos": v.incumplidos if v else [],
                "no_verificables": v.no_verificables if v else [],
            },
            "estado": self.estado,
        }


# ------------------------------------------------------------- el taller

_SISTEMA_AUTOR = (
    "Eres un director de arte. Recibes un encargo y devuelves DOS cosas, "
    "nada mas:\n"
    "LECTURA: en dos frases, que entiendes que se pide, incluyendo lo que "
    "el encargo NO dice y tu decides.\n"
    "PROMPT: una sola linea, en ingles, lista para un generador de "
    "imagenes, que recoja TODAS las promesas del contrato.\n"
    "No expliques nada mas. No inventes promesas que el encargo no hace."
)

_SISTEMA_CRITICO = (
    "Eres el critico del taller. NO creas nada: compruebas.\n"
    "Recibes (a) el contrato del encargo, (b) lo que una maquina MIDIO del "
    "archivo, y (c) el prompt con el que se genero.\n"
    "Para CADA promesa del contrato responde una linea exacta:\n"
    "  CUMPLE <n>: <motivo en una frase>\n"
    "  INCUMPLE <n>: <que falta, concreto y accionable>\n"
    "  NO_VERIFICABLE <n>: <por que no se puede comprobar desde aqui>\n"
    "Reglas duras:\n"
    "- Si una promesa depende de MIRAR la imagen y no tienes la imagen, es "
    "NO_VERIFICABLE. Nunca CUMPLE.\n"
    "- Lo que la maquina midio manda sobre tu opinion.\n"
    "- Se estricto: ante la duda, INCUMPLE. Es preferible una pasada de "
    "mas que entregar algo que no es lo pedido.\n"
    "Termina con una linea 'VEREDICTO: ENTREGABLE' o 'VEREDICTO: REHACER'."
)


class TallerDeArte:
    """Dos autores separados, un critico estricto y un reintento dirigido."""

    def __init__(self, llm, pintor, *, max_pasadas: int = MAX_PASADAS,
                 autores: tuple[str, ...] = AUTORES,
                 familias_critico: tuple[str, ...] = FAMILIA_CRITICO):
        """
        `llm`    objeto con `generate(sistema, usuario, family=..., tag=...)`
                 que devuelve `(texto, proveedor)` — FreeCloudLLM.
        `pintor` corrutina `pintar(prompt, aspect_ratio=..., seed=...)` que
                 devuelve una ruta — normalmente `Venice.imagen`.
        """
        self._llm = llm
        self._pintar = pintor
        self.max_pasadas = max_pasadas
        self.autores = tuple(autores)
        self.familias_critico = tuple(f for f in familias_critico
                                      if f not in self.autores)
        if not self.familias_critico:
            raise ValueError(
                "el critico se ha quedado sin familia propia: todas las "
                "candidatas estan tambien en AUTORES. Un critico que "
                "comparte modelo con el autor no critica, confirma.")

    # ------------------------------------------------------------ autores

    async def propuestas(self, encargo: Encargo) -> list[Propuesta]:
        """Los dos autores, EN PARALELO y sin verse.

        El paralelismo no es por velocidad: es la separacion. Encadenarlos
        obligaria a decidir quien va primero, y el segundo veria —aunque
        fuese en el prompt del sistema— por donde tiro el primero.
        """
        tareas = [self._propuesta(a, encargo) for a in self.autores]
        return list(await asyncio.gather(*tareas))

    async def _propuesta(self, autor: str, encargo: Encargo) -> Propuesta:
        t0 = time.monotonic()
        usuario = (f"ENCARGO: {encargo.peticion}\n\n"
                   f"CONTRATO (cada punto es una promesa separable):\n"
                   f"{encargo.texto_contrato()}\n\n"
                   f"Proporcion obligatoria: {encargo.aspect_ratio}")
        try:
            texto, _prov = await self._llm.generate(
                _SISTEMA_AUTOR, usuario, family=autor,
                tag=f"arte/autor/{autor}")
        except Exception as e:                            # noqa: BLE001
            return Propuesta(autor=autor, lectura="", prompt="",
                             ms=(time.monotonic() - t0) * 1000, error=str(e))
        lectura, prompt = self._parte(texto)
        return Propuesta(autor=autor, lectura=lectura, prompt=prompt,
                         ms=(time.monotonic() - t0) * 1000,
                         error="" if prompt else
                         "el autor no devolvio ninguna linea PROMPT")

    @staticmethod
    def _parte(texto: str) -> tuple[str, str]:
        lectura = prompt = ""
        for linea in (texto or "").splitlines():
            l = linea.strip()
            if l.upper().startswith("LECTURA:"):
                lectura = l.split(":", 1)[1].strip()
            elif l.upper().startswith("PROMPT:"):
                prompt = l.split(":", 1)[1].strip()
        return lectura, prompt

    # -------------------------------------------------------------- medir

    @staticmethod
    def medir(ruta: Path | None, aspect_ratio: str) -> Medida:
        """Lo que se puede saber del archivo sin opinar.

        SIN PILLOW NO SE APRUEBA NADA. Esta es la quinta regla del
        proyecto, y viene de un fallo real: sin Pillow, el observador de
        imagenes devolvia «correcto» sobre una captura que nunca llego a
        abrir. Aqui la ausencia de Pillow se apunta en `no_verificado` y
        el critico la ve; no se convierte en un visto bueno.
        """
        m = Medida(ruta=ruta)
        if ruta is None or not Path(ruta).exists():
            return m
        m.existe = True
        try:
            from PIL import Image
        except ImportError:
            m.no_verificado.append(
                "Pillow no esta instalado: no se han podido comprobar "
                "dimensiones, proporcion ni si la imagen esta en blanco. "
                "Instala pillow para que estas promesas dejen de ser una "
                "suposicion.")
            return m
        try:
            with Image.open(ruta) as im:
                im.load()
                m.abre = True
                m.ancho, m.alto = im.size
                m.proporcion = (m.ancho / m.alto) if m.alto else 0.0
                m.entropia = _entropia(im)
        except Exception as e:                            # noqa: BLE001
            m.no_verificado.append(f"la imagen no se pudo abrir: {e}")
        return m

    @staticmethod
    def comprueba_medibles(encargo: Encargo, m: Medida) -> dict[str, bool | None]:
        """Verdadero, falso o None (no se pudo comprobar) por criterio."""
        salida: dict[str, bool | None] = {}
        for c in encargo.criterios:
            if not c.medible:
                continue
            if c.clave == "existe":
                salida[c.texto] = m.existe and m.abre
            elif c.clave == "no_vacia":
                salida[c.texto] = None if not m.abre else m.entropia > 1.0
            elif c.clave == "proporcion":
                objetivo = _PROPORCIONES.get(c.esperado)
                if not m.abre or objetivo is None:
                    salida[c.texto] = None
                else:
                    salida[c.texto] = abs(m.proporcion - objetivo) <= 0.06
        return salida

    # ------------------------------------------------------------ critico

    async def juzga(self, encargo: Encargo, prompt: str,
                    m: Medida) -> Veredicto:
        medibles = self.comprueba_medibles(encargo, m)
        lineas_maquina = "\n".join(
            f"- {t}: " + ("SI" if v is True else "NO" if v is False
                          else "NO SE PUDO MEDIR")
            for t, v in medibles.items()
        ) or "- (nada medible en este encargo)"
        usuario = (
            f"CONTRATO:\n{encargo.texto_contrato()}\n\n"
            f"MEDIDO POR LA MAQUINA:\n{m.resumen()}\n{lineas_maquina}\n"
            + ("".join(f"\nAVISO: {x}" for x in m.no_verificado))
            + f"\n\nPROMPT USADO:\n{prompt}\n\n"
            "No tienes la imagen delante: no puedes verla."
        )
        texto = ""
        familia_usada = ""
        for fam in self.familias_critico:
            try:
                texto, _prov = await self._llm.generate(
                    _SISTEMA_CRITICO, usuario, family=fam,
                    temperature=0.1, tag="arte/critico")
                familia_usada = fam
                break
            except Exception as e:                        # noqa: BLE001
                logger.warning("[arte] critico %s fallo: %s", fam, e)

        v = self._lee_veredicto(texto, encargo, familia_usada)
        # La maquina manda sobre el modelo. Un criterio medible que salio
        # FALSO es incumplido aunque el critico lo apruebe: el sesgo de
        # complacencia existe y aqui hay un numero que lo desmiente.
        for texto_c, ok in medibles.items():
            if ok is False and texto_c not in v.incumplidos:
                v.incumplidos.append(texto_c)
                v.cumplidos = [x for x in v.cumplidos if x != texto_c]
            elif ok is None and texto_c not in v.no_verificables:
                v.no_verificables.append(texto_c)
                v.cumplidos = [x for x in v.cumplidos if x != texto_c]
        v.cumple = not v.incumplidos and bool(v.cumplidos)
        return v

    @staticmethod
    def _lee_veredicto(texto: str, encargo: Encargo,
                       familia: str) -> Veredicto:
        v = Veredicto(cumple=False, texto=texto or "", familia=familia)
        criterios = encargo.criterios
        for linea in (texto or "").splitlines():
            l = linea.strip()
            mm = re.match(r"^(CUMPLE|INCUMPLE|NO_VERIFICABLE)\s+(\d+)\s*:?(.*)$",
                          l, re.IGNORECASE)
            if not mm:
                continue
            marca, n, _resto = mm.group(1).upper(), int(mm.group(2)), mm.group(3)
            if not (1 <= n <= len(criterios)):
                continue
            t = criterios[n - 1].texto
            destino = {"CUMPLE": v.cumplidos, "INCUMPLE": v.incumplidos,
                       "NO_VERIFICABLE": v.no_verificables}[marca]
            if t not in destino:
                destino.append(t)
        return v

    # -------------------------------------------------------------- ciclo

    async def crear(self, peticion: str, *, aspect_ratio: str = "1:1",
                    seed: int | None = None) -> Obra:
        """Encargo -> dos lecturas -> pintar -> medir -> juzgar -> repetir."""
        encargo = Encargo.desde_peticion(peticion, aspect_ratio=aspect_ratio,
                                         seed=seed)
        obra = Obra(encargo=encargo)
        obra.propuestas = await self.propuestas(encargo)

        utiles = [p for p in obra.propuestas if p.util]
        if not utiles:
            obra.estado = "fallo"
            logger.error("[arte] ningun autor devolvio prompt: %s",
                         [p.error for p in obra.propuestas])
            return obra

        prompt = self._funde(utiles, encargo)
        correccion = ""
        for pasada in range(1, self.max_pasadas + 1):
            obra.pasadas = pasada
            usado = (prompt if not correccion
                     else f"{prompt}\n\n{correccion}")
            try:
                ruta = await self._pintar(usado, aspect_ratio=aspect_ratio,
                                          seed=seed)
            except Exception as e:                        # noqa: BLE001
                obra.estado = "fallo"
                logger.error("[arte] el pincel fallo en la pasada %d: %s",
                             pasada, e)
                return obra
            obra.ruta = Path(ruta)
            obra.elegida = usado
            obra.medida = self.medir(obra.ruta, aspect_ratio)
            veredicto = await self.juzga(encargo, usado, obra.medida)
            obra.veredictos.append(veredicto)
            if veredicto.cumple:
                obra.estado = "entregada"
                return obra
            correccion = veredicto.correccion()
            if not correccion:
                # Sin promesas incumplidas concretas, otra pasada seria la
                # misma pasada. Se para y se dice, en vez de gastar racion
                # repitiendo a ciegas.
                break
        obra.estado = "no_converge"
        return obra

    @staticmethod
    def _funde(utiles: list[Propuesta], encargo: Encargo) -> str:
        """Un prompt con lo que los DOS autores pidieron.

        No se elige uno y se tira el otro: la discrepancia entre dos
        lecturas independientes es informacion, y descartarla desperdicia
        justo lo que se ha pagado con dos llamadas. Se concatenan las dos
        y se deja que el critico cuente promesas sobre el resultado.
        """
        if len(utiles) == 1:
            return utiles[0].prompt
        partes = " | ".join(p.prompt for p in utiles)
        return f"{partes} — aspect ratio {encargo.aspect_ratio}"


def _entropia(im) -> float:
    """Entropia de Shannon del histograma. Un color plano da ~0."""
    try:
        h = im.convert("L").histogram()
    except Exception:                                    # noqa: BLE001
        return 0.0
    total = sum(h) or 1
    return -sum((c / total) * math.log2(c / total) for c in h if c)
