/* Explorador Modbus TCP · Taller 5 · prácticas 1a y 1b · ot-lab (UCuenca) */
'use strict';
const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
const NS = 'http://www.w3.org/2000/svg';
const TABLE_INFO = {
  di:    { y: 149, name: 'Discrete inputs',   sub: '1x · FC 02 · lectura',   fcs: [2] },
  coils: { y: 229, name: 'Coils',             sub: '0x · FC 01 · 05 · 15',   fcs: [1, 5, 15] },
  ir:    { y: 309, name: 'Input registers',   sub: '3x · FC 04 · lectura',   fcs: [4] },
  hr:    { y: 389, name: 'Holding registers', sub: '4x · FC 03 · 06 · 16',   fcs: [3, 6, 16] },
};
const FC_TABLE = { 1: 'coils', 2: 'di', 3: 'hr', 4: 'ir', 5: 'coils', 6: 'hr', 15: 'coils', 16: 'hr' };
const FC_WRITE = new Set([5, 6, 15, 16]);
const dec = (v, d = 1) => (v / 10).toFixed(d).replace('.', ',');
const i16 = v => (v > 32767 ? v - 65536 : v);

/* ------------------------------------------------------------------ tableros (láminas 21, 30 y 31) */
const TABLEROS = {
  lam31: {
    label: 'Lámina 31 · 4 medidas y 5 parámetros (registros)',
    left: 'CAMPO · 4 MEDIDAS', right: '5 PARÁMETROS · HOLDING',
    inputs: [
      { table: 'ir', addr: 0, name: 'Temperatura', icon: 'thermo', fmt: v => `${v} = ${dec(v)}°C` },
      { table: 'ir', addr: 1, name: 'Humedad',     icon: 'drop',   fmt: v => `${v} = ${dec(v)} %` },
      { table: 'ir', addr: 2, name: 'CO₂',         icon: 'co2',    fmt: v => `${v} ppm` },
      { table: 'ir', addr: 3, name: 'Presión',     icon: 'gauge',  fmt: v => `${v} hPa` },
    ],
    outputs: [
      { table: 'hr', addr: 0, name: 'Consigna T',   icon: 'knob', fmt: v => `${v} = ${dec(v)}°C` },
      { table: 'hr', addr: 1, name: 'Consigna HR',  icon: 'knob', fmt: v => `${v} = ${dec(v)} %` },
      { table: 'hr', addr: 2, name: 'Umbral CO₂',   icon: 'bell', fmt: v => `${v} ppm` },
      { table: 'hr', addr: 3, name: 'Ventilador %', icon: 'fan',  fmt: v => `${v} %` },
      { table: 'hr', addr: 4, name: 'Modo',         icon: 'knob', fmt: v => `${v} ${v ? '(auto)' : '(manual)'}` },
    ],
    json: `"inputRegister":   { "1": 235, "2": 480, "3": 612, "4": 1013 },
"holdingRegister": { "1": 260, "2": 500, "3": 800,
                     "4": 40,  "5": 0 }`,
    steps: [
      { t: '<b>FC 04</b> · las 4 medidas en una petición · <code>count=4</code>. Respuesta: 1 + 1 + 2·4 bytes', op: { read: 'ir', addr: 0, count: 4 } },
      { t: '<b>FC 03</b> · los 5 parámetros de una vez · <code>count=5</code>', op: { read: 'hr', addr: 0, count: 5 } },
      { t: '<b>FC 06</b> · solo el ventilador a 75 % (HR 3)', op: { write: 'register', addr: 3, val: '75' } },
      { t: '<b>FC 16</b> · «modo verano» en una sola trama desde HR 0 → <code>[240, 550, 1000, 60, 1]</code> · 10 bytes de datos, PDU 16', op: { write: 'registers', addr: 0, val: '240,550,1000,60,1' } },
      { t: '<code>write_register(2, 70000)</code> · ¿quién se queja?', op: { write: 'register', addr: 2, val: '70000' } },
      { t: '<code>write_register(0, -5)</code> · ¿y ahora?', op: { write: 'register', addr: 0, val: '-5' } },
      { t: '5 valores desde HR 3 (desborda a HR 7) · ¿excepción 02 o <code>initializeUndefinedRegisters</code>?', op: { write: 'registers', addr: 3, val: '60,1,0,0,0' } },
      { t: 'Releer los 5 parámetros · ¿qué quedó?', op: { read: 'hr', addr: 0, count: 5 } },
    ],
  },
  lam30: {
    label: 'Lámina 30 · 4 entradas y 5 salidas (bits)',
    left: 'CAMPO · 4 PULSADORES / SENSORES', right: '5 SALIDAS · COILS',
    inputs: [
      { table: 'di', addr: 0, name: 'Marcha',     icon: 'button', fmt: b => b ? '1 pulsado' : '0' },
      { table: 'di', addr: 1, name: 'Paro',       icon: 'button', fmt: b => b ? '1 pulsado' : '0' },
      { table: 'di', addr: 2, name: 'Emergencia', icon: 'button', fmt: b => b ? '1 pulsado' : '0' },
      { table: 'di', addr: 3, name: 'Puerta',     icon: 'door',   fmt: b => b ? '1 abierta' : '0 cerrada' },
    ],
    outputs: [
      { table: 'coils', addr: 0, name: 'LED verde',  icon: 'led',   fmt: b => b ? '1 encendido' : '0 apagado' },
      { table: 'coils', addr: 1, name: 'LED rojo',   icon: 'led',   fmt: b => b ? '1 encendido' : '0 apagado' },
      { table: 'coils', addr: 2, name: 'Ventilador', icon: 'fan',   fmt: b => b ? '1 encendido' : '0 apagado' },
      { table: 'coils', addr: 3, name: 'Bomba',      icon: 'pump',  fmt: b => b ? '1 marcha' : '0 parada' },
      { table: 'coils', addr: 4, name: 'Sirena',     icon: 'siren', fmt: b => b ? '1 sonando' : '0' },
    ],
    json: `"discreteInput": { "1": true, "2": false, "3": false, "4": true },
"coils":         { "1": true, "2": false, "3": false, "4": false, "5": false }`,
    steps: [
      { t: '<b>FC 02</b> · las 4 entradas en una petición · byte esperado: bits 1001', op: { read: 'di', addr: 0, count: 4 } },
      { t: '<b>FC 01</b> · los 5 coils de una vez · estado inicial', op: { read: 'coils', addr: 0, count: 5 } },
      { t: '<b>FC 05</b> · arrancar la bomba (coil 3) sin tocar nada más', op: { write: 'coil', addr: 3, val: 'T' } },
      { t: '<b>FC 15</b> · parada de emergencia en una trama: verde OFF, rojo ON, ventilador ON, bomba OFF, sirena ON · byte 10110', op: { write: 'coils', addr: 0, val: 'F,T,T,F,T' } },
      { t: 'Releer los 5 coils · comprobar', op: { read: 'coils', addr: 0, count: 5 } },
    ],
  },
  lam21: {
    label: 'Lámina 21 · PLC del ejemplo (pulsador, LED, ventilador, T, CO₂)',
    left: 'CAMPO · ENTRADAS', right: 'SALIDAS Y PARÁMETROS',
    inputs: [
      { table: 'di', addr: 0, name: 'Pulsador',    icon: 'button', fmt: b => b ? '1 pulsado' : '0' },
      { table: 'ir', addr: 0, name: 'Temperatura', icon: 'thermo', fmt: v => `${v} = ${dec(v)}°C` },
      { table: 'ir', addr: 1, name: 'CO₂',         icon: 'co2',    fmt: v => `${v} ppm` },
    ],
    outputs: [
      { table: 'coils', addr: 0, name: 'LED',        icon: 'led',  fmt: b => b ? '1 encendido' : '0 apagado' },
      { table: 'coils', addr: 1, name: 'Ventilador', icon: 'fan',  fmt: b => b ? '1 encendido' : '0 apagado' },
      { table: 'hr',    addr: 0, name: 'Consigna',   icon: 'knob', fmt: v => `${v} = ${dec(v)}°C` },
      { table: 'hr',    addr: 1, name: 'Umbral CO₂', icon: 'bell', fmt: v => `${v} ppm` },
    ],
    json: `"discreteInput":   { "1": true },
"coils":           { "1": false, "2": false },
"inputRegister":   { "1": 235, "2": 612 },
"holdingRegister": { "1": 260, "2": 800 }`,
    steps: [
      { t: '<b>FC 02</b> · el pulsador', op: { read: 'di', addr: 0, count: 1 } },
      { t: '<b>FC 01</b> · LED y ventilador', op: { read: 'coils', addr: 0, count: 2 } },
      { t: '<b>FC 05</b> · LED ON', op: { write: 'coil', addr: 0, val: 'T' } },
      { t: '<b>FC 15</b> · LED y ventilador a la vez (lámina 23)', op: { write: 'coils', addr: 0, val: 'T,T' } },
      { t: '<b>FC 04</b> · temperatura y CO₂', op: { read: 'ir', addr: 0, count: 2 } },
      { t: '<b>FC 03</b> · consigna y umbral', op: { read: 'hr', addr: 0, count: 2 } },
      { t: '<b>FC 06</b> · consigna 28,0 °C', op: { write: 'register', addr: 0, val: '280' } },
      { t: '<b>FC 16</b> · consigna y umbral en una trama', op: { write: 'registers', addr: 0, val: '280,1000' } },
    ],
  },
};
const STEPS_1B = [
  { t: '<b>FC 02</b> · %IX100.0–.1 (pulsador que el PLC trajo del simulador)', op: { read: 'di', addr: 800, count: 2 }, target: 'openplc' },
  { t: '<b>FC 01</b> · %QX100.0–.1 (LED y ventilador que el programa calcula)', op: { read: 'coils', addr: 800, count: 2 }, target: 'openplc' },
  { t: '<b>FC 04</b> · %IW100–103 (temperatura, CO₂, consigna, umbral)', op: { read: 'ir', addr: 100, count: 4 }, target: 'openplc' },
  { t: '<b>FC 03</b> · %QW100–101 (lo que el PLC escribiría si HR-Write &gt; 0)', op: { read: 'hr', addr: 100, count: 2 }, target: 'openplc' },
  { t: '<b>FC 01</b> · %QX0.0–.7 · salidas propias del PLC (coils 0–7)', op: { read: 'coils', addr: 0, count: 8 }, target: 'openplc' },
];

