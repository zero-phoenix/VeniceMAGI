# VeniceMAGI

La variante de MAGI donde **la única IA es [Venice](https://venice.ai)** —
**sin cuenta, sin clave, sin login**: el modo Guest de la web, manejado por
el enjambre. **v2: ventana propia de aplicación, IDE completa sobre TU
hardware, y la puerta de Edge aparcada fuera de pantalla.**

```
TU PETICIÓN → NAOKO clasifica (Venice)
            → MELCHIOR construye (Venice): ficheros, código, imagen
            → BALTHASAR refuta EJECUTANDO lo construido (Venice)
            → CASPER sintetiza y entrega (Venice)
```

Venice es tesis, antítesis y síntesis a la vez: mismo motor, tres contratos
que se confrontan con evidencia ejecutada.

## Cómo funciona (y por qué la ventana de Edge)

Verificado endpoint a endpoint el 2026-08-16: la API oficial exige clave,
el flujo anónimo legacy está muerto y el FAPI de Clerk pide Turnstile. La
única vía sin credenciales es la que usa tu navegador: **el Guest de la
web**. Y outerface solo atiende al Guest desde un navegador REAL (con
Chromium headless responde 403 por la atestación de cliente).

Por eso VeniceMAGI abre una **ventana de Edge** (el Edge de tu máquina,
perfil propio, nunca tu perfil personal): es literalmente Venice Guest en
tu pantalla, operado por el enjambre. Ahí se escriben los prompts y se
recogen las respuestas e imágenes.

## Lo que puede y lo que no — dicho claro

| Capacidad | Estado |
|---|---|
| Chat (todo el enjambre) | ✅ Guest, verificado E2E |
| Crear ficheros y ejecutar código | ✅ local, sin Venice |
| **Imagen** | ✅ vía chat del Guest (requiere cupo del día) |
| **Vídeo** | ❌ Venice lo reserva a cuentas Pro / clave de API. Naoko lo explica al pedirlo |
| Cupo | El Guest tiene ración **diaria por IP**. Agotada, Venice pide login: el sistema lo dice y no se esquiva |

«Sin raciones nuestras» significa que VeniceMAGI no añade ningún límite
encima de los de Venice; los de Venice se respetan y se explican.

## Tu propia VPN o proxy (opcional)

Si usas una VPN o un proxy en tu máquina, puedes enrutar por él **solo la
ventana del Guest**:

```
/proxy socks5://127.0.0.1:9050     # o http://host:puerto
/proxy off                          # volver a tu red normal
```

Es tu red y tu privacidad, y ahí se queda: VeniceMAGI no instala VPNs, no
rota IPs y no reconecta al agotarse el cupo — la ración diaria del servicio
gratuito se respeta y se explica. Eludirla con rotación de IP te expone a
que Venice bloquee el rango entero de tu proveedor.

## v2.0.0 — de REPL a IDE

- **Ventana propia** (pywebview): hilo del enjambre en vivo con los cuatro
  roles, workspace con árbol y editor, galería de medios, panel de estado
  y cola de trabajo.
- **Puerta aparcada**: el Edge del Guest sigue existiendo (sin él no hay
  sesión sin clave) pero fuera de pantalla; un botón lo muestra si quieres.
- **IDE sobre tu hardware**: read/patch/delete (con papelera + journal),
  run_python con plazo, `hardware_info` (CPU/RAM/GPU/disco), y `shell`
  SOLO con tu aprobación clic a clic en la GUI.
- **Vídeo de planos**: Venice reserva el vídeo AI a Pro; VeniceMAGI genera
  los planos como imágenes y **compone el mp4 en tu PC con ffmpeg**
  (honesto: planos con fundidos, no vídeo AI fluido).
- **Ración diaria visible**: contador de llamadas de hoy y caché LRU para
  que las repeticiones no gasten cupo.

## Uso

```
VeniceMAGI.exe            → abre la ventana de la aplicación
VeniceMAGI.exe --consola  → REPL clásico
crea un script que ordene una carpeta por extensiones     → ronda completa
/imagen una catedral gótica al amanecer                   → PNG en media\
/sesion                                                   → renueva el Guest
/estado  /historial  /refs  /ayuda  /salir
```

- Artefactos: `%LOCALAPPDATA%\VeniceMAGI\workspace` y `...\media`.
- Requisito: **Microsoft Edge** instalado (estándar en Windows).
- Si la sesión Guest caduca a mitad de operación, el sistema reentra solo
  y repite tu petición.

## Desarrollo

```
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m pytest tests/ -q        # 11 tests, sin red
.venv\Scripts\pyinstaller VeniceMAGI.spec --noconfirm
```

Proyecto independiente de MAGI System IDE. Local y privado: nada de GitHub.
