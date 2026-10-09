/* Explorador Modbus TCP · Taller 5 · prácticas 1a y 1b · ot-lab (UCuenca) */
'use strict';
const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
const NS = 'http://www.w3.org/2000/svg';
const TABLE_INFO = {
  di:    { y: 149, name: 'Discrete inputs',   sub: '1x · FC 02 · R',          acc: 'R',   fcs: [2] },
  coils: { y: 229, name: 'Coils',             sub: '0x · FC 01·05·15 · R/W', acc: 'R/W', fcs: [1, 5, 15] },
  ir:    { y: 309, name: 'Input registers',   sub: '3x · FC 04 · R',          acc: 'R',   fcs: [4] },
  hr:    { y: 389, name: 'Holding registers', sub: '4x · FC 03·06·16 · R/W', acc: 'R/W', fcs: [3, 6, 16] },
};
const FC_TABLE = { 1: 'coils', 2: 'di', 3: 'hr', 4: 'ir', 5: 'coils', 6: 'hr', 15: 'coils', 16: 'hr' };
const FC_WRITE = new Set([5, 6, 15, 16]);
const dec = (v, d = 1) => (v / 10).toFixed(d).replace('.', ',');
const i16 = v => (v > 32767 ? v - 65536 : v);
const FORMATS = {
  bool_onoff:   { label: 'bit · encendido/apagado', bits: true, fmt: b => b ? '1 encendido' : '0 apagado' },
  bool_pressed: { label: 'bit · pulsado',           bits: true, fmt: b => b ? '1 pulsado' : '0' },
  bool_open:    { label: 'bit · abierta/cerrada',   bits: true, fmt: b => b ? '1 abierta' : '0 cerrada' },
  bool_run:     { label: 'bit · marcha/parada',     bits: true, fmt: b => b ? '1 marcha' : '0 parada' },
  bool_alarm:   { label: 'bit · sonando',           bits: true, fmt: b => b ? '1 sonando' : '0' },
  int:   { label: 'entero 0–65535', fmt: v => `${v}` },
  x10c:  { label: '×10 · °C',       fmt: v => `${v} = ${dec(v)}°C` },
  x10pct:{ label: '×10 · %',        fmt: v => `${v} = ${dec(v)} %` },
  ppm:   { label: 'ppm',            fmt: v => `${v} ppm` },
  hpa:   { label: 'hPa',            fmt: v => `${v} hPa` },
  pct:   { label: '%',              fmt: v => `${v} %` },
  modo:  { label: '0 manual / 1 auto', fmt: v => `${v} ${v ? '(auto)' : '(manual)'}` },
  rpm:   { label: 'rpm',            fmt: v => `${v} rpm` },
  lpm:   { label: 'L/min',          fmt: v => `${v} L/min` },
};
const ICONS = { thermo: 'termómetro', drop: 'gota', co2: 'CO₂', gauge: 'manómetro', knob: 'consigna', bell: 'umbral/alarma', fan: 'ventilador', led: 'LED', button: 'pulsador', door: 'puerta', pump: 'bomba', siren: 'sirena' };
const fmtOf = it => (FORMATS[it.format] || FORMATS.int).fmt;

