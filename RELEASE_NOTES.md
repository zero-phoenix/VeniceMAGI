# VeniceMAGI v2.0.0 — de REPL a IDE con ventana propia

## Ventana de aplicación

Se acabó la consola: **GUI propia** (pywebview + servidor local) con el
hilo del enjambre en vivo — MELCHIOR, BALTHASAR, CASPER y NAOKO con su
color —, workspace con árbol de ficheros y editor, galería de medios,
panel de estado y cola de trabajo visible.

## El navegador, fuera de la vista (sin cerrarlo)

La ventana de Edge es la puerta de la sesión Guest sin clave — sin ella
no hay acceso gratuito (medido: headless = 403). v2 la **aparca fuera de
pantalla**: el navegador es real, la atestación se resuelve igual, y no
estorba. Un botón la muestra cuando quieras mirar.

## Tu hardware, de verdad

Herramientas nuevas para el enjambre: `read_file`, `list_dir`,
`patch_file` (quirúrgico: exige coincidencia única), `delete_file` (a la
papelera, con journal auditable), `hardware_info` (CPU/RAM/GPU/disco),
`run_python` con plazo, y **`shell` solo con tu aprobación clic a clic**
— la GUI te enseña el comando y tú decides.

## Vídeo de planos (honesto)

Venice reserva el vídeo AI a cuentas Pro. v2 entrega lo máximo que el
Guest permite: el enjambre descompone la escena en planos, Venice genera
las imágenes, y **el mp4 se compone en tu PC con ffmpeg** (fundidos
incluidos). Es un vídeo de planos, no vídeo AI fluido — y así se llama.

## Ración diaria, visible y bien gastada

Contador de llamadas de hoy en el panel de estado y caché LRU: repetir
la misma pregunta ya no gasta ración. El cupo de Venice por IP/día se
respeta (sin rotación de IP) y se explica cuando se agota.

---

# VeniceMAGI v1.1.0 — tu VPN, tú; el resto igual de honesto

## Nuevo: soporte de proxy/VPN propio

`/proxy socks5://127.0.0.1:9050` enruta **solo la ventana del Guest** por
el proxy o VPN que ya tengas en tu máquina (también `VENICE_PROXY` en el
entorno, o `/proxy off` para volver a tu red normal). Es tu red y tu
privacidad — VeniceMAGI no instala VPNs, no rota IPs y no reconecta al
agotarse el cupo: la ración diaria del servicio gratuito se respeta y se
explica, con un test que vigila que ningún mecanismo de evasión entre en
el paquete.

## Lo que es VeniceMAGI

La variante de MAGI donde **la única IA es Venice**, sin cuenta, sin clave
y sin login: el modo Guest de la web (verificado endpoint a endpoint),
operado desde una ventana de Edge con perfil propio.

- **Enjambre completo con un solo motor**: Naoko clasifica, Melchior
  construye (ficheros reales, ejecuta código, imagen), Balthasar refuta
  EJECUTANDO lo construido, Casper sintetiza. Ronda real verificada E2E.
- **Robustez medida**: sesión Guest que caduca → reentrada automática;
  respuestas eco (<40 caracteres útiles) nunca cuentan como respuesta;
  ventana cerrada → mensaje claro; imagen sin llegar → captura
  diagnóstica de la página.
- **Vídeo**: reservado por Venice a cuentas Pro/API; Naoko lo explica.

## Instalación

Descarga `VeniceMAGI-vX.Y.Z.zip`, descomprime y ejecuta `VeniceMAGI.exe`.
Requisito: Microsoft Edge. Verifica la descarga contra `CHECKSUMS.txt`
(`certutil -hashfile <zip> SHA256`).
