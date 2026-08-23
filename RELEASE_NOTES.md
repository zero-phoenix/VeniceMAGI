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