/* ------------------------------------------------------------------ estado */
const S = { tablero: 'lam31', vals: { di: {}, coils: {}, ir: {}, hr: {} }, items: [], log: [], targets: [], session: {}, poll: null, mon: null, capTimer: null };

/* ------------------------------------------------------------------ utilidades */
async function api(path, body, method) {
  const r = await fetch(path, { method: method || (body ? 'POST' : 'GET'), headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || `${r.status} ${r.statusText}`);
  return j;
}
let toastT;
function toast(msg, bad) { const t = $('#toast'); t.textContent = msg; t.className = 'toast' + (bad ? ' bad' : ''); clearTimeout(toastT); toastT = setTimeout(() => t.classList.add('hidden'), bad ? 5200 : 2800); }
function busy(btn, on) { if (!btn) return; btn.classList.toggle('busy', on); btn.disabled = !!on; }
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
function el(tag, attrs, text) { const e = document.createElementNS(NS, tag); for (const k in attrs || {}) e.setAttribute(k, attrs[k]); if (text != null) e.textContent = text; return e; }

/* ------------------------------------------------------------------ tablero SVG */
function icon(kind, x, y) {
  const g = el('g', { class: 'ico-g' });
  const add = (t, a) => { const e = el(t, a); g.appendChild(e); return e; };
  switch (kind) {
    case 'thermo': add('rect', { class: 'ico', x: x + 18, y: y + 15, width: 14, height: 34, rx: 7 }); add('circle', { class: 'ico on', cx: x + 25, cy: y + 57, r: 10 }); break;
    case 'drop': add('path', { class: 'ico', d: `M${x + 25} ${y + 17} C ${x + 47} ${y + 43}, ${x + 41} ${y + 63}, ${x + 25} ${y + 63} C ${x + 9} ${y + 63}, ${x + 3} ${y + 43}, ${x + 25} ${y + 17} Z` }); break;
    case 'co2': add('circle', { class: 'ico', cx: x + 25, cy: y + 41, r: 23 }); add('text', { x: x + 25, y: y + 48, 'text-anchor': 'middle', style: 'font-size:18px;font-weight:700;fill:#002856' }, 'CO₂'); break;
    case 'gauge': add('path', { class: 'ico', d: `M${x + 1} ${y + 51} A 24 24 0 0 1 ${x + 49} ${y + 51}` }); add('line', { class: 'ico', x1: x + 25, y1: y + 51, x2: x + 37, y2: y + 31 }); add('circle', { class: 'ico on', cx: x + 25, cy: y + 51, r: 4 }); break;
    case 'knob': add('rect', { class: 'ico', x: x + 1, y: y + 27, width: 48, height: 28, rx: 6 }); add('circle', { class: 'ico on knobdot', cx: x + 33, cy: y + 41, r: 8 }); break;
    case 'bell': add('path', { class: 'ico', d: `M${x + 9} ${y + 33} L${x + 9} ${y + 21} Q${x + 9} ${y + 3} ${x + 25} ${y + 3} Q${x + 41} ${y + 3} ${x + 41} ${y + 21} L${x + 41} ${y + 33} Z`, transform: `translate(0 14)` }); add('line', { class: 'ico', x1: x + 3, y1: y + 47, x2: x + 47, y2: y + 47 }); add('circle', { class: 'ico', cx: x + 25, cy: y + 55, r: 5 }); break;
    case 'fan': { const f = el('g', { class: 'fan' }); const cx = x + 25, cy = y + 41; f.appendChild(el('circle', { class: 'ico', cx, cy, r: 24 })); [0, 120, 240].forEach(a => f.appendChild(el('ellipse', { class: 'ico', cx, cy: cy - 14, rx: 7, ry: 14, transform: `rotate(${a} ${cx} ${cy})` }))); g.appendChild(f); break; }
    case 'led': add('circle', { class: 'ico led', cx: x + 25, cy: y + 41, r: 16 }); add('line', { class: 'ico', x1: x + 25, y1: y + 60, x2: x + 25, y2: y + 70 }); break;
    case 'button': add('circle', { class: 'ico', cx: x + 25, cy: y + 41, r: 20 }); add('circle', { class: 'ico led', cx: x + 25, cy: y + 41, r: 10 }); break;
    case 'door': add('rect', { class: 'ico', x: x + 9, y: y + 15, width: 32, height: 52, rx: 3 }); add('circle', { class: 'ico led', cx: x + 33, cy: y + 42, r: 3 }); break;
    case 'pump': add('circle', { class: 'ico', cx: x + 25, cy: y + 41, r: 20 }); add('path', { class: 'ico', d: `M${x + 25} ${y + 21} L${x + 25} ${y + 41} L${x + 41} ${y + 41}` }); add('rect', { class: 'ico', x: x + 3, y: y + 61, width: 44, height: 8 }); break;
    case 'siren': add('path', { class: 'ico', d: `M${x + 7} ${y + 59} A 18 18 0 0 1 ${x + 43} ${y + 59} Z` }); add('rect', { class: 'ico', x: x + 3, y: y + 59, width: 44, height: 8, rx: 2 }); add('path', { class: 'ico led', d: `M${x + 25} ${y + 15} L${x + 25} ${y + 25} M${x + 8} ${y + 24} L${x + 14} ${y + 30} M${x + 42} ${y + 24} L${x + 36} ${y + 30}` }); break;
  }
  return g;
}
function pathStr(x1, y1, x2, y2) { return `M${x1} ${y1} C ${x1 + 40} ${y1}, ${x2 - 40} ${y2}, ${x2} ${y2}`; }
function buildTablero() {
  const T = TABLEROS[S.tablero];
  const st = $('#dg-static'), cards = $('#dg-cards');
  st.innerHTML = ''; cards.innerHTML = ''; $('#dg-fx').innerHTML = '';
  st.appendChild(el('text', { class: 'ro', x: 0, y: 30 }, T.left));
  st.appendChild(el('text', { class: 'ro', x: 600, y: 30 }, T.right));
  st.appendChild(el('rect', { class: 'plc', x: 300, y: 44, width: 260, height: 452, rx: 10 }));
  st.appendChild(el('text', { class: 'tt', x: 430, y: 80, 'text-anchor': 'middle' }, 'PLC · esclavo'));
  st.appendChild(el('text', { class: 'ts', x: 430, y: 103, 'text-anchor': 'middle', id: 'dg-plc-sub' }, '— · unit —'));
  const used = new Set([...T.inputs, ...T.outputs].map(i => i.table));
  for (const [k, inf] of Object.entries(TABLE_INFO)) {
    const off = used.has(k) ? '' : ' off';
    st.appendChild(el('rect', { class: 'row' + off, id: 'row-' + k, x: 312, y: inf.y - 31, width: 236, height: 62, rx: 6 }));
    st.appendChild(el('text', { class: 'rt' + off, x: 324, y: inf.y - 5 }, inf.name));
    st.appendChild(el('text', { class: 'rs', x: 324, y: inf.y + 19 }, inf.sub));
  }
  S.items = [];
  const place = (list, x, isOut) => {
    const pitch = list.length > 4 ? 92 : 112;
    list.forEach((it, i) => {
      const y = 40 + i * pitch, cy = y + 41;
      const ry = TABLE_INFO[it.table].y;
      it.pIn = isOut ? pathStr(560, ry, 600, cy) : pathStr(270, cy, 300, ry);       // sentido de la flecha dibujada
      it.pRead = isOut ? pathStr(600, cy, 560, ry) : it.pIn;                        // lectura: tarjeta → PLC
      it.pWrite = isOut ? it.pIn : pathStr(300, ry, 270, cy);                        // escritura: PLC → tarjeta
      st.appendChild(el('path', { class: 'ln' + (isOut ? ' w' : ''), d: it.pIn }));
      const g = el('g', { class: 'item', id: `it-${it.table}-${it.addr}` });
      g.appendChild(el('rect', { class: 'card', x, y, width: 270, height: 82, rx: 8 }));
      g.appendChild(icon(it.icon, x + 8, y));
      g.appendChild(el('text', { class: 'nm2', x: x + 66, y: y + 34 }, it.name));
      g.appendChild(el('text', { class: 'ch', x: x + 66, y: y + 64 }, `${{ di: 'DI', coils: 'coil', ir: 'IR', hr: 'HR' }[it.table]} ${it.addr}`));
      const tv = el('text', { class: 'st2', x: x + 150, y: y + 64 }); tv.appendChild(el('tspan', { class: 'b' }, '—')); g.appendChild(tv);
      g.appendChild(el('text', { class: 'ty', x: x + 66, y: y + 80 }, `clave JSON "${it.addr + 1}" · ${{ di: 1, coils: 0, ir: 3, hr: 4 }[it.table]}${String(it.addr + 1).padStart(4, '0')}`));
      it.g = g; it.tv = tv; it.shown = undefined;
      cards.appendChild(g); S.items.push(it);
    });
  };
  place(T.inputs, 0, false); place(T.outputs, 600, true);
  S.items.forEach(refreshCard);
  updatePlcSub();
  renderSteps('#steps', T.steps);
  $('#json-snippet').textContent = T.json;
}
function updatePlcSub() { const s = S.session; const t = $('#dg-plc-sub'); if (t) t.textContent = s.connected ? `${s.host}:${s.port} · unit ${s.unit}` : 'sin conexión'; $('#dg-target').textContent = s.connected ? `${s.host}:${s.port} · unit ${s.unit}` : 'sin conexión'; }
function refreshCard(it, mode) {
  const v = S.vals[it.table][it.addr];
  it.tv.innerHTML = '';
  if (v === undefined) { it.tv.appendChild(el('tspan', { class: 'b' }, '—')); return; }
  const txt = it.fmt(v);
  if (it.shown !== undefined && it.shown !== v && mode === 'w') {
    const raw = x => typeof x === 'boolean' ? (x ? '1' : '0') : String(x);
    it.tv.appendChild(el('tspan', { class: 'b' }, raw(it.shown)));
    it.tv.appendChild(el('tspan', {}, ' → '));
    it.tv.appendChild(el('tspan', { class: 'on' }, raw(v) + (typeof v === 'boolean' ? '' : '')));
  } else it.tv.appendChild(el('tspan', { class: 'b' }, txt));
  it.shown = v;
  const on = typeof v === 'boolean' ? v : v > 0;
  it.g.querySelectorAll('.led').forEach(e => e.classList.toggle('lit', on));
  it.g.querySelectorAll('.fan').forEach(e => e.classList.toggle('spin', on));
  it.g.querySelectorAll('.knobdot').forEach(e => e.setAttribute('cx', on ? e.getAttribute('cx') : e.getAttribute('cx')));
}
function flashRow(table, write) { const r = $('#row-' + table); if (!r) return; r.classList.add(write ? 'hot' : 'hotr'); setTimeout(() => r.classList.remove('hot', 'hotr'), 700); }
function packet(path, write, label, delay) {
  const fx = $('#dg-fx');
  const g = el('g', { class: 'pkt' + (write ? ' w' : '') });
  g.appendChild(el('circle', { r: 11, class: 'pkt' + (write ? ' w' : '') }));
  g.appendChild(el('text', { 'text-anchor': 'middle', y: 5 }, label));
  const am = el('animateMotion', { dur: '0.55s', begin: 'indefinite', fill: 'freeze', path, calcMode: 'spline', keySplines: '.3 0 .3 1', keyTimes: '0;1', keyPoints: '0;1' });
  g.appendChild(am); fx.appendChild(g);
  setTimeout(() => { am.beginElement(); }, delay || 0);
  setTimeout(() => g.remove(), 700 + (delay || 0));
}
function animate(fc, addr, count, ok) {
  const table = FC_TABLE[fc], write = FC_WRITE.has(fc);
  const touched = S.items.filter(it => it.table === table && it.addr >= addr && it.addr < addr + count);
  flashRow(table, write);
  touched.forEach((it, i) => {
    packet(write ? it.pWrite : it.pRead, write, String(fc).padStart(2, '0'), i * 60);
    setTimeout(() => {
      it.g.classList.remove('flash-r', 'flash-w', 'err');
      it.g.classList.add(ok ? (write ? 'flash-w' : 'flash-r') : 'err');
      refreshCard(it, write ? 'w' : 'r');
      setTimeout(() => it.g.classList.remove('flash-r', 'flash-w'), 900);
      if (!ok) setTimeout(() => it.g.classList.remove('err'), 1800);
    }, 520 + i * 60);
  });
}

/* ------------------------------------------------------------------ tramas y tabla */
function bytesHtml(frame) {
  if (!frame) return '<span class="gr">— sin trama (pymodbus no llegó a enviar nada)</span>';
  let h = frame.mbap ? `<span class="by mbap" title="MBAP · Transaction ${frame.mbap.transaction_id} · Protocol 0 · Length ${frame.mbap.length} · Unit ${frame.mbap.unit_id}">${frame.mbap.hex}</span>` : '';
  (frame.fields || []).forEach(f => {
    const cls = f.name === 'FC' ? 'fc' : (f.name.startsWith('Data') ? 'data' : (f.name === 'Exception Code' ? 'exc' : ''));
    if (f.hex) h += `<span class="by ${cls}" title="${esc(f.name)}">${esc(f.hex)}</span>`;
  });
  let rows = (frame.fields || []).map(f => `<tr><td>${esc(f.name)}</td><td class="hx">${esc(f.hex)}</td><td>${esc(Array.isArray(f.value) ? '[' + f.value.join(', ') + ']' : f.value)}</td></tr>`).join('');
  const dataBytes = (frame.fields || []).filter(f => f.name.startsWith('Data')).reduce((a, f) => a + (f.hex ? f.hex.split(' ').length : 0), 0);
  const tot = frame.mbap ? `ADU ${frame.len} bytes = MBAP 7 + PDU ${frame.pdu.len}${dataBytes ? ` · datos ${dataBytes} bytes` : ''} · Transaction Id ${frame.mbap.transaction_id}` : '';
  return `<div class="bytes">${h}</div><table>${rows}</table><div class="tot">${tot}</div>`;
}
function showOp(res) {
  const q = res.frames.find(f => f.dir === 'query'), r = res.frames.find(f => f.dir === 'response');
  $('#pyline').innerHTML = `&gt;&gt;&gt; ${esc(res.pymodbus)}` + (res.ok ? `\n<span class="c"># ${esc(valueText(res))}</span>` : '');
  const b = $('#op-banner'); b.className = 'banner hidden';
  if (res.error) { b.className = 'banner'; b.innerHTML = `<b>Se quejó pymodbus, no el esclavo:</b> ${esc(res.error)}. No viajó ninguna trama.`; }
  else if (res.exception) { b.className = 'banner'; b.innerHTML = `<b>Excepción del esclavo:</b> FC ${res.fc} + 128 = 0x${(res.fc + 128).toString(16)} · código ${String(res.exception.code).padStart(2, '0')} ${esc(res.exception.name)}. Modbus no valida nada: el esclavo responde con la excepción y la Query viajó igual.`; }
  else if (!res.ok && !res.frames.length) { b.className = 'banner'; b.innerHTML = '<b>Sin respuesta</b> del esclavo (timeout). ¿Está arriba? ¿Puerto correcto?'; }
  $('#op-meta').textContent = `${res.fc_name} (FC ${String(res.fc).padStart(2, '0')}) · ${res.elapsed_ms} ms`;
  $('#frame-query .fbody').innerHTML = bytesHtml(q);
  $('#frame-response .fbody').innerHTML = r ? bytesHtml(r) : (q ? '<span class="gr">— sin Response (timeout)</span>' : '<span class="gr">—</span>');
}
function valueText(res) {
  if (res.error) return 'ERROR pymodbus';
  if (res.exception) return `Exception ${String(res.exception.code).padStart(2, '0')} ${res.exception.name}`;
  if (Array.isArray(res.values)) return '[' + res.values.map(v => typeof v === 'boolean' ? (v ? 'True' : 'False') : v).join(', ') + ']';
  return res.values == null ? '—' : String(res.values);
}
function logOp(res, addr) {
  const q = res.frames.find(f => f.dir === 'query'), r = res.frames.find(f => f.dir === 'response');
  const row = { n: res.seq, hora: new Date().toLocaleTimeString('es-EC', { hour12: false }), fc: res.fc, nombre: res.fc_name, dir: addr,
    datos: res.error ? '—' : (res.exception ? 'Response (excepción)' : (FC_WRITE.has(res.fc) ? 'Query' : 'Response')),
    pq: q ? q.pdu.hex : '—', pr: r ? r.pdu.hex : '—', valor: valueText(res), ms: res.elapsed_ms, bad: !res.ok };
  S.log.push(row); if (S.log.length > 300) S.log.shift();
  const tb = $('#log tbody');
  const tr = document.createElement('tr'); tr.className = 'new' + (row.bad ? ' err' : '');
  tr.innerHTML = `<td>${row.n}</td><td class="mono">${row.hora}</td><td class="mono">${String(row.fc).padStart(2, '0')}</td><td>${esc(row.nombre)}</td><td class="mono">${row.dir}</td><td>${row.datos}</td><td class="mono">${esc(row.pq)}</td><td class="mono">${esc(row.pr)}</td><td class="mono">${esc(row.valor)}</td><td class="mono">${row.ms}</td>`;
  tb.prepend(tr); while (tb.children.length > 300) tb.lastChild.remove();
}

/* ------------------------------------------------------------------ ejecutar operaciones */
function parseVals(txt, bits) {
  return txt.split(/[,;\s]+/).filter(Boolean).map(v => bits ? /^(1|t|true|on|v|si|sí)$/i.test(v) : (v.trim()));
}
async function runOp(op, btn) {
  if (!S.session.connected) { toast('Primero conecte con el esclavo (pestaña 1a · Sesión).', true); return null; }
  busy(btn, true);
  try {
    let res, addr = op.addr, count = 1;
    if (op.read) { count = op.count; res = await api('/api/read', { table: op.read, address: addr, count }); }
    else {
      const bits = op.write === 'coil' || op.write === 'coils';
      const multi = op.write === 'coils' || op.write === 'registers';
      const vals = parseVals(op.val, bits);
      if (!vals.length) throw new Error('Indique un valor.');
      const body = { kind: op.write, address: addr };
      if (multi) body.values = vals; else body.value = vals[0];
      count = multi ? vals.length : 1;
      res = await api('/api/write', body);
    }
    showOp(res); logOp(res, addr);
    if (res.ok) {
      if (op.read) res.values.forEach((v, i) => { S.vals[op.read][addr + i] = v; });
      else {
        const t = FC_TABLE[res.fc]; const bits = t === 'coils';
        const vals = parseVals(op.val, bits).map(v => bits ? v : (Number(v) & 0xFFFF));
        vals.forEach((v, i) => { S.vals[t][addr + i] = v; });
      }
    }
    animate(res.fc, addr, count, res.ok);
    return res;
  } catch (e) { toast(e.message, true); if (/sesión/i.test(e.message)) { S.session.connected = false; setChipSession(); } return null; }
  finally { busy(btn, false); }
}
function renderSteps(sel, steps) {
  const box = $(sel); box.innerHTML = '';
  steps.forEach((s, i) => {
    const d = document.createElement('div'); d.className = 'step';
    d.innerHTML = `<span class="n">${i + 1}</span><span class="t">${s.t}</span><button class="btn mini">Ejecutar</button>`;
    d.querySelector('button').onclick = async (ev) => {
      if (s.target && S.session.host !== targetById(s.target).host) { await connectTo(targetById(s.target)); }
      fillForm(s.op);
      const r = await runOp(s.op, ev.target); if (r) d.classList.add('done');
    };
    box.appendChild(d);
  });
}
function fillForm(op) {
  if (op.read) { $(`input[name=rt][value=${op.read}]`).checked = true; $('#r-addr').value = op.addr; $('#r-count').value = op.count; }
  else { $(`input[name=wt][value=${op.write}]`).checked = true; $('#w-addr').value = op.addr; $('#w-val').value = op.val; }
}

/* ------------------------------------------------------------------ sesión */
function targetById(id) { return S.targets.find(t => t.id === id); }
function setChipSession() {
  const c = $('#chip-session'); const s = S.session;
  c.textContent = s.connected ? `conectado · ${s.host}:${s.port} · unit ${s.unit}` : 'sin sesión Modbus';
  c.className = 'chip' + (s.connected ? ' ok' : ''); updatePlcSub();
}
function currentTarget() {
  const v = $('#target').value;
  if (v === 'custom') return { host: $('#host').value.trim(), port: +$('#port').value, unit: +$('#unit').value };
  const t = targetById(v); return { host: t.host, port: t.port, unit: +$('#unit').value };
}
async function connectTo(t) {
  try {
    if (t.id) $('#target').value = t.id; $('#custom-row').classList.toggle('hidden', $('#target').value !== 'custom');
    const r = await api('/api/connect', { host: t.host, port: t.port, unit: t.unit || +$('#unit').value });
    S.session = r; setChipSession();
    $('#pyline').innerHTML = `&gt;&gt;&gt; from pymodbus.client import ModbusTcpClient\n&gt;&gt;&gt; ${esc(r.pymodbus)}\n<span class="c"># True · sesión abierta: un único socket TCP para todas las peticiones</span>`;
    toast(`Conectado a ${r.host}:${r.port}`);
  } catch (e) { S.session = { connected: false }; setChipSession(); toast(e.message, true); }
}
async function initTargets() {
  const j = await api('/api/targets'); S.targets = j.targets; S.session = j.session;
  const sel = $('#target'); sel.innerHTML = j.targets.map(t => `<option value="${t.id}">${esc(t.label)} · ${t.host}:${t.port}</option>`).join('') + '<option value="custom">personalizado…</option>';
  sel.onchange = () => { $('#custom-row').classList.toggle('hidden', sel.value !== 'custom'); const t = targetById(sel.value); $('#target-note').textContent = t ? t.note : 'Cualquier esclavo alcanzable desde la red ot-lab (172.28.0.x) o por nombre de servicio.'; };
  sel.onchange(); setChipSession();
}

/* ------------------------------------------------------------------ sondeo (como OpenPLC) */
function pollTick() {
  const T = TABLEROS[S.tablero]; const byTable = {};
  [...T.inputs, ...T.outputs].forEach(it => { byTable[it.table] = Math.max(byTable[it.table] || 0, it.addr + 1); });
  const ops = Object.entries(byTable).map(([t, n]) => ({ read: t, addr: 0, count: n }));
  (async () => { for (const op of ops) { if (!S.poll) break; await runOp(op); } })();
}
function togglePoll() {
  const b = $('#btn-poll');
  if (S.poll) { clearInterval(S.poll); S.poll = null; b.textContent = 'Iniciar sondeo'; b.classList.remove('rojo'); return; }
  if (!S.session.connected) { toast('Conecte primero.', true); return; }
  const ms = +$('#poll-ms').value; S.poll = setInterval(pollTick, ms); pollTick();
  b.textContent = '■ Detener sondeo'; b.classList.add('rojo');
}

/* ------------------------------------------------------------------ captura / Wireshark */
function capRender(c) {
  const chip = $('#chip-capture');
  chip.textContent = c.running ? `● capturando ${c.seconds}s · ${c.bytes} B` : (c.file ? `captura ${c.file}` : 'sin captura');
  chip.className = 'chip' + (c.running ? ' bad' : (c.file ? ' ok' : ''));
  $('#cap-status').textContent = c.running ? `tcpdump activo · ${c.file} · ${c.bytes} bytes` : (c.file ? `detenida · ${c.file} · ${c.bytes} bytes` : (c.tcpdump ? 'lista para capturar' : 'tcpdump no disponible'));
  const ready = !c.running && c.file && c.bytes > 24;
  $('#cap-ready').classList.toggle('hidden', !ready);
  if (ready) $('#btn-wireshark').href = `/api/capture/file/${c.file}`;
  $('#btn-cap-start').disabled = c.running; $('#btn-cap-stop').disabled = !c.running;
}
async function capRefresh() { try { capRender(await api('/api/capture')); } catch (e) { /* silencioso */ } }
async function capList() {
  try { const j = await api('/api/capture/list'); $('#cap-files').innerHTML = j.files.length ? j.files.map(f => `<li><a href="/api/capture/file/${f.name}" download>${esc(f.name)}</a><span class="gr mono">${f.bytes} B · ${f.mtime.replace('T', ' ')}</span></li>`).join('') : '<li class="gr">todavía ninguna · están en ot-lab/captures/</li>'; } catch (e) { }
}

/* ------------------------------------------------------------------ OpenPLC */
function plcChip(st) { const c = $('#chip-plc'); c.textContent = 'OpenPLC · ' + (st || '?'); c.className = 'chip' + (st === 'Running' ? ' ok' : (st === 'Stopped' ? ' bad' : '')); }
async function plcRefresh() {
  try {
    const j = await api('/api/openplc/status');
    plcChip(j.status);
    $('#plc-status').textContent = `${j.status} · programa: ${j.program || '—'} (${j.file || '—'})`;
    const tb = $('#plc-devices tbody');
    tb.innerHTML = j.devices.length ? j.devices.map(d => `<tr><td>${esc(d.cols[0] || '')}</td><td>${esc(d.cols[1] || '')}</td>${[2, 3, 4, 5].map(i => `<td class="mono">${esc(d.cols[i] || '-')}</td>`).join('')}<td><button class="btn mini gris" data-del="${d.id}">borrar</button></td></tr>`).join('') : '<tr><td colspan="7" class="gr">ningún Slave Device configurado</td></tr>';
    tb.querySelectorAll('[data-del]').forEach(b => b.onclick = async () => { busy(b, true); try { await api(`/api/openplc/device/${b.dataset.del}`, null, 'DELETE'); await plcRefresh(); } catch (e) { toast(e.message, true); } });
  } catch (e) { plcChip('sin acceso'); $('#plc-status').textContent = e.message; }
}
async function plcPrograms() {
  try {
    const j = await api('/api/openplc/programs'); const sel = $('#plc-prog');
    sel.innerHTML = j.programs.map(p => `<option value="${p.id}">${esc(p.id)}.st · ${esc(p.title.slice(0, 60))}</option>`).join('') + '<option value="_edit">(editado a mano)</option>';
    sel.onchange = () => { const p = j.programs.find(x => x.id === sel.value); if (p) { $('#plc-st').value = p.st; $('#plc-name').value = p.id; } };
    sel.onchange();
    $('#plc-st').addEventListener('input', () => { sel.value = '_edit'; });
  } catch (e) { toast(e.message, true); }
}
function plcLog(txt, ok) { const p = $('#plc-log'); p.classList.remove('hidden'); p.innerHTML = esc(txt).replace(/Compilation finished successfully!/, '<span class="ok">$&</span>').replace(/Compilation finished with errors!/, '<span class="bad">$&</span>'); p.scrollTop = p.scrollHeight; }
async function plcProgram(setup, btn) {
  busy(btn, true); plcLog('Subiendo y compilando… (MatIEC + gcc, 30–120 s la primera vez)');
  try {
    const body = { name: $('#plc-name').value || 'programa', st: $('#plc-st').value, start: $('#plc-autostart').checked };
    const j = await api(setup ? '/api/openplc/setup' : '/api/openplc/program', body);
    plcLog(j.log || '(sin log)'); toast(j.ok ? `Compilado · PLC ${j.status}` : 'La compilación falló: revise el log', !j.ok);
    await plcRefresh();
  } catch (e) { plcLog('ERROR: ' + e.message); toast(e.message, true); }
  finally { busy(btn, false); }
}
function monRender(j) {
  const tb = $('#mon-table tbody');
  $('#mon-meta').textContent = `${j.status} · ${j.rows.length} variables · ${new Date().toLocaleTimeString('es-EC', { hour12: false })}`;
  if (!j.rows.length) { tb.innerHTML = `<tr><td colspan="4" class="gr">${j.status === 'Running' ? 'sin variables located (AT %…) en el programa' : 'PLC parado: Start PLC para ver valores'}</td></tr>`; return; }
  tb.innerHTML = j.rows.map(r => {
    let v;
    if (r.type === 'BOOL') v = `<span class="tf ${/TRUE/.test(r.value) ? 'on' : ''}"></span>${r.value}`;
    else { const n = Number(r.value); const pct = isNaN(n) ? 0 : Math.min(100, Math.abs(n) / 655.35); v = `<span class="bar" style="width:${Math.max(2, pct)}px"></span>${esc(r.value)}`; }
    return `<tr><td>${esc(r.name)}</td><td class="mono">${esc(r.type)}</td><td class="mono">${esc(r.location)}</td><td>${v}</td></tr>`;
  }).join('');
}
async function monTick() { try { monRender(await api('/api/openplc/monitor')); } catch (e) { $('#mon-meta').textContent = e.message; } }
function monToggle() {
  const b = $('#btn-mon-toggle');
  if (S.mon) { clearInterval(S.mon); S.mon = null; b.textContent = '▶ Iniciar monitoreo'; b.classList.remove('rojo'); return; }
  S.mon = setInterval(monTick, +$('#mon-ms').value); monTick(); b.textContent = '■ Detener monitoreo'; b.classList.add('rojo');
}

/* ------------------------------------------------------------------ server.json */
async function jsonRefresh() {
  try {
    const j = await api('/api/serverjson'); const tb = $('#json-table tbody');
    if (!j.available) { $('#json-meta').textContent = 'no montado'; return; }
    if (j.error) { $('#json-meta').textContent = j.error; tb.innerHTML = ''; return; }
    $('#json-meta').textContent = `${j.path} · ${j.mtime.replace('T', ' ')} · puerto ${j.server.listenerPort} · log ${j.server.logging && j.server.logging.logLevel}`;
    const map = { discreteInput: ['DI · FC 02', 1], coils: ['Coils · FC 01/05/15', 0], inputRegister: ['IR · FC 04', 3], holdingRegister: ['HR · FC 03/06/16', 4] };
    let h = '';
    for (const [k, [lab, pre]] of Object.entries(map)) {
      const t = j.registers[k] || {};
      Object.keys(t).sort((a, b) => a - b).forEach(key => { const a = +key - 1; h += `<tr><td>${lab}</td><td class="mono">"${key}"</td><td class="mono">${a}</td><td class="mono">${pre}${String(a + 1).padStart(4, '0')}</td><td class="mono">${String(t[key])}</td></tr>`; });
    }
    tb.innerHTML = h || '<tr><td colspan="5" class="gr">sin registros declarados</td></tr>';
  } catch (e) { $('#json-meta').textContent = e.message; }
}

/* ------------------------------------------------------------------ arranque */
function init() {
  const ts = $('#tablero'); ts.innerHTML = Object.entries(TABLEROS).map(([k, t]) => `<option value="${k}">${esc(t.label)}</option>`).join('');
  ts.onchange = () => { S.tablero = ts.value; buildTablero(); };
  buildTablero(); renderSteps('#steps-1b', STEPS_1B);
  $$('.tabs button').forEach(b => b.onclick = () => { $$('.tabs button').forEach(x => x.classList.toggle('on', x === b)); $$('.tab').forEach(t => t.classList.toggle('on', t.id === b.dataset.tab)); if (b.dataset.tab === 'tjson') jsonRefresh(); if (b.dataset.tab === 'tws') { capRefresh(); capList(); } if (b.dataset.tab === 't1b') plcRefresh(); });
  $('#btn-connect').onclick = () => connectTo(currentTarget());
  $('#btn-disconnect').onclick = async () => { try { await api('/api/disconnect', {}); } catch (e) { } S.session = { connected: false }; setChipSession(); if (S.poll) togglePoll(); $('#pyline').innerHTML = '&gt;&gt;&gt; c.close()'; };
  $('#btn-read').onclick = e => runOp({ read: $('input[name=rt]:checked').value, addr: +$('#r-addr').value, count: +$('#r-count').value }, e.target);
  $('#btn-write').onclick = e => runOp({ write: $('input[name=wt]:checked').value, addr: +$('#w-addr').value, val: $('#w-val').value }, e.target);
  $('#btn-poll').onclick = togglePoll;
  $('#btn-clear').onclick = () => { S.log = []; $('#log tbody').innerHTML = ''; };
  $('#btn-csv').onclick = () => {
    const head = ['#', 'hora', 'FC', 'funcion', 'direccion', 'datos_en', 'pdu_query', 'pdu_response', 'valor', 'ms'];
    const rows = S.log.map(r => [r.n, r.hora, r.fc, r.nombre, r.dir, r.datos, r.pq, r.pr, r.valor, r.ms].map(v => `"${String(v).replace(/"/g, '""')}"`).join(','));
    const blob = new Blob(['﻿' + [head.join(','), ...rows].join('\n')], { type: 'text/csv' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'tabla_modbus.csv'; a.click();
  };
  $('#btn-cap-start').onclick = async e => { busy(e.target, true); try { capRender(await api('/api/capture/start', { ports: [5020, 502] })); toast('Capturando: ejecute ahora las operaciones'); S.capTimer = setInterval(capRefresh, 2000); } catch (x) { toast(x.message, true); } finally { busy(e.target, false); } };
  $('#btn-cap-stop').onclick = async e => { busy(e.target, true); try { capRender(await api('/api/capture/stop', {})); clearInterval(S.capTimer); capList(); toast('Captura detenida: «Abrir en Wireshark»'); } catch (x) { toast(x.message, true); } finally { busy(e.target, false); } };
  $$('[data-copy]').forEach(b => b.onclick = () => navigator.clipboard.writeText($('#' + b.dataset.copy).textContent).then(() => toast('Copiado al portapapeles')));
  $('#btn-cmd-openplc').onclick = () => { $('#cmd-live').textContent = `docker run --rm --net container:openplc nicolaka/netshoot \\\n  tcpdump -i eth0 -U -w - "tcp port 5020" \\\n  | wireshark -k -i - -o mbtcp.tcp.port:5020`; };
  $('#btn-cmd-script').onclick = () => { $('#cmd-live').textContent = `./scripts/wireshark_vivo.sh modbus-sim    # o: openplc · modbus-explorer`; };
  $('#btn-json').onclick = jsonRefresh;
  $('#btn-plc-refresh').onclick = plcRefresh;
  $('#btn-plc-start').onclick = async e => { busy(e.target, true); try { const j = await api('/api/openplc/start', {}); plcChip(j.status); await plcRefresh(); } catch (x) { toast(x.message, true); } finally { busy(e.target, false); } };
  $('#btn-plc-stop').onclick = async e => { busy(e.target, true); try { const j = await api('/api/openplc/stop', {}); plcChip(j.status); await plcRefresh(); } catch (x) { toast(x.message, true); } finally { busy(e.target, false); } };
  $('#btn-plc-setup').onclick = e => plcProgram(true, e.target);
  $('#btn-plc-program').onclick = e => plcProgram(false, e.target);
  $('#btn-dv-add').onclick = async e => {
    busy(e.target, true);
    try { await api('/api/openplc/device', { name: $('#dv-name').value, ip: $('#dv-ip').value, port: +$('#dv-port').value, slave_id: +$('#dv-id').value, di_size: +$('#dv-di').value, coil_size: +$('#dv-co').value, ir_size: +$('#dv-ir').value, hr_read_size: +$('#dv-hr').value, hr_write_size: +$('#dv-hw').value }); toast('Esclavo guardado · reinicie el PLC (Stop → Start)'); await plcRefresh(); }
    catch (x) { toast(x.message, true); } finally { busy(e.target, false); }
  };
  $('#btn-mon-toggle').onclick = monToggle;
  $('#btn-iframe').onclick = () => { $('#iframe-wrap').innerHTML = '<iframe src="http://localhost:8080/monitoring" title="OpenPLC Monitoring"></iframe>'; };
  initTargets().then(() => { const s = S.session; if (s && s.connected) setChipSession(); });
  capRefresh(); plcPrograms(); plcRefresh();
}
document.addEventListener('DOMContentLoaded', init);
