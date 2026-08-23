/* VeniceMAGI GUI — polling local: simple a propósito. */
"use strict";

let ultimoEvento = 0;
let edRuta = "";

const $ = (id) => document.getElementById(id);

async function api(ruta, cuerpo) {
  const r = await fetch(ruta, cuerpo
    ? { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cuerpo) }
    : undefined);
  return r.json();
}

/* ------------------------------------------------------------- eventos */

async function tick() {
  try {
    const d = await api(`/api/eventos?desde=${ultimoEvento}`);
    (d.eventos || []).forEach(pintaEvento);
    ultimoEvento = d.eventos && d.eventos.length
      ? d.eventos[d.eventos.length - 1].id : ultimoEvento;
    $("estado-chip").textContent = d.trabajando ? "trabajando…" : "en espera";
  } catch { /* el servidor puede reiniciarse */ }
  await Promise.all([estado(), aprobaciones()]);
}

function pintaEvento(e) {
  if (e.tipo === "ronda_empieza") {
    msg("SYS", "(ronda: " + e.peticion.slice(0, 120) + ")");
  } else if (e.tipo === "ronda_fin") {
    if (e.tesis) msg("MELCHIOR", e.tesis);
    if (e.antitesis) msg("BALTHASAR", e.antitesis);
    if (e.nota) msg("NAOKO", e.nota);
    msg("CASPER", e.sintesis || "(sin síntesis)");
    if (e.artefactos && e.artefactos.length)
      msg("SYS", "artefactos:\n  " + e.artefactos.join("\n  "));
    medios(); arbolWs();
  } else if (e.tipo === "ronda_error") {
    msg("NAOKO", e.mensaje);
  } else if (e.tipo === "medio_nuevo") {
    msg("SYS", (e.tipo_medio || e.tipo2 || "medio") + " listo: " + e.ruta);
    medios();
  } else if (e.tipo === "estado") {
    msg("SYS", e.mensaje);
  }
}

function msg(quien, texto) {
  const d = document.createElement("div");
  d.className = "msg " + (quien === "tú" ? "user" : "");
  const color = quien === "tú" ? "SYS" : quien;
  d.innerHTML = `<div class="quien ${color}">[${quien}]</div>
                 <div class="cuerpo"></div>`;
  d.querySelector(".cuerpo").textContent = texto;
  $("hilo").appendChild(d);
  $("hilo").scrollTop = $("hilo").scrollHeight;
}

/* ------------------------------------------------------------ entrada */

function enviar() {
  const t = $("pet").value.trim();
  if (!t) return;
  $("pet").value = "";
  msg("tú", t);
  api("/api/peticion", { texto: t });
}
function prefijo(p) { $("pet").value = p + $("pet").value; $("pet").focus(); }
$("pet").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(); }
});

/* -------------------------------------------------------- aprobaciones */

async function aprobaciones() {
  const d = await api("/api/aprobaciones");
  const p = (d.pendientes || [])[0];
  $("aprobaciones").classList.toggle("oculto", !p);
  if (p) $("ap-cmd").textContent = p.cmd;
}
async function aprobar(ok) {
  const d = await api("/api/aprobaciones");
  const p = (d.pendientes || [])[0];
  if (p) await api("/api/aprobar", { id: p.id, ok });
  $("aprobaciones").classList.add("oculto");
  msg("SYS", p ? (ok ? "shell APROBADA: " + p.cmd
                     : "shell rechazada") : "");
}

/* ------------------------------------------------------ estado/toggles */

async function estado() {
  const d = await api("/api/estado");
  $("estado").innerHTML =
    `<b>versión</b> ${d.version}<br>` +
    `<b>llamadas hoy</b> ${d.llamadas_hoy} (ración Venice por IP/día)<br>` +
    `<b>cola</b> ${d.cola} · <b>${d.trabajando ? "trabajando" : "en espera"}</b><br>` +
    `<b>puerta</b> ${d.puerta_visible ? "visible" : "aparcada (off-screen)"}<br>` +
    `<b>proxy</b> ${d.proxy || "(ninguno)"}<br>` +
    `<b>shell</b> ${d.permitir_shell ? "permitida (pide aprobar cada comando)"
                                      : "bloqueada"}`;
  $("btn-puerta").textContent = "puerta: " +
    (d.puerta_visible ? "visible" : "aparcada");
  $("btn-shell").textContent = "shell: " +
    (d.permitir_shell ? "on" : "off");
}
async function togglePuerta() {
  const d = await api("/api/estado");
  await api("/api/puerta", { visible: !d.puerta_visible });
  msg("SYS", "puerta " + (!d.puerta_visible
    ? "visible (se reabrirá a la próxima)"
    : "aparcada (se reabrirá a la próxima)"));
}
async function toggleShell() {
  const d = await api("/api/estado");
  await api("/api/shell", { permitir: !d.permitir_shell });
  estado();
}

/* ---------------------------------------------------- workspace/medios */

function pintaNodo(n, cont) {
  const d = document.createElement("div");
  d.className = "n" + (n.dir ? " dir" : "");
  d.textContent = (n.dir ? "▸ " : "  ") + n.nombre;
  if (!n.dir) d.onclick = () => abreFichero(n.ruta);
  cont.appendChild(d);
  if (n.hijos) n.hijos.forEach((h) => pintaNodo(h, cont));
}
async function arbolWs() {
  const d = await api("/api/workspace");
  $("arbol").innerHTML = "";
  pintaNodo(d, $("arbol"));
}
async function abreFichero(ruta) {
  const d = await api("/api/fichero?ruta=" + encodeURIComponent(ruta));
  if (d.error) return;
  edRuta = ruta;
  $("ed-ruta").textContent = ruta;
  $("editor").value = d.contenido;
}
async function guardarFichero() {
  if (!edRuta) return;
  const d = await api("/api/guardar_fichero",
    { ruta: edRuta, contenido: $("editor").value });
  msg("SYS", d.ok ? "guardado: " + edRuta : "error al guardar");
}
async function medios() {
  const d = await api("/api/medios");
  $("galeria").innerHTML = "";
  (d.medios || []).forEach((m) => {
    const el = document.createElement(
      m.tipo === "video" ? "video" : "img");
    if (m.tipo === "video") { el.controls = true; el.src = "file:///" +
      m.ruta.replace(/\\/g, "/"); }
    else el.src = "file:///" + m.ruta.replace(/\\/g, "/");
    el.title = m.nombre;
    $("galeria").appendChild(el);
  });
}

/* historial viejo al abrir */
async function historial() {
  const d = await api("/api/historial?n=5");
  if ((d.filas || []).length)
    msg("SYS", "historial reciente:\n" +
      d.filas.map((f) => "  · " + f.peticion.slice(0, 70)).join("\n"));
}

tick(); arbolWs(); medios(); historial();
setInterval(tick, 800);