/* ------------------------------------------------------------------ tableros (láminas 21, 30 y 31) */
const TABLEROS = {
  lam31: {
    label: 'Lámina 31 · 4 medidas y 5 parámetros (registros)',
    left: 'CAMPO · 4 MEDIDAS', right: '5 PARÁMETROS · HOLDING',
    inputs: [
      { table: 'ir', addr: 0, name: 'Temperatura', icon: 'thermo', format: 'x10c' },
      { table: 'ir', addr: 1, name: 'Humedad',     icon: 'drop',   format: 'x10pct' },
      { table: 'ir', addr: 2, name: 'CO₂',         icon: 'co2',    format: 'ppm' },
      { table: 'ir', addr: 3, name: 'Presión',     icon: 'gauge',  format: 'hpa' },
    ],
    outputs: [
      { table: 'hr', addr: 0, name: 'Consigna T',   icon: 'knob', format: 'x10c' },
      { table: 'hr', addr: 1, name: 'Consigna HR',  icon: 'knob', format: 'x10pct' },
      { table: 'hr', addr: 2, name: 'Umbral CO₂',   icon: 'bell', format: 'ppm' },
      { table: 'hr', addr: 3, name: 'Ventilador %', icon: 'fan',  format: 'pct' },
      { table: 'hr', addr: 4, name: 'Modo',         icon: 'knob', format: 'modo' },
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
      { table: 'di', addr: 0, name: 'Marcha',     icon: 'button', format: 'bool_pressed' },
      { table: 'di', addr: 1, name: 'Paro',       icon: 'button', format: 'bool_pressed' },
      { table: 'di', addr: 2, name: 'Emergencia', icon: 'button', format: 'bool_pressed' },
      { table: 'di', addr: 3, name: 'Puerta',     icon: 'door',   format: 'bool_open' },
    ],
    outputs: [
      { table: 'coils', addr: 0, name: 'LED verde',  icon: 'led',   format: 'bool_onoff' },
      { table: 'coils', addr: 1, name: 'LED rojo',   icon: 'led',   format: 'bool_onoff' },
      { table: 'coils', addr: 2, name: 'Ventilador', icon: 'fan',   format: 'bool_onoff' },
      { table: 'coils', addr: 3, name: 'Bomba',      icon: 'pump',  format: 'bool_run' },
      { table: 'coils', addr: 4, name: 'Sirena',     icon: 'siren', format: 'bool_alarm' },
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
      { table: 'di', addr: 0, name: 'Pulsador',    icon: 'button', format: 'bool_pressed' },
      { table: 'ir', addr: 0, name: 'Temperatura', icon: 'thermo', format: 'x10c' },
      { table: 'ir', addr: 1, name: 'CO₂',         icon: 'co2',    format: 'ppm' },
    ],
    outputs: [
      { table: 'coils', addr: 0, name: 'LED',        icon: 'led',  format: 'bool_onoff' },
      { table: 'coils', addr: 1, name: 'Ventilador', icon: 'fan',  format: 'bool_onoff' },
      { table: 'hr',    addr: 0, name: 'Consigna',   icon: 'knob', format: 'x10c' },
      { table: 'hr',    addr: 1, name: 'Umbral CO₂', icon: 'bell', format: 'ppm' },
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
const S = { tablero: 'custom', vals: { di: {}, coils: {}, ir: {}, hr: {} }, items: [], log: [], targets: [], session: {}, poll: null, mon: null, capTimer: null };

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
function pathStr(x1, y1, x2, y2) { const k = x2 > x1 ? 45 : -45; return `M${x1} ${y1} C ${x1 + k} ${y1}, ${x2 - k} ${y2}, ${x2} ${y2}`; }
function buildTablero() {
  const T = TABLEROS[S.tablero];
  const st = $('#dg-static'), cards = $('#dg-cards');
  st.innerHTML = ''; cards.innerHTML = ''; $('#dg-fx').innerHTML = '';
  st.appendChild(el('text', { class: 'ro', x: 0, y: 30 }, T.left));
  st.appendChild(el('text', { class: 'ro', x: 870, y: 30, 'text-anchor': 'end' }, T.right));
  st.appendChild(el('rect', { class: 'plc', x: 315, y: 44, width: 240, height: 452, rx: 10 }));
  st.appendChild(el('text', { class: 'tt', x: 435, y: 80, 'text-anchor': 'middle' }, 'PLC · esclavo'));
  st.appendChild(el('text', { class: 'ts', x: 435, y: 103, 'text-anchor': 'middle', id: 'dg-plc-sub' }, '— · unit —'));
  const used = new Set([...T.inputs, ...T.outputs].map(i => i.table));
  for (const [k, inf] of Object.entries(TABLE_INFO)) {
    const off = used.has(k) ? '' : ' off';
    st.appendChild(el('rect', { class: 'row' + off, id: 'row-' + k, x: 327, y: inf.y - 31, width: 216, height: 62, rx: 6 }));
    st.appendChild(el('text', { class: 'rt' + off, x: 339, y: inf.y - 5 }, inf.name));
    st.appendChild(el('text', { class: 'rs', x: 339, y: inf.y + 19 }, inf.sub));
  }
  S.items = [];
  const custom = S.tablero === 'custom';
  const slotsIn = custom ? Math.max(T.inputs.length, 4) : T.inputs.length;     // huecos fantasma solo en el tablero del editor
  const slotsOut = custom ? Math.max(T.outputs.length, 4) : T.outputs.length;
  const nmax = Math.max(slotsIn, slotsOut, 4);
  const H = nmax > 5 ? 40 + nmax * 92 + 8 : 500;
  $('#dg').setAttribute('viewBox', `0 0 870 ${H}`);
  st.querySelector('.plc').setAttribute('height', H - 48);
  const place = (list, x, isOut) => {
    const pitch = (isOut ? slotsOut : slotsIn) > 4 ? 92 : 112;
    list.forEach((it, i) => {
      const y = 40 + i * pitch, cy = y + 41;
      const ry = TABLE_INFO[it.table].y;
      it.pIn = isOut ? pathStr(555, ry, 640, cy) : pathStr(230, cy, 315, ry);       // sentido de la flecha dibujada
      it.pRead = isOut ? pathStr(640, cy, 555, ry) : it.pIn;                        // lectura: tarjeta → PLC
      it.pWrite = isOut ? it.pIn : pathStr(315, ry, 230, cy);                        // escritura: PLC → tarjeta
      const rw = TABLE_INFO[it.table].acc === 'R/W';
      st.appendChild(el('path', { class: 'ln' + (rw ? ' w' : ''), d: it.pIn }));
      // etiqueta R / R/W sobre el cable, cerca de la tarjeta
      const lx = isOut ? 640 - 12 : 230 + 12, ly = cy - 12;
      st.appendChild(el('text', { class: 'acc' + (rw ? ' w' : ''), x: lx, y: ly, 'text-anchor': isOut ? 'end' : 'start' }, rw ? 'R/W' : 'R'));
      const g = el('g', { class: 'item', id: `it-${it.table}-${it.addr}` });
      g.appendChild(el('rect', { class: 'card', x, y, width: 230, height: 82, rx: 8 }));
      g.appendChild(icon(it.icon, x + 8, y));
      g.appendChild(el('text', { class: 'nm2', x: x + 66, y: y + 34 }, it.name));
      g.appendChild(el('text', { class: 'ch', x: x + 66, y: y + 64 }, `${{ di: 'DI', coils: 'coil', ir: 'IR', hr: 'HR' }[it.table]} ${it.addr}`));
      const tv = el('text', { class: 'st2', x: x + 146, y: y + 64 }); tv.appendChild(el('tspan', { class: 'b' }, '—')); g.appendChild(tv);
      g.appendChild(el('text', { class: 'ty', x: x + 66, y: y + 80 }, `clave JSON "${it.addr + 1}" · ${{ di: 1, coils: 0, ir: 3, hr: 4 }[it.table]}${String(it.addr + 1).padStart(4, '0')}`));
      it.g = g; it.tv = tv; it.shown = undefined;
      cards.appendChild(g); S.items.push(it);
    });
  };
  place(T.inputs, 0, false); place(T.outputs, 640, true);
  if (S.tablero === 'custom') {   // huecos en gris: se irán llenando desde el editor «Modbus server»
    const ghost = (x, i, n, isOut) => {
      const pitch = n > 4 ? 92 : 112; const y = 40 + i * pitch;
      const g = el('g', { class: 'item ghost' });
      g.appendChild(el('rect', { class: 'card', x, y, width: 230, height: 82, rx: 8 }));
      g.appendChild(el('rect', { class: 'ico', x: x + 14, y: y + 20, width: 40, height: 40, rx: 8 }));
      g.appendChild(el('text', { class: 'gh', x: x + 66, y: y + 40 }, isOut ? 'salida / parámetro' : 'entrada / medida'));
      g.appendChild(el('text', { class: 'gh', x: x + 66, y: y + 66, style: 'font-size:15px;font-weight:400' }, 'añádalo en Modbus server'));
      cards.appendChild(g);
    };
    for (let i = T.inputs.length; i < slotsIn; i++) ghost(0, i, slotsIn, false);
    for (let i = T.outputs.length; i < slotsOut; i++) ghost(640, i, slotsOut, true);
  }
  S.items.forEach(refreshCard);
  updatePlcSub();
  renderSteps('#steps', T.steps);
  $('#json-snippet').textContent = T.json || edJson();
}
function updatePlcSub() { const s = S.session; const t = $('#dg-plc-sub'); if (t) t.textContent = s.connected ? `${s.host}:${s.port} · unit ${s.unit}` : 'sin conexión'; $('#dg-target').textContent = s.connected ? `${s.host}:${s.port} · unit ${s.unit}` : 'sin conexión'; }
function refreshCard(it, mode) {
  const v = S.vals[it.table][it.addr];
  it.tv.innerHTML = '';
  if (v === undefined) { it.tv.appendChild(el('tspan', { class: 'b' }, '—')); return; }
  const txt = fmtOf(it)(v);
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
function logRow(row) {
  S.log.push(row); if (S.log.length > 400) S.log.shift();
  const tb = $('#log tbody'); const tr = document.createElement('tr'); tr.className = 'new' + (row.bad ? ' err' : '') + (row.trama === 'Query' ? ' q' : ' r');
  tr.innerHTML = `<td>${row.n}</td><td class="mono">${row.hora}</td><td><span class="tr-${row.trama === 'Query' ? 'q' : 'r'}">${esc(row.trama)}</span><br><span class="gr">${esc(row.sentido)}</span></td><td class="mono">${row.fc}</td><td>${esc(row.nombre)}</td><td class="mono">${row.dir}</td><td class="mono">${esc(row.pdu)}</td><td class="mono">${esc(row.datos)}</td><td class="mono">${row.ms}</td>`;
  tb.prepend(tr); while (tb.children.length > 400) tb.lastChild.remove();
}
function logOp(res, addr) {
  // dos filas por transacción, como la lista de Wireshark: primero la Query del maestro, luego la Response del esclavo
  const q = res.frames.find(f => f.dir === 'query'), r = res.frames.find(f => f.dir === 'response');
  const hora = new Date().toLocaleTimeString('es-EC', { hour12: false }); const write = FC_WRITE.has(res.fc);
  const fld = (f, name) => { const x = (f.fields || []).find(z => z.name.startsWith(name)); return x ? (Array.isArray(x.value) ? '[' + x.value.join(', ') + ']' : String(x.value)) : ''; };
  if (!q) { logRow({ n: res.seq, hora, trama: 'Query', sentido: 'no enviada', fc: String(res.fc).padStart(2, '0'), nombre: res.fc_name, dir: addr, pdu: '—', datos: res.error || '—', ms: '', bad: true }); return; }
  const qData = write ? fld(q, 'Data') : `solo pide · ${fld(q, 'Bit Count') || fld(q, 'Word Count')} ${res.fc <= 2 ? 'bits' : 'registros'}`;
  // la Response va primero al prepend para que la Query quede arriba
  if (!r) logRow({ n: res.seq, hora, trama: 'Response', sentido: 'esclavo → maestro', fc: '—', nombre: 'sin Response (timeout)', dir: addr, pdu: '—', datos: '—', ms: res.elapsed_ms, bad: true });
  else if (res.exception) logRow({ n: res.seq, hora, trama: 'Response', sentido: 'esclavo → maestro', fc: `${String(res.fc).padStart(2, '0')}+128 = 0x${(res.fc + 128).toString(16)}`, nombre: `excepción ${String(res.exception.code).padStart(2, '0')} ${res.exception.name}`, dir: addr, pdu: r.pdu.hex, datos: 'código de excepción', ms: res.elapsed_ms, bad: true });
  else logRow({ n: res.seq, hora, trama: 'Response', sentido: 'esclavo → maestro', fc: String(res.fc).padStart(2, '0'), nombre: res.fc_name, dir: addr, pdu: r.pdu.hex, datos: write ? (res.fc <= 6 ? `eco · ${fld(r, 'Data')}` : `confirma · count ${fld(r, 'Count')}`) : fld(r, 'Data'), ms: res.elapsed_ms, bad: false });
  logRow({ n: res.seq, hora, trama: 'Query', sentido: 'maestro → esclavo', fc: String(res.fc).padStart(2, '0'), nombre: res.fc_name, dir: addr, pdu: q.pdu.hex, datos: qData, ms: '', bad: false });
}

/* ------------------------------------------------------------------ ejecutar operaciones */
function parseVals(txt, bits) {
  return txt.split(/[,;\s]+/).filter(Boolean).map(v => bits ? /^(1|t|true|on|v|si|sí)$/i.test(v) : (v.trim()));
}
function opAlert(pyline, html) {   // alerta en «Última operación»: la petición no se envía
  $('#pyline').innerHTML = `&gt;&gt;&gt; ${esc(pyline)}\n<span class="c"># no enviado: la web lo rechazó antes de llegar a pymodbus</span>`;
  const b = $('#op-banner'); b.className = 'banner'; b.innerHTML = `<b>No se puede:</b> ${html}`;
  $('#op-meta').textContent = 'rechazado · ninguna trama viajó';
  $('#frame-query .fbody').innerHTML = '<span class="gr">—</span>'; $('#frame-response .fbody').innerHTML = '<span class="gr">—</span>';
  toast('Operación rechazada: vea «Última operación»', true);
  // también queda en la tabla a entregar: cuenta como intento, sin trama
  logRow({ n: '—', hora: new Date().toLocaleTimeString('es-EC', { hour12: false }), trama: 'Query', sentido: 'rechazada por la web · no enviada', fc: '—', nombre: 'petición no válida', dir: '—', pdu: '—', datos: html.replace(/<[^>]+>/g, '').slice(0, 110), ms: '', bad: true });
}
function validateOp(op) {
  const addrBad = v => !Number.isInteger(v) || v < 0 || v > 65535;
  if (addrBad(op.addr)) return [`c.read_coils(${op.addr}, …)`, `la dirección debe ser un entero entre 0 y 65535 (en la trama viaja en 2 bytes).`];
  if (op.read) {
    if (!Number.isInteger(op.count) || op.count < 1) return [`c.${READ_NAMES[op.read]}(${op.addr}, count=${op.count})`, `<code>count</code> debe ser al menos 1.`];
    const max = (op.read === 'coils' || op.read === 'di') ? 2000 : 125;
    if (op.count > max) return [`c.${READ_NAMES[op.read]}(${op.addr}, count=${op.count})`, `Modbus limita una lectura a ${max} ${max === 2000 ? 'bits' : 'registros'} por petición (la PDU cabe en 253 bytes). Pida menos o haga varias peticiones.`];
    return null;
  }
  const bits = op.write === 'coil' || op.write === 'coils'; const multi = op.write === 'coils' || op.write === 'registers';
  const raw = String(op.val).split(/[,;\s]+/).filter(Boolean);
  const fn = { coil: 'write_coil', coils: 'write_coils', register: 'write_register', registers: 'write_registers' }[op.write];
  const py = `c.${fn}(${op.addr}, ${multi ? '[' + raw.join(', ') + ']' : raw[0]}, device_id=${S.session.unit})`;
  if (!raw.length) return [py, 'indique un valor.'];
  if (!multi && raw.length > 1) return [py, `FC ${bits ? '05' : '06'} escribe <b>un solo</b> ${bits ? 'coil' : 'registro'}. Para varios use FC ${bits ? '15 (varios coils)' : '16 (varios registros)'}.`];
  if (bits) {
    const bad = raw.filter(v => !/^(0|1|t|f|true|false|on|off|v|si|sí|no)$/i.test(v));
    if (bad.length) return [py, `un <b>coil es un bit</b>: solo admite 0/1 (o T/F, true/false, on/off). «${esc(bad[0])}» no cabe en un bit; en la trama FC 05 solo existen <code>ff 00</code> (ON) y <code>00 00</code> (OFF). Si quería escribir un número, use un <b>holding register</b> (FC 06/16).`];
    if (raw.length > 1968) return [py, 'FC 15 admite como máximo 1968 coils por petición.'];
  } else {
    const bad = raw.filter(v => !/^-?\d+$/.test(v));
    if (bad.length) return [py, `un <b>registro es un entero de 16 bits</b> (0–65535). «${esc(bad[0])}» no es un entero; los decimales se acuerdan con escala (23,5 °C → 235, ×10).`];
    if (raw.length > 123) return [py, 'FC 16 admite como máximo 123 registros por petición.'];
  }
  return null;
}
const READ_NAMES = { coils: 'read_coils', di: 'read_discrete_inputs', hr: 'read_holding_registers', ir: 'read_input_registers' };
function declaredWarning(table, addr, count) {   // aviso si se toca una dirección que el tablero no declara (modbus-sim)
  if (!S.session.connected || S.session.host !== '172.28.0.30') return '';
  const T = TABLEROS[S.tablero]; if (!T) return '';
  const declared = new Set([...T.inputs, ...T.outputs].filter(i => i.table === table).map(i => i.addr));
  if (!declared.size) return `la tabla <b>${TABLE_INFO[table].name}</b> no tiene elementos en el tablero actual: el esclavo responde 0 (<code>initializeUndefinedRegisters</code>) o excepción 02 si está desactivado.`;
  const missing = []; for (let a = addr; a < addr + count; a++) if (!declared.has(a)) missing.push(a);
  return missing.length ? `la${missing.length > 1 ? 's' : ''} dirección${missing.length > 1 ? 'es' : ''} <b>${missing.join(', ')}</b> no está${missing.length > 1 ? 'n' : ''} declarada${missing.length > 1 ? 's' : ''} en el tablero (${TABLE_INFO[table].name}): el esclavo contesta 0 por <code>initializeUndefinedRegisters</code>; con esa opción desactivada respondería excepción 02 Illegal Data Address.` : '';
}
async function runOp(op, btn) {
  if (!S.session.connected) { toast('Primero conecte con el esclavo (pestaña pymodbus · Sesión).', true); return null; }
  const bad = validateOp(op); if (bad) { opAlert(bad[0], bad[1]); return null; }
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
    const warn = declaredWarning(FC_TABLE[res.fc], addr, count);
    if (warn) { const b = $('#op-banner'); if (b.classList.contains('hidden')) { b.className = 'banner'; b.innerHTML = `<b>Aviso:</b> ${warn}`; } else b.innerHTML += `<br><b>Aviso:</b> ${warn}`; }
    if (res.ok) {
      if (op.read) res.values.forEach((v, i) => { S.vals[op.read][addr + i] = v; });
      else {
        const t = FC_TABLE[res.fc]; const bits = t === 'coils';
        const vals = parseVals(op.val, bits).map(v => bits ? v : (Number(v) & 0xFFFF));
        vals.forEach((v, i) => { S.vals[t][addr + i] = v; });
      }
    }
    animate(res.fc, addr, count, res.ok);
    escPacket();
    bcast({ type: 'op', res, addr, count, vals: S.vals });
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
  escUpdate();
  const c = $('#chip-session'); const s = S.session;
  const who = { '172.28.0.30': 'Modbus server', '172.28.0.10': 'OpenPLC', '172.28.0.90': 'Conpot' }[s.host] || `${s.host}:${s.port}`;
  c.textContent = s.connected ? `${who} · ${s.unit}` : 'Modbus Server';
  c.className = 'chip' + (s.connected ? ' ok live' : ''); updatePlcSub();
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
    S.session = r; setChipSession(); bcast({ type: 'session', session: r });
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
  S.capRunning = !!c.running; escUpdate();
  const chip = $('#chip-capture');
  chip.textContent = c.running ? `Captura · ${c.seconds}s · ${c.bytes} B` : (c.file ? `Captura · ${c.file}` : 'Captura');
  chip.className = 'chip' + (c.running ? ' bad rec' : (c.file ? ' ok' : ''));
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
function plcChip(st) { if (S.plcStatus !== st) bcast({ type: 'plc', status: st }); S.plcStatus = st; escUpdate(); const c = $('#chip-plc'); c.textContent = st === 'Running' || st === 'Stopped' ? 'OpenPLC' : 'OpenPLC · ' + (st || '?'); c.title = 'Estado del runtime: ' + (st || '?'); c.className = 'chip' + (st === 'Running' ? ' ok live' : (st === 'Stopped' ? ' bad' : '')); }
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
    const map = { discreteInput: ['DI · FC 02', 1, 'R'], coils: ['Coils · FC 01/05/15', 0, 'R/W'], inputRegister: ['IR · FC 04', 3, 'R'], holdingRegister: ['HR · FC 03/06/16', 4, 'R/W'] };
    let h = '';
    for (const [k, [lab, pre, acc]] of Object.entries(map)) {
      const t = j.registers[k] || {}; const rw = acc === 'R/W';
      Object.keys(t).sort((a, b) => a - b).forEach(key => { const a = +key - 1; h += `<tr class="${rw ? 'acc-rw' : 'acc-r'}"><td>${lab}</td><td><span class="tag ${rw ? 'rw' : ''}">${acc}</span></td><td class="mono">"${key}"</td><td class="mono">${a}</td><td class="mono">${pre}${String(a + 1).padStart(4, '0')}</td><td class="mono">${String(t[key])}</td></tr>`; });
    }
    tb.innerHTML = h || '<tr><td colspan="6" class="gr">sin registros declarados</td></tr>';
    offsetCheck();
  } catch (e) { $('#json-meta').textContent = e.message; }
}

/* ------------------------------------------------------------------ arranque */
function tableroOptions() {
  const ts = $('#tablero'); const cur = ts.value;
  const order = ['custom', ...Object.keys(TABLEROS).filter(k => k !== 'custom')];
  ts.innerHTML = order.filter(k => TABLEROS[k]).map(k => `<option value="${k}">${esc(TABLEROS[k].label)}</option>`).join('');
  ts.value = cur && TABLEROS[cur] ? cur : S.tablero;
}
function init() {
  TABLEROS.custom = customTablero();
  const ts = $('#tablero'); tableroOptions();
  ts.onchange = () => { S.tablero = ts.value; buildTablero(); bcast({ type: 'tablero', ed: {}, tablero: ts.value }); };
  edInit(); escInit(); layoutInit();
  buildTablero(); renderSteps('#steps-1b', STEPS_1B);
  $$('.tabs button[data-tab]').forEach(b => b.onclick = () => { $$('.tabs button[data-tab]').forEach(x => x.classList.toggle('on', x === b)); $$('.tab').forEach(t => t.classList.toggle('on', t.id === b.dataset.tab)); if (b.dataset.tab === 'tjson') jsonRefresh(); if (b.dataset.tab === 'tws') { capRefresh(); capList(); } if (b.dataset.tab === 't1b') plcRefresh(); });
  $('#btn-connect').onclick = () => connectTo(currentTarget());
  $('#btn-disconnect').onclick = async () => { try { await api('/api/disconnect', {}); } catch (e) { } S.session = { connected: false }; setChipSession(); if (S.poll) togglePoll(); $('#pyline').innerHTML = '&gt;&gt;&gt; c.close()'; };
  $('#btn-read').onclick = e => runOp({ read: $('input[name=rt]:checked').value, addr: +$('#r-addr').value, count: +$('#r-count').value }, e.target);
  $('#btn-write').onclick = e => runOp({ write: $('input[name=wt]:checked').value, addr: +$('#w-addr').value, val: $('#w-val').value }, e.target);
  $('#btn-poll').onclick = togglePoll;
  $('#btn-clear').onclick = () => { S.log = []; $('#log tbody').innerHTML = ''; };
  $('#btn-csv').onclick = () => {
    const head = ['#', 'hora', 'trama', 'sentido', 'FC', 'funcion', 'direccion', 'pdu', 'datos', 'ms'];
    const rows = S.log.map(r => [r.n, r.hora, r.trama, r.sentido, r.fc, r.nombre, r.dir, r.pdu, r.datos, r.ms].map(v => `"${String(v).replace(/"/g, '""')}"`).join(','));
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
  capRefresh(); plcPrograms(); plcRefresh(); jsonRefresh();
}
document.addEventListener('DOMContentLoaded', init);


/* ------------------------------------------------------------------ Modbus server · editor gráfico */
const ED = { title: 'Mi tablero', left: 'CAMPO · ENTRADAS', right: 'SALIDAS Y PARÁMETROS', inputs: [], outputs: [], logLevel: 'DEBUG', init: true, dirty: false };
const DEF_ITEM = { di: { name: 'Pulsador', icon: 'button', format: 'bool_pressed', value: false }, coils: { name: 'LED', icon: 'led', format: 'bool_onoff', value: false },
                   ir: { name: 'Sensor', icon: 'gauge', format: 'int', value: 0 }, hr: { name: 'Parámetro', icon: 'knob', format: 'int', value: 0 } };
function edAddresses() {   // dirección = orden dentro de cada tabla
  const c = { di: 0, coils: 0, ir: 0, hr: 0 };
  [...ED.inputs, ...ED.outputs].forEach(it => { it.addr = c[it.table]++; });
}
function customTablero() {
  edAddresses();
  const mk = it => ({ table: it.table, addr: it.addr, name: it.name, icon: it.icon, format: it.format });
  const T = { label: `${ED.title} · editor (Modbus server)${ED.inputs.length + ED.outputs.length ? '' : ' · vacío'}`, left: ED.left, right: ED.right, inputs: ED.inputs.map(mk), outputs: ED.outputs.map(mk), json: null, steps: [] };
  const n = { di: 0, coils: 0, ir: 0, hr: 0 }; [...ED.inputs, ...ED.outputs].forEach(it => { n[it.table] = Math.max(n[it.table], it.addr + 1); });
  const names = { di: ['FC 02', 'entradas digitales'], coils: ['FC 01', 'coils'], ir: ['FC 04', 'input registers'], hr: ['FC 03', 'holding registers'] };
  for (const t of ['di', 'ir', 'coils', 'hr']) if (n[t]) T.steps.push({ t: `<b>${names[t][0]}</b> · leer ${n[t]} ${names[t][1]} en bloque · <code>count=${n[t]}</code>`, op: { read: t, addr: 0, count: n[t] } });
  ED.outputs.forEach(it => {
    if (it.table === 'coils') T.steps.push({ t: `<b>FC 05</b> · ${esc(it.name)} ON (coil ${it.addr})`, op: { write: 'coil', addr: it.addr, val: 'T' } });
    else T.steps.push({ t: `<b>FC 06</b> · ${esc(it.name)} (HR ${it.addr}) ← valor`, op: { write: 'register', addr: it.addr, val: String(Number(it.value) || 0) } });
  });
  const hrs = ED.outputs.filter(i => i.table === 'hr'), cls = ED.outputs.filter(i => i.table === 'coils');
  if (cls.length > 1) T.steps.push({ t: `<b>FC 15</b> · todos los coils en una trama`, op: { write: 'coils', addr: 0, val: cls.map(() => 'T').join(',') } });
  if (hrs.length > 1) T.steps.push({ t: `<b>FC 16</b> · todos los holding en una trama`, op: { write: 'registers', addr: 0, val: hrs.map(i => Number(i.value) || 0).join(',') } });
  return T;
}
function edJson() {
  edAddresses();
  const keys = { di: 'discreteInput', coils: 'coils', ir: 'inputRegister', hr: 'holdingRegister' };
  const regs = { discreteInput: {}, coils: {}, inputRegister: {}, holdingRegister: {} };
  [...ED.inputs, ...ED.outputs].forEach(it => { const bits = FORMATS[it.format] && FORMATS[it.format].bits; regs[keys[it.table]][String(it.addr + 1)] = bits ? !!it.value : (Number(it.value) & 0xFFFF); });
  const line = (k) => `"${k}":${' '.repeat(Math.max(1, 18 - k.length))}{ ${Object.entries(regs[k]).map(([a, v]) => `"${a}": ${v}`).join(', ')} }`;
  return `"initializeUndefinedRegisters": ${ED.init},\n` + Object.keys(regs).filter(k => Object.keys(regs[k]).length).map(line).join(',\n');
}
function edRow(it, list, i) {
  const bits = it.table === 'di' || it.table === 'coils';
  const fmts = Object.entries(FORMATS).filter(([k, f]) => !!f.bits === bits);
  const d = document.createElement('div'); d.className = 'edrow' + (list === ED.outputs ? ' out' : '');
  d.innerHTML = `<span class="ch">${{ di: 'DI', coils: 'coil', ir: 'IR', hr: 'HR' }[it.table]} ${it.addr}</span>
    <input class="nm" value="${esc(it.name)}" title="nombre">
    <select class="ic" title="icono">${Object.entries(ICONS).map(([k, v]) => `<option value="${k}" ${k === it.icon ? 'selected' : ''}>${v}</option>`).join('')}</select>
    <select class="fm" title="formato / escala">${fmts.map(([k, f]) => `<option value="${k}" ${k === it.format ? 'selected' : ''}>${f.label}</option>`).join('')}</select>
    ${bits ? `<select class="vl" title="valor inicial"><option value="0" ${!it.value ? 'selected' : ''}>0 false</option><option value="1" ${it.value ? 'selected' : ''}>1 true</option></select>` : `<input class="vl" type="number" min="0" max="65535" value="${Number(it.value) || 0}" title="valor inicial">`}
    <span class="ops"><button data-op="up" title="subir">↑</button><button data-op="down" title="bajar">↓</button><button data-op="del" title="borrar">✕</button></span>`;
  d.querySelector('.nm').oninput = e => { it.name = e.target.value; edChanged(false); };
  d.querySelector('.ic').onchange = e => { it.icon = e.target.value; edChanged(); };
  d.querySelector('.fm').onchange = e => { it.format = e.target.value; edChanged(); };
  d.querySelector('.vl').onchange = e => { it.value = bits ? e.target.value === '1' : Number(e.target.value); edChanged(); };
  d.querySelectorAll('[data-op]').forEach(b => b.onclick = () => {
    const j = list.indexOf(it);
    if (b.dataset.op === 'del') list.splice(j, 1);
    if (b.dataset.op === 'up' && j > 0) [list[j - 1], list[j]] = [list[j], list[j - 1]];
    if (b.dataset.op === 'down' && j < list.length - 1) [list[j + 1], list[j]] = [list[j], list[j + 1]];
    edChanged();
  });
  return d;
}
function edRender() {
  edAddresses();
  const a = $('#ed-inputs'), b = $('#ed-outputs'); a.innerHTML = ''; b.innerHTML = '';
  ED.inputs.forEach((it, i) => a.appendChild(edRow(it, ED.inputs, i)));
  ED.outputs.forEach((it, i) => b.appendChild(edRow(it, ED.outputs, i)));
  if (!ED.inputs.length) a.innerHTML = '<span class="gr">sin entradas · use los botones +</span>';
  if (!ED.outputs.length) b.innerHTML = '<span class="gr">sin salidas · use los botones +</span>';
  $('#ed-title').value = ED.title; $('#ed-left').value = ED.left; $('#ed-right').value = ED.right; $('#ed-log').value = ED.logLevel; $('#ed-init').checked = ED.init;
}
function edChanged(rerender = true, fromPeer = false) {
  ED.dirty = true; if (!fromPeer) bcast({ type: 'tablero', ed: { title: ED.title, left: ED.left, right: ED.right, inputs: ED.inputs, outputs: ED.outputs, init: ED.init }, tablero: 'custom' }); $('#ed-status').textContent = 'cambios sin guardar';
  TABLEROS.custom = customTablero(); tableroOptions();
  if (rerender) edRender();
  if (S.tablero !== 'custom') { S.tablero = 'custom'; $('#tablero').value = 'custom'; }
  const keep = S.vals; buildTablero(); S.vals = keep; S.items.forEach(it => refreshCard(it));
  $('#json-snippet').textContent = edJson();
}
function edLoadPreset(k) {
  const T = TABLEROS[k]; if (!T) return;
  const vals = { lam31: { ir: [235, 480, 612, 1013], hr: [260, 500, 800, 40, 0] }, lam30: { di: [true, false, false, true], coils: [true, false, false, false, false] }, lam21: { di: [true], coils: [false, false], ir: [235, 612], hr: [260, 800] } }[k] || {};
  const mk = it => ({ table: it.table, name: it.name, icon: it.icon, format: it.format, value: (vals[it.table] || [])[it.addr] ?? (FORMATS[it.format].bits ? false : 0) });
  ED.title = T.label.split(' · ')[0]; ED.left = T.left; ED.right = T.right; ED.inputs = T.inputs.map(mk); ED.outputs = T.outputs.map(mk);
  edChanged();
}
function edFromRegisters(regs) {
  const map = [['discreteInput', 'di', true], ['inputRegister', 'ir', true], ['coils', 'coils', false], ['holdingRegister', 'hr', false]];
  ED.inputs = []; ED.outputs = [];
  for (const [key, t, isIn] of map) {
    const tbl = regs[key] || {}; const ks = Object.keys(tbl).map(Number).sort((a, b) => a - b); const n = ks.length ? Math.max(...ks) : 0;
    for (let a = 1; a <= n; a++) { const d = DEF_ITEM[t]; (isIn ? ED.inputs : ED.outputs).push({ table: t, name: `${d.name} ${a - 1}`, icon: d.icon, format: d.format, value: tbl[String(a)] ?? d.value }); }
  }
  ED.title = 'server.json actual'; edChanged();
}
function edDoc() {
  edAddresses();
  const mk = it => ({ table: it.table, name: it.name, icon: it.icon, format: it.format, value: it.value });
  return { server: { logLevel: ED.logLevel, initializeUndefinedRegisters: ED.init }, tablero: { title: ED.title, left: ED.left, right: ED.right, inputs: ED.inputs.map(mk), outputs: ED.outputs.map(mk) } };
}
async function edSave(btn, apply) {
  busy(btn, true);
  try {
    const j = await api('/api/modbus-server', edDoc(), 'PUT');
    ED.dirty = false; $('#ed-status').textContent = 'guardado en modbus/server.json'; toast('server.json guardado');
    if (apply) {
      $('#ed-status').textContent = 'reiniciando modbus-sim…';
      const r = await api('/api/modbus-server/apply', {});
      $('#ed-status').textContent = `modbus-sim ${r.status} · tablero aplicado`; toast('modbus-sim reiniciado con el nuevo tablero');
      S.vals = { di: {}, coils: {}, ir: {}, hr: {} }; S.items.forEach(it => { it.shown = undefined; refreshCard(it); });
      if (S.session.connected && S.session.host === '172.28.0.30') { await new Promise(r => setTimeout(r, 1200)); await connectTo({ host: '172.28.0.30', port: 5020, unit: S.session.unit }); }
      else { S.session = { connected: false }; setChipSession(); }
    }
    jsonRefresh();
  } catch (e) { $('#ed-status').textContent = e.message; toast(e.message, true); }
  finally { busy(btn, false); }
}
async function edInit() {
  $$('[data-preset]').forEach(b => b.onclick = () => edLoadPreset(b.dataset.preset));
  $$('[data-add]').forEach(b => b.onclick = () => { const t = b.dataset.add; const d = DEF_ITEM[t]; (t === 'di' || t === 'ir' ? ED.inputs : ED.outputs).push({ table: t, ...d }); edChanged(); });
  $('#btn-ed-empty').onclick = () => { ED.inputs = []; ED.outputs = []; ED.title = 'Mi tablero'; edChanged(); };
  $('#btn-ed-fromjson').onclick = async () => { const j = await api('/api/modbus-server'); if (j.registers) edFromRegisters(j.registers); };
  $('#ed-title').oninput = e => { ED.title = e.target.value; edChanged(false); };
  $('#ed-left').oninput = e => { ED.left = e.target.value; edChanged(false); };
  $('#ed-right').oninput = e => { ED.right = e.target.value; edChanged(false); };
  $('#ed-log').onchange = e => { ED.logLevel = e.target.value; ED.dirty = true; $('#ed-status').textContent = 'cambios sin guardar'; };
  $('#ed-init').onchange = e => { ED.init = e.target.checked; edChanged(false); };
  $('#btn-ed-save').onclick = e => edSave(e.target, false);
  $('#btn-ed-apply').onclick = e => edSave(e.target, true);
  try {
    const j = await api('/api/modbus-server');
    if (j.tablero && (j.tablero.inputs.length || j.tablero.outputs.length)) {
      Object.assign(ED, { title: j.tablero.title, left: j.tablero.left, right: j.tablero.right, inputs: j.tablero.inputs, outputs: j.tablero.outputs });
    }   // sin tablero.json: el editor arranca vacío y el tablero muestra los huecos en gris
    if (j.server) { ED.logLevel = (j.server.logging && j.server.logging.logLevel) || 'DEBUG'; ED.init = j.registers ? j.registers.initializeUndefinedRegisters !== false : true; }
    if (!j.docker) $('#btn-ed-apply').title = 'Sin socket de Docker: guarde y ejecute docker compose restart modbus-sim';
    TABLEROS.custom = customTablero(); tableroOptions(); edRender(); if (S.tablero === 'custom') { const keep = S.vals; buildTablero(); S.vals = keep; S.items.forEach(it => refreshCard(it)); } $('#json-snippet').textContent = edJson(); ED.dirty = false; $('#ed-status').textContent = j.writable ? 'listo' : 'carpeta modbus/ solo lectura';
  } catch (e) { $('#ed-status').textContent = e.message; }
}

/* ------------------------------------------------------------------ escenario: vista simple por niveles CIM (Clase 2) y vista Detalle (lámina 18) */
let escTimer = null;
function escSvg() { return document.body.classList.contains('esc-detail') ? $('#esc') : $('#esc-cim'); }
function escUpdate() {
  if (!$('#esc') || !$('#esc-cim')) return;
  const s = S.session || {}; const toSim = s.connected && s.host === '172.28.0.30'; const toPlc = s.connected && s.host === '172.28.0.10';
  const running = S.plcStatus === 'Running';
  const setLink = (name, on) => $$(`[data-link="${name}"]`).forEach(e => { e.classList.add('on'); e.classList.toggle('live', !!on); });
  const setNode = (name, cls, on) => $$(`[data-node="${name}"]`).forEach(e => e.classList.toggle(cls, !!on));
  setLink('ex-sim', toSim); setLink('ex-plc', toPlc); setLink('plc-sim', running);
  setNode('sim', 'live', toSim); setNode('plc', 'live', toPlc); setNode('plc', 'off', S.plcStatus === 'Stopped' || S.plcStatus === 'sin acceso');
  setNode('explorer', 'live', s.connected);
  const set = (id, cls, on) => { const e = $('#' + id); if (e) e.classList.toggle(cls, !!on); };
  set('l-cap', 'live', S.capRunning); set('esc-cap', 'live', S.capRunning); set('l-browser', 'live', true);
  $('#esc-meta').textContent = `${s.connected ? 'sesión → ' + s.host + ':' + s.port : 'sin sesión'} · PLC ${S.plcStatus || '?'}${S.capRunning ? ' · capturando' : ''}`;
  if (running && !escTimer) escTimer = setInterval(() => escQueryResponse('plc-sim', 420), 1000);   // cada ciclo: Query baja, Response sube
  if (!running && escTimer) { clearInterval(escTimer); escTimer = null; }
}
function escDot(link, dur, back) {
  // Query: por el cable de ida (maestro → esclavo). Response: por el cable de vuelta (.up) si existe, o el mismo cable al revés.
  const svg = escSvg(); if (!svg || svg.classList.contains('hidden')) return;
  const down = svg.querySelector(`path[data-link="${link}"]:not(.up)`) || svg.querySelector('#' + link);
  const up = svg.querySelector(`path.up[data-link="${link}"]`);
  const fx = svg.querySelector('#esc-fx, #cim-fx'); if (!down || !fx) return;
  const p = back && up ? up : down; const reverse = back && !up;
  const c = el('circle', { r: 7, class: 'dot' + (back ? ' resp' : '') });
  const am = el('animateMotion', { dur: `${dur || 600}ms`, begin: 'indefinite', fill: 'freeze', path: p.getAttribute('d'), keyPoints: reverse ? '1;0' : '0;1', keyTimes: '0;1', calcMode: 'linear' });
  c.appendChild(am); fx.appendChild(c); am.beginElement(); setTimeout(() => c.remove(), (dur || 600) + 80);
}
function escQueryResponse(link, dur) { escDot(link, dur); setTimeout(() => escDot(link, dur, true), dur + 40); }
function escPacket() {
  const s = S.session || {}; const link = s.host === '172.28.0.10' ? 'ex-plc' : 'ex-sim';
  escQueryResponse(link, 450); escDot('l-browser', 400);
}
function escInit() {
  const keyD = 'esc-detail'; let hidden = false, detail = false;
  try { detail = localStorage.getItem(keyD) === '1'; } catch (e) { }
  const apply = () => {
    document.body.classList.toggle('esc-detail', detail);
    $('#esc').classList.toggle('hidden', hidden || !detail); $('#esc-cim').classList.toggle('hidden', hidden || detail);
    $('#btn-esc-detail').textContent = detail ? 'Simple' : 'Detalle';
    $('#esc-title').textContent = detail ? 'Escenario · detalle: qué hay y dónde vive (lámina 18)' : 'Escenario · por niveles CIM (Clase 2) · una orden baja, un dato sube';
  };
  $('#btn-esc-detail').onclick = () => { detail = !detail; try { localStorage.setItem(keyD, detail ? '1' : '0'); } catch (e) { } apply(); };
  apply(); escUpdate();
}

/* ------------------------------------------------------------------ disposición: bloques movibles y en pestaña nueva */
const LAYOUT_KEY = 'explorer-layout-v1';
const BC = ('BroadcastChannel' in window) ? new BroadcastChannel('modbus-explorer') : null;
const TAB_ID = Math.random().toString(36).slice(2);
function layoutSave() {
  const lay = {};
  $$('[data-drop]').forEach(c => { lay[c.dataset.drop] = $$in(':scope > [data-block]', c).map(b => b.dataset.block); });
  try { localStorage.setItem(LAYOUT_KEY, JSON.stringify(lay)); } catch (e) { }
}
function $$in(sel, root) { return Array.from(root.querySelectorAll(sel)); }
function layoutApply() {
  let lay = null; try { lay = JSON.parse(localStorage.getItem(LAYOUT_KEY) || 'null'); } catch (e) { }
  if (!lay) return;
  for (const [cid, ids] of Object.entries(lay)) {
    const c = document.querySelector(`[data-drop="${cid}"]`); if (!c) continue;
    ids.forEach(id => { const b = document.querySelector(`[data-block="${id}"]`); if (b) c.appendChild(b); });
  }
}
function layoutInit() {
  $$('[data-block]').forEach(b => {
    const bh = document.createElement('div'); bh.className = 'bh';
    const inTab = !!b.closest('.tab');   // dentro de una pestaña: la pestaña entera se abre con el botón de la barra, no cada caja
    bh.innerHTML = `<span class="hd" title="Arrastre para mover este bloque (a la columna izquierda o a otra pestaña)" draggable="true">⠿</span><span class="bt">${esc(b.dataset.title || '')}</span><button class="op col" title="Ocultar o mostrar el contenido de este bloque">Ocultar</button>${inTab ? '' : '<button class="op open" title="Abrir este bloque solo, en una pestaña nueva">↗ pestaña</button>'}`;
    b.prepend(bh);
    const colBtn = bh.querySelector('.col');
    const setCol = (on) => { b.classList.toggle('collapsed', on); colBtn.textContent = on ? 'Mostrar' : 'Ocultar'; };
    let collapsed = []; try { collapsed = JSON.parse(localStorage.getItem('explorer-collapsed') || '[]'); } catch (e) { }
    setCol(collapsed.includes(b.dataset.block));
    colBtn.onclick = () => {
      const on = !b.classList.contains('collapsed'); setCol(on);
      try { let c = JSON.parse(localStorage.getItem('explorer-collapsed') || '[]'); c = on ? [...new Set([...c, b.dataset.block])] : c.filter(x => x !== b.dataset.block); localStorage.setItem('explorer-collapsed', JSON.stringify(c)); } catch (e) { }
    };
    const ob = bh.querySelector('.open'); if (ob) ob.onclick = () => window.open(`${location.pathname}?block=${encodeURIComponent(b.dataset.block)}`, '_blank');
    const hd = bh.querySelector('.hd');
    hd.ondragstart = e => { e.dataTransfer.setData('text/plain', b.dataset.block); e.dataTransfer.effectAllowed = 'move'; b.classList.add('dragging'); S.drag = b; };
    hd.ondragend = () => { b.classList.remove('dragging'); S.drag = null; $$('.drop-marker').forEach(m => m.remove()); $$('[data-drop].dropping').forEach(c => c.classList.remove('dropping')); };
  });
  $$('[data-drop]').forEach(c => {
    c.ondragover = e => {
      if (!S.drag) return; e.preventDefault(); e.dataTransfer.dropEffect = 'move'; c.classList.add('dropping');
      $$('.drop-marker').forEach(m => m.remove());
      const blocks = $$in(':scope > [data-block]', c).filter(x => x !== S.drag);
      const after = blocks.find(x => e.clientY < x.getBoundingClientRect().top + x.getBoundingClientRect().height / 2);
      const m = document.createElement('div'); m.className = 'drop-marker';
      if (after) c.insertBefore(m, after); else c.appendChild(m);
    };
    c.ondragleave = e => { if (!c.contains(e.relatedTarget)) c.classList.remove('dropping'); };
    c.ondrop = e => {
      e.preventDefault(); if (!S.drag) return;
      const m = c.querySelector(':scope > .drop-marker');
      if (m) { c.insertBefore(S.drag, m); m.remove(); } else c.appendChild(S.drag);
      c.classList.remove('dropping'); layoutSave();
    };
  });
  // soltar sobre una pestaña: la activa para poder dejar el bloque dentro
  $$('.tabs button[data-tab]').forEach(t => {
    t.ondragenter = e => { if (!S.drag) return; e.preventDefault(); t.classList.add('droptarget'); t.click(); };
    t.ondragover = e => { if (S.drag) e.preventDefault(); };
    t.ondragleave = () => t.classList.remove('droptarget');
    t.ondrop = e => { e.preventDefault(); t.classList.remove('droptarget'); const c = document.getElementById(t.dataset.tab); if (c && S.drag) { c.appendChild(S.drag); layoutSave(); } };
  });
  $('#btn-layout-reset').onclick = () => { try { localStorage.removeItem(LAYOUT_KEY); localStorage.removeItem('explorer-collapsed'); } catch (e) { } location.reload(); };
  layoutApply();
  const syncTabLink = () => { const t = $('.tabs button.on'); if (t) $('#btn-tab-open').href = `${location.pathname}?tab=${t.dataset.tab}`; };
  syncTabLink(); $$('.tabs button[data-tab]').forEach(b => b.addEventListener('click', syncTabLink));
  drawerInit();
  // modo «solo»: ?block=id muestra únicamente ese bloque; ?tab=id, una pestaña entera
  const qs = new URLSearchParams(location.search); const solo = qs.get('block'); const soloTab = qs.get('tab');
  if (solo) {
    const b = document.querySelector(`[data-block="${solo}"]`);
    if (b) { document.body.classList.add('solo'); $('#solo').appendChild(b); document.title = `${b.dataset.title} · Explorador Modbus`; }
  } else if (soloTab) {
    const t = document.getElementById(soloTab); const btn = $(`.tabs button[data-tab="${soloTab}"]`);
    if (t) { document.body.classList.add('solo'); t.classList.add('on'); $('#solo').appendChild(t); document.title = `${btn ? btn.firstChild.textContent : soloTab} · Explorador Modbus`; if (soloTab === 'tjson') jsonRefresh(); if (soloTab === 'tws') { capRefresh(); capList(); } }
  }
  // sincronía entre pestañas: lo que una hace, las demás lo pintan
  if (BC) {
    BC.onmessage = ev => {
      const m = ev.data; if (!m || m.from === TAB_ID) return;
      if (m.type === 'op') { showOp(m.res); logOp(m.res, m.addr); if (m.vals) S.vals = m.vals; animate(m.res.fc, m.addr, m.count, m.res.ok); escPacket(); }
      if (m.type === 'session') { S.session = m.session; setChipSession(); }
      if (m.type === 'plc') { plcChip(m.status); }
      if (m.type === 'cap') { capRender(m.cap); }
      if (m.type === 'tablero') { if (m.ed && m.ed.inputs) Object.assign(ED, m.ed); TABLEROS.custom = customTablero(); tableroOptions(); if ($('#ed-inputs')) edRender(); S.tablero = m.tablero; $('#tablero').value = m.tablero; const keep = S.vals; buildTablero(); S.vals = keep; S.items.forEach(it => refreshCard(it)); }
    };
  }
}
function bcast(msg) { if (BC) BC.postMessage({ from: TAB_ID, ...msg }); }

async function offsetCheck() {
  const n = $('#offset-note'); if (!n) return;
  try { const j = await api('/api/modbus-server/offset-check'); n.className = 'banner' + (j.ok ? ' ok' : ''); n.querySelector('span').textContent = j.text; }
  catch (e) { n.querySelector('span').textContent = e.message; }
}


/* ------------------------------------------------------------------ panel lateral auto-ocultable */
function drawerInit() {
  const KEY = 'explorer-autohide'; const right = $('#right'); let auto = false, timer = null;
  try { auto = localStorage.getItem(KEY) === '1'; } catch (e) { }
  const apply = () => { document.body.classList.toggle('autohide', auto); right.classList.remove('open'); try { localStorage.setItem(KEY, auto ? '1' : '0'); } catch (e) { } };
  const open = () => { clearTimeout(timer); right.classList.add('open'); };
  const close = (ms) => { clearTimeout(timer); timer = setTimeout(() => right.classList.remove('open'), ms == null ? 700 : ms); };
  $('#btn-drawer').onclick = () => { auto = true; apply(); };
  $('#rail-pin').onclick = () => { auto = false; apply(); };
  $$('#rail [data-railtab]').forEach(b => b.onclick = () => { const t = $(`.tabs button[data-tab="${b.dataset.railtab}"]`); if (t) t.click(); $$('#rail [data-railtab]').forEach(x => x.classList.toggle('on', x === b)); open(); });
  right.addEventListener('mouseenter', () => { if (auto) open(); });
  right.addEventListener('mouseleave', () => { if (auto) close(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && auto) close(0); });
  // al activar una pestaña desde la barra normal, marcar también el riel
  $$('.tabs button[data-tab]').forEach(t => t.addEventListener('click', () => $$('#rail [data-railtab]').forEach(x => x.classList.toggle('on', x.dataset.railtab === t.dataset.tab))));
  apply();
}
