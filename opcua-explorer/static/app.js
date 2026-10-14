/* Explorador OPC UA · ot-lab
   Izquierda: el modelo de opcua-py dibujado (objetos y variables, con valores en vivo) y el server.py que genera,
   con las líneas nuevas/eliminadas respecto a lo guardado en disco y las del elemento seleccionado resaltadas.
   Derecha: editor del elemento, cliente asyncua (navegar, leer, escribir, suscribirse) y mensajes OPC UA Binary. */
'use strict';
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const clone = o => JSON.parse(JSON.stringify(o));

async function api(path, body, method) {
  const r = await fetch(path, { method: method || (body ? 'POST' : 'GET'), headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = j.detail;
    const msg = Array.isArray(d) ? d.map(x => `${(x.loc || []).filter(k => k !== 'body').join('.')}: ${x.msg}`).join(' · ') : d;
    throw new Error(msg || `${r.status} ${r.statusText}`);
  }
  return j;
}
let toastT;
function toast(msg, bad) { const t = $('#toast'); t.textContent = msg; t.className = 'toast' + (bad ? ' bad' : ''); clearTimeout(toastT); toastT = setTimeout(() => t.classList.add('hidden'), bad ? 5200 : 2800); }
function busy(btn, on) { if (btn) { btn.disabled = on; btn.classList.toggle('busy', on); } }

/* ------------------------------------------------------------------ iconos (trazo de 24×24; .f = relleno que se colorea «on») */
const ICONS = {
  plc:    ['PLC', '<rect x="3" y="5" width="18" height="14" rx="1.5"/><path d="M7 9h5M7 12.5h5M7 16h5"/><rect class="f" x="15" y="9" width="3" height="7"/>'],
  tank:   ['tanque', '<path d="M6 4h12v16H6z"/><path class="f" d="M6 12h12v8H6z"/>'],
  motor:  ['motor', '<rect x="3" y="7" width="13" height="10" rx="2"/><path d="M16 12h5M7 7V4.5h5V7"/><circle class="f" cx="9.5" cy="12" r="2"/>'],
  pump:   ['bomba', '<circle cx="11" cy="13" r="7"/><path d="M11 6h10v4"/><path class="f" d="M8 13l3-3.5 3 3.5z"/>'],
  valve:  ['válvula', '<path class="f" d="M3 7v10l9-5zM21 7v10l-9-5z"/><path d="M12 12V5M8.5 5h7"/>'],
  fan:    ['ventilador', '<g class="rot"><circle cx="12" cy="12" r="2"/><path class="f" d="M12 10c0-4 1-7 3-7s2 5-3 7zM14 12c4 0 7 1 7 3s-5 2-7-3zM12 14c0 4-1 7-3 7s-2-5 3-7zM10 12c-4 0-7-1-7-3s5-2 7 3z"/></g>'],
  thermo: ['termómetro', '<path d="M10 4.5a2 2 0 0 1 4 0v9.6a4 4 0 1 1-4 0z"/><circle class="f" cx="12" cy="17.2" r="1.8"/><path d="M12 9v6.5"/>'],
  drop:   ['nivel / gota', '<path class="f" d="M12 3c3 4 6 7.5 6 11a6 6 0 0 1-12 0c0-3.5 3-7 6-11z"/>'],
  gauge:  ['manómetro', '<path d="M4 16a8 8 0 1 1 16 0"/><path d="M12 16l4.5-5"/><circle class="f" cx="12" cy="16" r="1.6"/>'],
  led:    ['LED', '<circle class="f" cx="12" cy="10" r="5.5"/><path d="M9.5 15.5V21M14.5 15.5V21"/>'],
  button: ['pulsador', '<rect x="4" y="11" width="16" height="9" rx="2"/><path class="f" d="M8 11V7.5a4 4 0 0 1 8 0V11z"/>'],
  knob:   ['consigna', '<circle cx="12" cy="12" r="7.5"/><path d="M12 12l3.5-5.5"/><circle class="f" cx="12" cy="12" r="2"/>'],
  bell:   ['alarma', '<path class="f" d="M6 16v-5a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>'],
  folder: ['carpeta', '<path class="f" d="M3 6h7l2 2h9v11H3z"/>'],
};
const OBJ_ICONS = ['plc', 'tank', 'motor', 'pump', 'valve', 'fan'];
const VAR_ICONS = ['thermo', 'drop', 'gauge', 'led', 'button', 'knob', 'bell', 'valve', 'pump', 'fan', 'motor'];
const icon = (name, on, extra) => `<svg class="ico ${esc(name)}${on ? ' on' : ''}${extra ? ' ' + extra : ''}" viewBox="0 0 24 24" aria-hidden="true">${(ICONS[name] || ICONS.gauge)[1]}</svg>`;
const SIM_LABEL = { ninguna: 'sin simulación', seno: 'senoide', coseno: 'cosenoide', rampa: 'rampa (diente de sierra)', aleatorio: 'aleatorio', pulso: 'pulso ON/OFF', modbus: 'pasarela Modbus → OPC UA' };
const NUMERIC = ['Int16', 'UInt16', 'Int32', 'Float', 'Double'];

/* ------------------------------------------------------------------ estado */
const S = {
  model: null, disk: { model: null, code: '' }, def: null, types: [], code: '', spans: {}, previewErr: null,
  sel: { k: 'srv' }, live: {}, liveMap: {}, session: { connected: false }, targets: [],
  msgs: [], lastSeen: 0, lastOp: new Set(), msgSel: null, container: {},
  optable: [], hist: {}, counts: {}, parentOf: {}, nodeClass: {}, capRunning: false, policies: ['None'],
};
const opcuaPy = () => /172\.28\.0\.21|opcua-py/.test(S.session.url || '');

/* ------------------------------------------------------------------ dibujo del espacio de direcciones */
function selKey(sel) { return sel.k === 'obj' ? `obj:${sel.i}` : sel.k === 'var' ? `var:${sel.i}:${sel.j}` : 'srv'; }
function diskHas(o, v) {
  const d = (S.disk.model?.objetos || []).find(x => x.nombre === o.nombre);
  return !!d && (!v || d.variables.some(x => x.nombre === v.nombre && x.tipo === v.tipo));
}
function simText(v) {
  const s = v.sim || {}; const u = v.unidad ? ' ' + v.unidad : '';
  if (s.forma === 'seno' || s.forma === 'coseno') return `${SIM_LABEL[s.forma]} ${s.centro} ± ${s.amplitud}${u} · ${s.periodo_s} s`;
  if (s.forma === 'rampa') return `rampa ${s.min}→${s.max}${u} · ${s.periodo_s} s`;
  if (s.forma === 'aleatorio') return `aleatorio ${s.min}…${s.max}${u}`;
  if (s.forma === 'pulso') return `pulso cada ${s.periodo_s} s`;
  if (s.forma === 'modbus') return `pasarela Modbus · ${(s.tabla || 'hr').toUpperCase()} ${s.direccion ?? 0} de ${s.host || '172.28.0.30'}:${s.puerto || 5020}${s.escala && s.escala != 1 ? ' ×' + s.escala : ''}`;
  return v.escribible ? 'la escriben los clientes' : 'valor fijo';
}
function fmtVal(v, unit) {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'boolean') return v ? 'ON' : 'OFF';
  if (typeof v === 'number') return (Number.isInteger(v) ? String(v) : v.toFixed(2)) + (unit ? ' ' + unit : '');
  return String(v);
}
function renderAspace() {
  const m = S.model; const k = selKey(S.sel);
  $('#addr-meta').textContent = `${m.servidor.endpoint.replace('0.0.0.0', 'localhost')} · ns=2 → ${m.servidor.namespace}`;
  let h = `<div class="aroot${k === 'srv' ? ' sel' : ''}" data-sel="srv">${icon('folder')}<span class="n">Objects</span><span class="m">ns=0;i=85 · carpeta estándar de la norma: aquí cuelgan sus objetos</span></div><div class="objs">`;
  m.objetos.forEach((o, i) => {
    h += `<div class="obj${k === `obj:${i}` ? ' sel' : ''}"><div class="oh" data-sel="obj:${i}">${icon(o.icono)}<div><div class="n">${esc(o.nombre)}${diskHas(o) ? '' : '<span class="badge new">nuevo</span>'}</div><div class="m">ns=2;s=${esc(o.nombre)}</div></div><button class="ibtn x" data-del-obj="${i}" title="Eliminar el objeto">✕</button></div>`;
    o.variables.forEach((v, j) => {
      const label = `${o.nombre}.${v.nombre}`;
      const act = !v.escribible ? '' : v.tipo === 'Boolean'
        ? `<div class="act"><button class="btn mini rojo" data-toggle="${esc(label)}">conmutar</button><span class="gr small">escribe por OPC UA (WriteRequest)</span></div>`
        : `<div class="act"><input data-wval="${esc(label)}" placeholder="valor"><button class="btn mini rojo" data-wbtn="${esc(label)}">escribir</button></div>`;
      h += `<div class="var${k === `var:${i}:${j}` ? ' sel' : ''}" data-sel="var:${i}:${j}">${icon(v.icono, false, '')}
        <div><span class="vn">${esc(v.nombre)}</span><span class="badge ty">${v.tipo}</span><span class="badge ${v.escribible ? 'rw' : 'r'}">${v.escribible ? 'R/W' : 'R'}</span>${diskHas(o, v) ? '' : '<span class="badge new">nuevo</span>'}</div>
        <div class="vv stale" data-live="${esc(label)}" title="valor inicial del modelo: conéctese a opcua-py para verlo en vivo">${esc(fmtVal(v.valor, v.unidad))}</div>
        <div class="vm">ns=2;s=${esc(label)} · ${esc(simText(v))}</div>${act}</div>`;
    });
    if (o.metodo_reset) h += `<div class="var met"><span class="badge ty">Method</span><span class="vn">Reiniciar()</span><span class="vm">ns=2;s=${esc(o.nombre)}.Reiniciar · servicio Call: devuelve las variables escribibles a su valor inicial</span><button class="btn mini rojo" data-call="${esc(o.nombre)}">llamar</button></div>`;
    h += `<div class="addv"><button class="btn mini gris" data-add-var="${i}">+ variable</button></div></div>`;
  });
  h += `</div><button class="btn mini addobj" id="btn-add-obj">+ objeto</button>`;
  $('#aspace').innerHTML = h;
  updateLive();
}
function updateLive() {
  $$('#aspace [data-live]').forEach(el => {
    const label = el.dataset.live; const it = S.live[label];
    const [on, vn] = label.split('.');
    const v = S.model.objetos.find(o => o.nombre === on)?.variables.find(x => x.nombre === vn);
    if (!v) return;
    const row = el.closest('.var');
    if (it && it.value !== null && it.value !== undefined && S.session.connected) {
      const txt = fmtVal(it.value, v.unidad);
      if (el.textContent !== txt) { el.textContent = txt; el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash'); }
      if (S.counts[label] !== undefined && it.count > S.counts[label]) animRow(label, 'PublishResponse', 'pub');
      S.counts[label] = it.count;
      el.classList.remove('stale'); el.title = `en vivo · ${it.status} · ${it.count} cambio(s) recibidos por Publish`;
      row.querySelector('.ico').classList.toggle('on', it.value === true);
    } else {
      el.classList.add('stale'); el.textContent = fmtVal(v.valor, v.unidad);
      row.querySelector('.ico').classList.remove('on');
      el.title = S.session.connected && opcuaPy() ? 'sin valor en vivo: guarde y reinicie opcua-py para publicar esta variable' : 'valor inicial del modelo: conéctese a opcua-py para verlo en vivo';
    }
  });
}

/* ------------------------------------------------------------------ código generado con diferencias */
function diffLines(a, b) {   // LCS por líneas: suficiente para archivos de unos cientos de líneas
  const n = a.length, m = b.length; const T = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) T[i][j] = a[i] === b[j] ? T[i + 1][j + 1] + 1 : Math.max(T[i + 1][j], T[i][j + 1]);
  const out = []; let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) { out.push({ t: 'same', s: b[j], no: j + 1 }); i++; j++; }
    else if (T[i + 1][j] >= T[i][j + 1]) out.push({ t: 'del', s: a[i++] });
    else { out.push({ t: 'add', s: b[j], no: j + 1 }); j++; }
  }
  while (i < n) out.push({ t: 'del', s: a[i++] });
  while (j < m) { out.push({ t: 'add', s: b[j], no: j + 1 }); j++; }
  return out;
}
function hlPy(line) {   // resaltado mínimo: palabras clave, cadenas y comentario final
  const kw = t => t.replace(/\b(async|await|def|import|from|while|with|True|False|return)\b/g, '<span class="kw">$1</span>');
  let out = '', plain = '', q = null;
  const flush = () => { out += kw(esc(plain)); plain = ''; };
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (!q && c === '#') { flush(); return out + `<span class="cm">${esc(line.slice(i))}</span>`; }
    if (!q && (c === '"' || c === "'")) { flush(); q = c; plain = c; continue; }
    if (q) { plain += c; if (c === q) { out += `<span class="st">${esc(plain)}</span>`; plain = ''; q = null; } continue; }
    plain += c;
  }
  if (q) out += `<span class="st">${esc(plain)}</span>`; else flush();
  return out;
}
let lastSelKey = null;
function renderCode() {
  const ops = diffLines(S.disk.code.replace(/\n$/, '').split('\n'), S.code.replace(/\n$/, '').split('\n'));
  const k = selKey(S.sel); const ranges = [];
  for (const key of [k, k.replace('var:', 'sim:')]) if (S.spans[key]) ranges.push(S.spans[key]);
  const inSel = no => no && ranges.some(([a, b]) => no >= a && no <= b);
  const only = $('#code-only').checked;
  const changed = ops.map(o => o.t !== 'same');
  let h = '', gap = false; let nAdd = 0, nDel = 0;
  ops.forEach((o, idx) => {
    if (o.t === 'add') nAdd++; if (o.t === 'del') nDel++;
    if (only && !changed.slice(Math.max(0, idx - 2), idx + 3).some(Boolean) && !inSel(o.no)) { if (!gap) { h += '<div class="ln gap"><span class="no"></span><span class="mk"></span><span>⋯</span></div>'; gap = true; } return; }
    gap = false;
    const cls = ['ln', o.t !== 'same' ? o.t : '', inSel(o.no) ? 'sel' : ''].filter(Boolean).join(' ');
    h += `<div class="${cls}"><span class="no">${o.no || ''}</span><span class="mk">${o.t === 'add' ? '+' : o.t === 'del' ? '−' : ''}</span><span>${hlPy(o.s) || ' '}</span></div>`;
  });
  const cv = $('#codeview'); cv.innerHTML = h;
  $('#code-meta').textContent = S.previewErr ? 'el modelo tiene errores: se muestra el último código válido'
    : (nAdd || nDel) ? `${nAdd} línea(s) nueva(s) · ${nDel} eliminada(s) sin guardar` : 'igual que lo guardado en disco';
  if (lastSelKey !== k) {
    lastSelKey = k;
    const first = cv.querySelector('.ln.sel');
    if (first) cv.scrollTop = Math.max(0, first.offsetTop - cv.clientHeight / 3);
  }
}
let previewT = null;
function changed(rerenderForm) {
  renderAspace();
  if (rerenderForm) renderSel();
  clearTimeout(previewT); previewT = setTimeout(preview, 120);
}
async function preview() {
  try {
    const r = await api('/api/model/preview', { model: S.model });
    const box = $('#model-error');
    if (!r.ok) { S.previewErr = r.error; box.className = 'banner'; box.innerHTML = `<b>No se puede generar server.py:</b> ${esc(r.error)}`; }
    else { S.previewErr = null; box.className = 'banner hidden'; S.code = r.code; S.spans = r.spans; }
    renderCode();
  } catch (e) { toast(e.message, true); }
}

/* ------------------------------------------------------------------ editor del elemento seleccionado */
function iconPicker(list, cur, attr) {
  return `<div class="icopick">${list.map(n => `<button type="button" title="${esc(ICONS[n][0])}" data-${attr}="${n}" class="${n === cur ? 'on' : ''}">${icon(n)}</button>`).join('')}</div>`;
}
function uniqueName(base, taken) { let n = 1; while (taken.includes(`${base}${n}`.toLowerCase())) n++; return `${base}${n}`; }
function renderSel() {
  const f = $('#sel-form'); const sel = S.sel;
  if (sel.k === 'obj') {
    const o = S.model.objetos[sel.i];
    $('#sel-title').innerHTML = `Objeto · <code>ns=2;s=${esc(o.nombre)}</code>`;
    f.innerHTML = `<div class="fgrid">
      <span>Nombre</span><input id="f-oname" value="${esc(o.nombre)}" class="w190">
      <span>Icono</span>${iconPicker(OBJ_ICONS, o.icono, 'oico')}
    </div>
    <p class="note">En el código es <code>add_object</code> bajo la carpeta <b>Objects</b>. El nombre es a la vez el <b>BrowseName</b> (<code>2:${esc(o.nombre)}</code>) y el NodeId de texto (<code>ns=2;s=${esc(o.nombre)}</code>): no cambia aunque añada o quite otros objetos, así que Ignition, FUXA o Node-RED siguen encontrando sus etiquetas.</p>
    <div class="fgrid"><span>Método</span><label class="chk"><input type="checkbox" id="f-met" ${o.metodo_reset ? 'checked' : ''}> <code>Reiniciar()</code>: método OPC UA (servicio <b>Call</b>) que devuelve las variables escribibles a su valor inicial</label></div>
    <div class="frow wrap"><button class="btn mini" data-add-var="${sel.i}">+ variable</button><button class="btn mini gris" id="f-odel">Eliminar objeto</button></div>`;
    $('#f-met').onchange = e => { o.metodo_reset = e.target.checked; changed(true); };
    $('#f-oname').oninput = e => { o.nombre = e.target.value.trim(); changed(); $('#sel-title').innerHTML = `Objeto · <code>ns=2;s=${esc(o.nombre)}</code>`; };
    f.querySelectorAll('[data-oico]').forEach(b => b.onclick = () => { o.icono = b.dataset.oico; changed(true); });
    $('#f-odel').onclick = () => delObj(sel.i);
    return;
  }
  if (sel.k === 'var') {
    const o = S.model.objetos[sel.i]; const v = o.variables[sel.j]; const s = v.sim || (v.sim = { forma: 'ninguna' });
    const forms = v.tipo === 'Boolean' ? ['ninguna', 'pulso', 'modbus'] : v.tipo === 'String' ? ['ninguna'] : ['ninguna', 'seno', 'coseno', 'rampa', 'aleatorio', 'modbus'];
    const num = (id, val, step) => `<input id="${id}" type="number" step="${step || 'any'}" value="${esc(val)}" class="w90">`;
    let simf = '';
    if (s.forma === 'seno' || s.forma === 'coseno') simf = `<span>Centro ± amplitud</span><div class="frow">${num('f-c', s.centro ?? 0)} ± ${num('f-a', s.amplitud ?? 1)} ${esc(v.unidad)}</div><span>Periodo</span><div class="frow">${num('f-p', s.periodo_s ?? 60)} s</div>`;
    else if (s.forma === 'rampa') simf = `<span>Desde → hasta</span><div class="frow">${num('f-min', s.min ?? 0)} → ${num('f-max', s.max ?? 100)} ${esc(v.unidad)}</div><span>Periodo</span><div class="frow">${num('f-p', s.periodo_s ?? 60)} s</div>`;
    else if (s.forma === 'aleatorio') simf = `<span>Entre</span><div class="frow">${num('f-min', s.min ?? 0)} y ${num('f-max', s.max ?? 100)} ${esc(v.unidad)}</div>`;
    else if (s.forma === 'pulso') simf = `<span>Conmuta cada</span><div class="frow">${num('f-p', s.periodo_s ?? 2)} s</div>`;
    else if (s.forma === 'modbus') {
      const tabs = v.tipo === 'Boolean' ? [['coils', 'coils · FC 01'], ['di', 'discrete inputs · FC 02']] : [['hr', 'holding registers · FC 03'], ['ir', 'input registers · FC 04']];
      simf = `<span>Esclavo Modbus</span><div class="frow wrap"><input id="f-mhost" value="${esc(s.host ?? '172.28.0.30')}" class="w120 mono" title="host"> : ${num('f-mport', s.puerto ?? 5020, 1)} unit ${num('f-munit', s.unit ?? 1, 1)}</div>
        <span>Registro</span><div class="frow wrap"><select id="f-mtab">${tabs.map(([k, l]) => `<option value="${k}" ${k === (s.tabla || tabs[0][0]) ? 'selected' : ''}>${l}</option>`).join('')}</select> dir ${num('f-maddr', s.direccion ?? 0, 1)}${v.tipo !== 'Boolean' ? ' × escala ' + num('f-mesc', s.escala ?? 1) : ''}</div>
        <span></span><span class="gr small">cada ciclo el servidor lee ese registro con pymodbus y lo publica aquí: el servidor OPC UA hace de <b>pasarela</b> (nivel 2 ← nivel 0/1). 172.28.0.30:5020 = modbus-sim · 172.28.0.10:502 = OpenPLC (%IW100 = IR 100).</span>`;
    }
    const rng = NUMERIC.includes(v.tipo) ? `<span>Rango (EURange)</span><div class="frow wrap">${num('f-rlo', v.rango ? v.rango[0] : '')} … ${num('f-rhi', v.rango ? v.rango[1] : '')} ${esc(v.unidad)} <span class="gr small">vacío = el de la simulación</span></div>` : '';
    const valIn = v.tipo === 'Boolean' ? `<label class="chk"><input type="checkbox" id="f-val" ${v.valor ? 'checked' : ''}> ON (True)</label>`
      : `<input id="f-val" value="${esc(v.valor)}" class="w190 mono">`;
    $('#sel-title').innerHTML = `Variable · <code>ns=2;s=${esc(o.nombre)}.${esc(v.nombre)}</code>`;
    f.innerHTML = `<div class="fgrid">
      <span>Nombre</span><input id="f-vname" value="${esc(v.nombre)}" class="w190">
      <span>Tipo</span><select id="f-tipo">${S.types.map(t => `<option ${t === v.tipo ? 'selected' : ''}>${t}</option>`).join('')}</select>
      <span>Valor inicial</span>${valIn}
      <span>Acceso</span><label class="chk"><input type="checkbox" id="f-rw" ${v.escribible ? 'checked' : ''}> los clientes pueden escribirla (<code>set_writable()</code>)</label>
      <span>Unidad</span><input id="f-unit" value="${esc(v.unidad)}" class="w90" placeholder="°C, %, bar…">
      <span>Icono</span>${iconPicker(VAR_ICONS, v.icono, 'vico')}
      <span>Simulación</span><select id="f-sim">${forms.map(x => `<option value="${x}" ${x === s.forma ? 'selected' : ''}>${SIM_LABEL[x]}</option>`).join('')}</select>
      ${simf}
      ${rng}
    </div>
    ${v.escribible && s.forma !== 'ninguna' ? '<div class="banner"><b>Ojo:</b> es escribible y además simulada: el servidor sobrescribe lo que escriba un cliente en el siguiente ciclo.</div>' : ''}
    <p class="note">En el código: <code>add_variable</code> dentro de <b>${esc(o.nombre)}</b>${v.escribible ? ', <code>set_writable()</code>' : ''}${s.forma !== 'ninguna' ? ' y una línea <code>write_value</code> en el bucle de simulación' : ''}. Mire las líneas resaltadas a la izquierda.</p>
    <div class="frow wrap"><button class="btn mini gris" id="f-up">↑ subir</button><button class="btn mini gris" id="f-down">↓ bajar</button><button class="btn mini gris" id="f-vdel">Eliminar variable</button></div>`;
    const title = () => { $('#sel-title').innerHTML = `Variable · <code>ns=2;s=${esc(o.nombre)}.${esc(v.nombre)}</code>`; };
    $('#f-vname').oninput = e => { v.nombre = e.target.value.trim(); title(); changed(); };
    $('#f-tipo').onchange = e => {
      v.tipo = e.target.value;
      v.valor = v.tipo === 'Boolean' ? false : v.tipo === 'String' ? '' : (NUMERIC.includes(v.tipo) && ['Float', 'Double'].includes(v.tipo) ? 0.0 : 0);
      if (v.tipo === 'Boolean' && s.forma !== 'pulso') v.sim = { forma: 'ninguna' };
      if (v.tipo === 'String') v.sim = { forma: 'ninguna' };
      if (v.tipo !== 'Boolean' && s.forma === 'pulso') v.sim = { forma: 'ninguna' };
      changed(true);
    };
    const fv = $('#f-val');
    fv.oninput = fv.onchange = e => {
      if (v.tipo === 'Boolean') v.valor = e.target.checked;
      else if (v.tipo === 'String') v.valor = e.target.value;
      else { const n = Number(String(e.target.value).replace(',', '.')); v.valor = Number.isFinite(n) && e.target.value !== '' ? n : e.target.value; }
      changed();
    };
    $('#f-rw').onchange = e => { v.escribible = e.target.checked; changed(true); };
    $('#f-unit').oninput = e => { v.unidad = e.target.value; changed(); };
    f.querySelectorAll('[data-vico]').forEach(b => b.onclick = () => { v.icono = b.dataset.vico; changed(true); });
    $('#f-sim').onchange = e => {
      const fm = e.target.value;
      v.sim = fm === 'seno' || fm === 'coseno' ? { forma: fm, centro: s.centro ?? (typeof v.valor === 'number' ? v.valor : 0), amplitud: s.amplitud ?? 5, periodo_s: s.periodo_s ?? 60 }
        : fm === 'rampa' ? { forma: fm, min: s.min ?? 0, max: s.max ?? 100, periodo_s: s.periodo_s ?? 60 }
        : fm === 'aleatorio' ? { forma: fm, min: s.min ?? 0, max: s.max ?? 100 }
        : fm === 'pulso' ? { forma: fm, periodo_s: s.periodo_s ?? 2 }
        : fm === 'modbus' ? { forma: fm, host: s.host ?? '172.28.0.30', puerto: s.puerto ?? 5020, unit: s.unit ?? 1, tabla: s.tabla ?? (v.tipo === 'Boolean' ? 'coils' : 'hr'), direccion: s.direccion ?? 0, escala: s.escala ?? 1 } : { forma: 'ninguna' };
      changed(true);
    };
    const mh = $('#f-mhost'); if (mh) mh.oninput = e => { v.sim.host = e.target.value.trim(); changed(); };
    const mt = $('#f-mtab'); if (mt) mt.onchange = e => { v.sim.tabla = e.target.value; changed(); };
    const rlo = $('#f-rlo'), rhi = $('#f-rhi');
    const setR = () => { const a = rlo.value, b = rhi.value; v.rango = a === '' || b === '' ? null : [Number(a), Number(b)]; changed(); };
    if (rlo) { rlo.oninput = setR; rhi.oninput = setR; }
    const bindNum = (id, key) => { const el = $('#' + id); if (el) el.oninput = e => { const n = Number(e.target.value); v.sim[key] = e.target.value === '' ? e.target.value : n; changed(); }; };
    bindNum('f-c', 'centro'); bindNum('f-a', 'amplitud'); bindNum('f-p', 'periodo_s'); bindNum('f-min', 'min'); bindNum('f-max', 'max');
    bindNum('f-mport', 'puerto'); bindNum('f-munit', 'unit'); bindNum('f-maddr', 'direccion'); bindNum('f-mesc', 'escala');
    $('#f-up').onclick = () => moveVar(sel.i, sel.j, -1);
    $('#f-down').onclick = () => moveVar(sel.i, sel.j, 1);
    $('#f-vdel').onclick = () => delVar(sel.i, sel.j);
    return;
  }
  $('#sel-title').textContent = 'Elemento seleccionado';
  f.innerHTML = `<p class="note">Pulse un <b>objeto</b> o una <b>variable</b> en el dibujo de la izquierda para editarlo, o añada uno con <b>+ objeto</b> / <b>+ variable</b>. Cada cambio regenera <code>opcua/server.py</code> al instante: verá en verde las líneas nuevas y tachadas en rojo las que desaparecen respecto a lo guardado.</p>
    <div class="frow"><button class="btn mini" id="f-addobj">+ objeto</button></div>`;
  $('#f-addobj').onclick = addObj;
}
function select(sel) { S.sel = sel; renderAspace(); renderSel(); renderCode(); }
function addObj() {
  const taken = S.model.objetos.map(o => o.nombre.toLowerCase());
  S.model.objetos.push({ nombre: uniqueName('PLC', taken), icono: 'plc', variables: [] });
  S.sel = { k: 'obj', i: S.model.objetos.length - 1 }; changed(true);
}
function addVar(i) {
  const o = S.model.objetos[i]; const taken = o.variables.map(v => v.nombre.toLowerCase());
  o.variables.push({ nombre: uniqueName('Variable', taken), tipo: 'Double', valor: 0.0, escribible: false, icono: 'gauge', unidad: '', sim: { forma: 'ninguna' } });
  S.sel = { k: 'var', i, j: o.variables.length - 1 }; changed(true);
}
function delObj(i) { S.model.objetos.splice(i, 1); S.sel = { k: 'srv' }; changed(true); }
function delVar(i, j) { S.model.objetos[i].variables.splice(j, 1); S.sel = { k: 'obj', i }; changed(true); }
function moveVar(i, j, d) {
  const vs = S.model.objetos[i].variables; const k = j + d; if (k < 0 || k >= vs.length) return;
  [vs[j], vs[k]] = [vs[k], vs[j]]; S.sel = { k: 'var', i, j: k }; changed(true);
}
function bindServerForm() {
  const m = S.model.servidor;
  $('#srv-nombre').value = m.nombre; $('#srv-ciclo').value = m.ciclo_ms; $('#srv-endpoint').value = m.endpoint; $('#srv-namespace').value = m.namespace;
  $('#srv-nombre').oninput = e => { S.model.servidor.nombre = e.target.value; changed(); };
  $('#srv-ciclo').oninput = e => { S.model.servidor.ciclo_ms = Number(e.target.value); changed(); };
  $('#srv-endpoint').oninput = e => { S.model.servidor.endpoint = e.target.value.trim(); changed(); };
  $('#srv-namespace').oninput = e => { S.model.servidor.namespace = e.target.value.trim(); changed(); };
  const seg = m.seguridad || (m.seguridad = { none: true, politicas: [], usuarios: [] });
  $('#sec-none').checked = seg.none !== false;
  $('#sec-none').onchange = e => { seg.none = e.target.checked; changed(); };
  const POLS = ['Basic256Sha256', 'Aes128_Sha256_RsaOaep', 'Aes256_Sha256_RsaPss', 'Basic128Rsa15', 'Basic256'];
  $('#sec-pols').innerHTML = POLS.map(pn => `<label class="chk"><input type="checkbox" data-pol="${pn}" ${(seg.politicas || []).includes(pn) ? 'checked' : ''}> ${pn}${pn === 'Basic128Rsa15' || pn === 'Basic256' ? ' <span class="gr small">(obsoleta)</span>' : ''}</label>`).join('');
  $$('#sec-pols [data-pol]').forEach(cb => cb.onchange = () => { seg.politicas = $$('#sec-pols [data-pol]').filter(x => x.checked).map(x => x.dataset.pol); changed(); });
  const renderUsers = () => {
    $('#sec-users').innerHTML = (seg.usuarios || []).map((u, i) => `<div class="frow wrap"><input data-u="${i}" value="${esc(u.usuario)}" class="w120" placeholder="usuario"><input data-p="${i}" value="${esc(u.clave)}" class="w120 mono" placeholder="clave"><button class="ibtn x" data-ud="${i}" title="quitar">✕</button></div>`).join('') || '<span class="gr small">sin usuarios: solo sesión anónima</span>';
    $$('#sec-users [data-u]').forEach(el => el.oninput = e => { seg.usuarios[+el.dataset.u].usuario = e.target.value.trim(); changed(); });
    $$('#sec-users [data-p]').forEach(el => el.oninput = e => { seg.usuarios[+el.dataset.p].clave = e.target.value; changed(); });
    $$('#sec-users [data-ud]').forEach(el => el.onclick = () => { seg.usuarios.splice(+el.dataset.ud, 1); renderUsers(); changed(); });
  };
  renderUsers();
  $('#sec-adduser').onclick = () => { (seg.usuarios = seg.usuarios || []).push({ usuario: 'alumno', clave: 'ucuenca' }); renderUsers(); changed(); };
}
function loadModel(m) { S.model = clone(m); S.sel = { k: 'srv' }; bindServerForm(); changed(true); }

/* ------------------------------------------------------------------ guardar / aplicar */
async function refreshServer() {
  try {
    const r = await api('/api/model'); S.container = r.container;
    const c = $('#chip-server'); const cs = r.container;
    if (!cs.available) { c.textContent = 'opcua-py · sin Docker'; c.className = 'chip'; return r; }
    if (cs.status !== 'running') { c.textContent = `opcua-py · ${cs.status}`; c.className = 'chip bad'; return r; }
    c.textContent = r.pending_restart ? 'opcua-py · pendiente de reiniciar' : 'opcua-py · al día';
    c.className = 'chip' + (r.pending_restart ? ' bad' : ' ok');
    return r;
  } catch (e) { return null; }
}
async function save() {
  const r = await api('/api/model', { model: S.model }, 'PUT');
  S.disk = { model: clone(S.model), code: r.code }; S.code = r.code;
  renderAspace(); renderCode(); refreshServer();
  $('#save-status').textContent = `guardado ${new Date().toLocaleTimeString()} · ${r.files.join(' + ')}`;
}
async function apply(btn) {
  busy(btn, true); $('#apply-logs').classList.add('hidden'); S.applying = true;
  try {
    await save();
    $('#save-status').textContent = 'reiniciando opcua-py…';
    const wasOurs = S.session.connected && opcuaPy();
    const r = await api('/api/model/apply', {});
    if (!r.ok) {
      $('#save-status').textContent = `opcua-py no arrancó (${r.container?.status || '?'})`;
      const lg = $('#apply-logs'); lg.textContent = r.logs || '(sin registros)'; lg.classList.remove('hidden');
      toast('opcua-py no arrancó: mire el registro debajo del botón', true);
    } else {
      $('#save-status').textContent = `opcua-py en marcha con el código nuevo · ${r.seconds} s`;
      toast('opcua-py reiniciado con el modelo nuevo');
      if (wasOurs || r.reconnect) { S.session.connected = false; await connectTo(S.session.url || targetById('opcua-py').url); }
    }
  } catch (e) { toast(e.message, true); $('#save-status').textContent = ''; }
  finally { S.applying = false; busy(btn, false); refreshServer(); }
}

/* ------------------------------------------------------------------ cliente: sesión */
function targetById(id) { return S.targets.find(t => t.id === id); }
function setChipSession() {
  const c = $('#chip-session'); const s = S.session;
  const who = (S.targets.find(t => t.url === s.url) || {}).id || s.url;
  c.textContent = s.connected ? `${who}${s.security && s.security.policy !== 'None' ? ' · ' + s.security.mode : ''}` : 'OPC UA';
  c.className = 'chip' + (s.connected ? ' ok live' : '');
  c.title = s.connected ? `sesión con ${secDesc(s.security)}` : 'sin sesión';
}
function showPy(res, resultLine) {
  const lines = String(res.asyncua || '').split('\n').map(l => `&gt;&gt;&gt; ${esc(l)}`).join('\n');
  const tail = res.error ? `<span class="bad">${esc(res.error)}</span>` : `<span class="c"># ${esc(resultLine || 'OK')}${res.elapsed_ms !== undefined ? ` · ${res.elapsed_ms} ms` : ''}</span>`;
  $('#pyline').innerHTML = `${lines}\n${tail}`;
  const msgs = res.messages || [];
  S.lastOp = new Set(msgs.map(m => m.n));
  ingest(msgs);
  $('#op-msgs').innerHTML = msgs.length ? `<div class="lbl" style="margin:4px 0 2px">Mensajes de esta operación (${msgs.length})</div>` + msgs.map(msgRow).join('') : '';
}
function secDesc(sec) { return !sec || sec.policy === 'None' ? 'None · anónimo' : `${sec.policy} · ${sec.mode}${sec.user ? ' · usuario ' + sec.user : ' · anónimo'}`; }
async function connectTo(url) {
  const btn = $('#btn-connect'); busy(btn, true);
  try {
    const policy = $('#sec-policy').value, mode = policy === 'None' ? 'None' : ($('#sec-mode').value === 'None' ? 'SignAndEncrypt' : $('#sec-mode').value);
    const r = await api('/api/connect', { url, interval: +$('#interval').value, policy, mode, user: $('#sec-user').value.trim(), password: $('#sec-pass').value });
    $('#sec-current').textContent = `sesión con ${secDesc(r.security)}`;
    S.session = r; S.msgs = []; S.lastSeen = 0; S.live = {}; S.liveMap = {}; setChipSession();
    showPy(r, `True · ${r.namespaces.length} namespaces: ${r.namespaces.slice(0, 4).join(' · ')}${r.namespaces.length > 4 ? ' …' : ''}`);
    toast(`Conectado a ${url}`);
    loadTree('i=85');
    if (opcuaPy()) await watchModel();
  } catch (e) { S.session = { connected: false }; setChipSession(); toast(e.message, true); }
  finally { busy(btn, false); }
}
async function watchModel() {
  try {
    const r = await api('/api/watch/model', {});
    S.liveMap = r.map || {};
    showPy(r, `suscripción creada · ${Object.keys(S.liveMap).length} variables del modelo vigiladas${r.rejected?.length ? ` · ${r.rejected.length} no existen aún en el servidor` : ''}`);
  } catch (e) { toast(e.message, true); }
}
function sessionLost() {
  S.session = { ...S.session, connected: false }; setChipSession(); updateLive();
  toast('Se perdió la sesión OPC UA (¿se reinició el servidor?): pulse «Conectar».', true);
}

/* ------------------------------------------------------------------ cliente: navegar */
function treeItem(c) {
  const leaf = c.cls === 'Method';
  return `<li data-node="${esc(c.node)}"><div class="tn"><span class="tg">${leaf ? '·' : '▸'}</span><span class="nc ${esc(c.cls)}">${esc(c.cls)}</span><span>${esc(c.name)}</span><span class="nid">${esc(c.node)}</span></div></li>`;
}
async function loadTree(root) {
  $('#tree').innerHTML = `<ul>${treeItem({ node: root, name: root === 'i=85' ? 'Objects' : root === 'i=84' ? 'Root' : 'Server', cls: 'Object' })}</ul>`;
  await expand($('#tree li'));
}
async function expand(li) {
  const tg = li.querySelector('.tg');
  if (li.querySelector('ul')) { li.querySelector('ul').remove(); tg.textContent = '▸'; return; }
  try {
    const r = await api('/api/browse?node=' + encodeURIComponent(li.dataset.node));
    showPy(r, `${r.children.length} hijos`);
    if (!r.children.length) { tg.textContent = '·'; return; }
    tg.textContent = '▾';
    li.insertAdjacentHTML('beforeend', `<ul>${r.children.map(treeItem).join('')}</ul>`);
  } catch (e) { toast(e.message, true); }
}
async function selectNode(node) {
  $('#node-input').value = node; $('#node-id').textContent = node;
  $$('#tree .tn.sel').forEach(x => x.classList.remove('sel'));
  const li = $(`#tree li[data-node="${CSS.escape(node)}"] > .tn`); if (li) li.classList.add('sel');
  try {
    const r = await api('/api/node?node=' + encodeURIComponent(node));
    const val = r.attrs.find(a => a.attr === 'Value');
    const ncls = (r.attrs.find(a => a.attr === 'NodeClass') || {}).value; S.nodeClass[node] = ncls;
    $('#call-row').classList.toggle('hidden', ncls !== 'Method');
    if (ncls === 'Method') $('#call-info').textContent = S.parentOf[node] ? `objeto ${S.parentOf[node]} · sin argumentos de entrada` : 'seleccione el método desde el árbol para conocer su objeto';
    animNode(node, 'ReadRequest', 'rd');
    showPy(r, `${r.attrs.filter(a => a.status.startsWith('Good')).length} de ${r.attrs.length} atributos con valor`);
    $('#attrs').innerHTML = '<thead><tr><th>Atributo</th><th>Valor</th></tr></thead><tbody>' + r.attrs.map(a => {
      let v = a.value;
      if (a.attr === 'Value' && v) v = `${typeof v.Value === 'object' ? JSON.stringify(v.Value) : v.Value} · ${v.VariantType}<br><span class="gr small">Source ${v.SourceTimestamp || '—'}</span>`;
      else v = v === null ? `<span class="gr">${esc(a.status)}</span>` : esc(typeof v === 'object' ? JSON.stringify(v) : v);
      return `<tr><td>${a.attr}</td><td class="mono">${v}</td></tr>`;
    }).join('') + '</tbody>';
    $('#write-row').classList.toggle('hidden', !r.writable);
    $('#write-type').textContent = val?.value ? `tipo ${val.value.VariantType} · UserAccessLevel permite Write` : '';
    if (r.writable && val?.value) $('#write-val').value = typeof val.value.Value === 'object' ? '' : val.value.Value;
  } catch (e) { toast(e.message, true); }
}
async function writeNode(node, value) {
  animNode(node, 'WriteRequest', 'wr');
  const r = await api('/api/write', { node, value });
  showPy(r, r.ok ? `escrito ${JSON.stringify(r.written)} (${r.variant}) · WriteResponse Good` : '');
  if (!r.ok) toast(r.error, true);
  return r;
}

/* ------------------------------------------------------------------ cliente: suscripción */
function renderWatch(items) {
  $('#watch tbody').innerHTML = items.length ? items.map(it => `<tr><td class="mono">${esc(it.label !== it.node ? it.label : it.node)}<br><span class="gr small">${esc(it.node)}${it.sampling || it.queue > 1 || it.deadband ? ` · sampling ${it.sampling} · queue ${it.queue}${it.deadband ? ' · deadband ' + it.deadband : ''}` : ''}</span></td>
    <td class="mono">${esc(typeof it.value === 'object' && it.value !== null ? JSON.stringify(it.value) : fmtVal(it.value))}</td><td>${sparkline(S.hist[it.node])}</td><td class="small">${esc(it.status)}</td>
    <td class="small mono">${esc((it.source_ts || '').replace('T', ' ').slice(0, 23))}</td><td class="mono">${it.count}</td>
    <td><button class="ibtn" data-unwatch="${esc(it.node)}" title="Quitar">✕</button></td></tr>`).join('')
    : '<tr><td colspan="7" class="gr">Nada vigilado: seleccione un nodo y pulse «Vigilar» (con opcua-py, las variables del modelo se vigilan solas).</td></tr>';
}
async function poll() {
  try {
    const w = await api('/api/watch');
    if (S.session.connected && !w.session.connected && !S.applying) sessionLost();
    const lv = {}; w.items.forEach(it => { lv[it.label] = it; const h = S.hist[it.node] || (S.hist[it.node] = []); if (typeof it.value === 'number' || typeof it.value === 'boolean') { const v = +it.value; if (!h.length || h[h.length - 1].c !== it.count) { h.push({ v, c: it.count }); if (h.length > 60) h.shift(); } } });
    S.live = lv; updateLive(); renderWatch(w.items);
    const m = await api('/api/messages?since=' + S.lastSeen);
    ingest(m.messages);
  } catch (e) { /* el backend se está reiniciando */ }
}

/* ------------------------------------------------------------------ mensajes */
function msgRow(m) {
  const sv = m.service || m.type;
  return `<div class="msg${S.msgSel === m.n ? ' sel' : ''}${S.lastOp.has(m.n) ? ' last' : ''}" data-msg="${m.n}"><span class="n">#${m.n}</span><span class="d ${m.dir === 'query' ? 'q' : 'r'}">${m.dir === 'query' ? '→' : '←'}</span><span class="ty ${esc(m.type)}">${esc(m.type)}</span><span class="sv">${esc(sv)}</span><span class="sm">${esc(m.summary || '')}</span><span class="sz">${m.size} B</span></div>`;
}
function ingest(list) {
  if (!list || !list.length) return;
  const known = new Set(S.msgs.map(m => m.n));
  list.forEach(m => { if (!known.has(m.n)) { S.msgs.push(m); if (!m.bg) tableAdd(m); } S.lastSeen = Math.max(S.lastSeen, m.n); });
  if (S.msgs.length > 600) S.msgs.splice(0, S.msgs.length - 600);
  renderMsgs(); renderSeq();
}
const isBg = m => !!m.bg;   // Publish de la suscripción y keep-alive del cliente (marcados por el backend)
function renderMsgs() {
  const hide = $('#hide-publish').checked;
  const shown = S.msgs.filter(m => !hide || !isBg(m));
  $('#msgs-count').textContent = `${S.msgs.length} mensajes` + (hide ? ` · ${S.msgs.length - shown.length} de fondo ocultos` : '');
  if (!$('#t-msgs').classList.contains('on')) return;
  const box = $('#msglist'); const atEnd = box.scrollTop + box.clientHeight >= box.scrollHeight - 30;
  box.innerHTML = shown.length ? shown.map(msgRow).join('') : '<div class="note" style="padding:8px">Sin mensajes: conéctese y opere en «Cliente asyncua».</div>';
  if (atEnd) box.scrollTop = box.scrollHeight;
}
function jsonHtml(o, ind) {
  ind = ind || '';
  if (o === null || o === undefined) return '<span class="v">null</span>';
  if (typeof o === 'string') return `<span class="s">"${esc(o)}"</span>`;
  if (typeof o !== 'object') return `<span class="v">${esc(String(o))}</span>`;
  const arr = Array.isArray(o); const ks = arr ? o.map((_, i) => i) : Object.keys(o);
  if (!ks.length) return arr ? '[]' : '{}';
  const n = ind + '  ';
  return (arr ? '[' : '{') + '\n' + ks.map(k => n + (arr ? '' : `<span class="k">${esc(k)}</span>: `) + jsonHtml(o[k], n)).join(',\n') + '\n' + ind + (arr ? ']' : '}');
}
function showMsg(n) {
  const m = S.msgs.find(x => x.n === n); if (!m) return;
  S.msgSel = n; $$('.msg.sel').forEach(x => x.classList.remove('sel')); $$(`.msg[data-msg="${n}"]`).forEach(x => x.classList.add('sel'));
  const bytes = m.hex.split(' '); const cls = new Array(bytes.length).fill('body'); const name = new Array(bytes.length).fill('');
  (m.fields || []).forEach((f, fi) => { for (let i = f.from; i < Math.min(f.to, bytes.length); i++) { cls[i] = f.cls; name[i] = f.name; } });
  const LIM = 360;
  const bh = bytes.slice(0, LIM).map((b, i) => `<span class="by ${cls[i]}" title="${esc(name[i])} · byte ${i}">${b}</span>`).join('') + (bytes.length > LIM || m.truncated ? ` <span class="gr">… ${m.size - LIM} bytes más</span>` : '');
  $('#msg-title').innerHTML = `#${m.n} · ${m.dir === 'query' ? 'cliente → servidor' : 'servidor → cliente'} · <code>${esc(m.type)}</code> ${esc(m.service || '')}`;
  $('#msg-detail').innerHTML = `
    <p class="note">${m.dir === 'query' ? 'Enviado por el cliente asyncua de esta web' : 'Recibido del servidor'} · ${m.size} bytes · ${new Date(m.t * 1000).toLocaleTimeString()}${m.error ? ` · <b>no se pudo decodificar:</b> ${esc(m.error)}` : ''}</p>
    ${GLOSS[(m.service || m.type || '').replace(/(Request|Response)$/, '')] ? `<div class="banner ok small"><b>${esc(m.service || m.type)}:</b> ${GLOSS[(m.service || m.type).replace(/(Request|Response)$/, '')]}</div>` : ''}
    <div class="bytes">${bh}</div>
    <table class="tabla small"><thead><tr><th>Campo</th><th>Bytes</th><th>Valor</th></tr></thead><tbody>${(m.fields || []).map(f => `<tr data-hl="${f.from}-${f.to}"><td>${esc(f.name)}</td><td class="mono">${f.from}–${f.to - 1}</td><td class="mono">${esc(f.value)}</td></tr>`).join('')}</tbody></table>
    ${m.body ? `<div class="lbl" style="margin-top:10px">Cuerpo decodificado · ${esc(m.service)}</div><div class="jtree">${jsonHtml(m.body)}</div>` : ''}`;
  $$('#msg-detail tr[data-hl]').forEach(tr => {
    const [a, b] = tr.dataset.hl.split('-').map(Number);
    tr.onmouseenter = () => $$('#msg-detail .by').forEach((el, i) => el.classList.toggle('hl', i >= a && i < b));
    tr.onmouseleave = () => $$('#msg-detail .by.hl').forEach(el => el.classList.remove('hl'));
  });
}
function openTab(id) {
  $$('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === id));
  $$('.tab').forEach(t => t.classList.toggle('on', t.id === id));
  if (id === 't-msgs') renderMsgs();
}

/* ------------------------------------------------------------------ eventos */
function bind() {
  $$('#tabs button').forEach(b => b.onclick = () => openTab(b.dataset.tab));
  $('#aspace').addEventListener('click', async e => {
    const t = e.target;
    if (t.closest('input')) return;
    const del = t.closest('[data-del-obj]'); if (del) { e.stopPropagation(); delObj(+del.dataset.delObj); return; }
    const av = t.closest('[data-add-var]'); if (av) { addVar(+av.dataset.addVar); return; }
    if (t.closest('#btn-add-obj')) { addObj(); return; }
    const tg = t.closest('[data-toggle]');
    if (tg) {
      const label = tg.dataset.toggle; const node = S.liveMap[label];
      if (!node || !S.session.connected) { toast('Conéctese a opcua-py (pestaña «Cliente asyncua») para escribir: la variable debe existir en el servidor en marcha.', true); return; }
      busy(tg, true); try { await writeNode(node, !(S.live[label]?.value === true)); } catch (x) { toast(x.message, true); } finally { busy(tg, false); }
      return;
    }
    const wb = t.closest('[data-wbtn]');
    if (wb) {
      const label = wb.dataset.wbtn; const node = S.liveMap[label]; const inp = $(`[data-wval="${CSS.escape(label)}"]`);
      if (!node || !S.session.connected) { toast('Conéctese a opcua-py (pestaña «Cliente asyncua») para escribir: la variable debe existir en el servidor en marcha.', true); return; }
      busy(wb, true); try { await writeNode(node, inp.value); } catch (x) { toast(x.message, true); } finally { busy(wb, false); }
      return;
    }
    const s = t.closest('[data-sel]');
    if (s) {
      const [k, i, j] = s.dataset.sel.split(':');
      select(k === 'srv' ? { k } : k === 'obj' ? { k, i: +i } : { k, i: +i, j: +j });
      if (k === 'var' && S.liveMap[`${S.model.objetos[+i].nombre}.${S.model.objetos[+i].variables[+j].nombre}`] && S.session.connected) $('#node-input').value = S.liveMap[`${S.model.objetos[+i].nombre}.${S.model.objetos[+i].variables[+j].nombre}`];
    }
  });
  $('#sel-form').addEventListener('click', e => { const av = e.target.closest('[data-add-var]'); if (av) addVar(+av.dataset.addVar); });
  $('#code-only').onchange = renderCode;
  $('#btn-m-disk').onclick = () => loadModel(S.disk.model);
  $('#btn-m-default').onclick = () => loadModel(S.def);
  $('#btn-m-empty').onclick = () => loadModel({ servidor: clone(S.model.servidor), objetos: [] });
  $('#btn-save').onclick = async e => { busy(e.target, true); try { await save(); toast('Guardado: opcua/modelo.json y opcua/server.py'); } catch (x) { toast(x.message, true); } finally { busy(e.target, false); } };
  $('#btn-apply').onclick = e => apply(e.target);

  $('#target').onchange = () => {
    const t = targetById($('#target').value);
    $('#custom-row').classList.toggle('hidden', !!t);
    $('#target-note').textContent = t ? `${t.url} · ${t.note}` : 'Cualquier servidor alcanzable desde la red ot-lab (172.28.0.x) o por nombre de servicio.';
  };
  $('#btn-connect').onclick = () => { const t = targetById($('#target').value); connectTo(t ? t.url : $('#custom-url').value.trim()); };
  $('#btn-disconnect').onclick = async () => {
    try { const r = await api('/api/disconnect', {}); showPy(r, 'sesión cerrada'); } catch (x) { toast(x.message, true); }
    S.session = { connected: false }; S.live = {}; setChipSession(); updateLive(); renderWatch([]);
  };
  $$('[data-root]').forEach(b => b.onclick = () => { if (!S.session.connected) return toast('Conéctese primero.', true); loadTree(b.dataset.root); });
  $('#tree').addEventListener('click', e => {
    const li = e.target.closest('li'); if (!li) return;
    const pli = li.parentElement && li.parentElement.closest('li'); if (pli) S.parentOf[li.dataset.node] = pli.dataset.node;
    if (e.target.closest('.tg')) expand(li); else selectNode(li.dataset.node);
  });
  $('#tree').addEventListener('dblclick', e => { const li = e.target.closest('li'); if (li) expand(li); });
  const need = () => { if (!S.session.connected) { toast('Conéctese primero.', true); return null; } const n = $('#node-input').value.trim(); if (!n) toast('Indique un NodeId.', true); return n || null; };
  $('#btn-attrs').onclick = () => { const n = need(); if (n) selectNode(n); };
  $('#btn-read').onclick = async () => {
    const n = need(); if (!n) return;
    animNode(n, 'ReadRequest', 'rd');
    try { const r = await api('/api/read', { node: n }); showPy(r, r.value ? `${JSON.stringify(r.value.Value)} · ${r.value.VariantType} · ${r.value.Status}` : ''); } catch (x) { toast(x.message, true); }
  };
  $('#btn-write').onclick = async e => { const n = need(); if (!n) return; busy(e.target, true); try { await writeNode(n, $('#write-val').value); } catch (x) { toast(x.message, true); } finally { busy(e.target, false); } };
  $('#btn-watch').onclick = async () => {
    const n = need(); if (!n) return;
    try { const r = await api('/api/watch', { node: n, sampling: +$('#w-sampling').value || 0, queue: +$('#w-queue').value || 1, deadband: +$('#w-deadband').value || null }); showPy(r, r.rejected.length ? 'el servidor rechazó el MonitoredItem' : 'MonitoredItem creado: los cambios llegan en PublishResponse'); } catch (x) { toast(x.message, true); }
  };
  $('#watch').addEventListener('click', async e => {
    const b = e.target.closest('[data-unwatch]'); if (!b) return;
    try { const r = await api('/api/unwatch', { node: b.dataset.unwatch }); if (r.asyncua) showPy(r, 'MonitoredItem eliminado'); } catch (x) { toast(x.message, true); }
  });
  $('#hide-publish').onchange = renderMsgs;
  $('#btn-msgs-clear').onclick = async () => { const r = await api('/api/messages/clear', {}); S.msgs = []; S.lastSeen = r.last; renderMsgs(); $('#msg-detail').innerHTML = '<span class="gr">Pulse un mensaje de la lista.</span>'; };
  document.addEventListener('click', e => {
    const m = e.target.closest('[data-msg]'); if (!m) return;
    if (m.closest('#op-msgs')) openTab('t-msgs');
    showMsg(+m.dataset.msg);
  });
}

async function init() {
  bind();
  const r = await api('/api/model');
  S.types = r.types; S.def = r.default;
  S.disk = { model: clone(r.model), code: r.code_disk };
  S.model = clone(r.model);
  bindServerForm(); renderAspace(); renderSel(); await preview();
  if (r.source !== 'modelo.json') toast(`Modelo: ${r.source}`);
  refreshServer();
  const t = await api('/api/targets'); S.targets = t.targets; S.session = t.session;
  $('#target').innerHTML = t.targets.map(x => `<option value="${x.id}">${esc(x.label)}</option>`).join('') + '<option value="custom">personalizado…</option>';
  $('#target').onchange(); setChipSession();
  S.policies = t.policies || ['None'];
  $('#sec-policy').innerHTML = S.policies.map(pn => `<option value="${pn}">${pn}</option>`).join('');
  $('#sec-policy').onchange = () => { const none = $('#sec-policy').value === 'None'; $('#sec-mode').disabled = none; if (!none && $('#sec-mode').value === 'None') $('#sec-mode').value = 'SignAndEncrypt'; if (none) $('#sec-mode').value = 'None'; };
  $('#sec-policy').onchange();
  if (S.session.connected) { $('#sec-current').textContent = `sesión con ${secDesc(S.session.security)}`; loadTree('i=85'); if (opcuaPy()) watchModel(); }
  bindExtras(); layoutInit(); drawerInit(); zoomInit(); capRefresh(); capList();
  setInterval(poll, 700);
  setInterval(refreshServer, 5000);
  setInterval(capRefresh, 3000);
}
init().catch(e => toast(e.message, true));


/* ================================================================== glosario de servicios (una línea por servicio, en español) */
const GLOSS = {
  Hello: 'primer mensaje del cliente: propone tamaños de buffer y de mensaje y dice a qué EndpointUrl quiere hablar.',
  Acknowledge: 'el servidor acepta (o recorta) los tamaños propuestos en Hello; desde aquí ambos saben cuánto puede medir un chunk.',
  OpenSecureChannel: 'abre el canal seguro: política (None, Basic256Sha256…) y modo (None, Sign, SignAndEncrypt); con None todo lo que sigue viaja en claro.',
  CloseSecureChannel: 'cierra el canal seguro al desconectar.',
  GetEndpoints: 'pregunta al servidor qué endpoints ofrece (políticas, modos, tokens de usuario) sin abrir sesión: es lo que hace UaExpert al descubrir.',
  CreateSession: 'crea la sesión sobre el canal: nombre de aplicación, certificado del cliente y timeout; el servidor devuelve el SessionId y su AuthenticationToken.',
  ActivateSession: 'activa la sesión e identifica al usuario (AnonymousIdentityToken o UserNameIdentityToken): a partir de aquí se puede leer y escribir.',
  CloseSession: 'cierra la sesión.',
  Browse: 'navega el espacio de direcciones: pide las referencias (hijos) de un nodo; la respuesta trae NodeId, BrowseName, DisplayName y NodeClass de cada uno.',
  Read: 'lee atributos de nodos (normalmente Value): la respuesta es un DataValue con valor, StatusCode y marcas de tiempo.',
  Write: 'escribe atributos; el servidor contesta con un StatusCode por nodo (Good o Bad…, p. ej. BadUserAccessDenied).',
  Call: 'ejecuta un método del servidor con argumentos de entrada y recibe los de salida.',
  CreateSubscription: 'crea una suscripción con su PublishingInterval: el cajón donde el servidor acumula las notificaciones.',
  CreateMonitoredItems: 'añade variables a la suscripción con SamplingInterval, QueueSize y filtro (banda muerta).',
  DeleteMonitoredItems: 'quita variables de la suscripción.',
  Publish: 'el cliente deja PublishRequest pendientes y el servidor responde con PublishResponse cuando hay cambios (o keep-alive): no hay sondeo de valores.',
  ServiceFault: 'el servidor no pudo atender la petición: el ResponseHeader lleva el StatusCode del error.',
};

/* ================================================================== animación sobre el dibujo */
function animRow(label, text, cls) {
  const el = $(`#aspace [data-live="${CSS.escape(label)}"]`); if (!el) return;
  const row = el.closest('.var'); if (!row) return;
  row.classList.remove('hit-rd', 'hit-wr', 'hit-pub'); void row.offsetWidth; row.classList.add('hit-' + cls);
  const pill = document.createElement('span'); pill.className = 'pill ' + cls; pill.textContent = text; row.appendChild(pill);
  setTimeout(() => pill.remove(), 1300);
}
function animNode(node, text, cls) { const label = Object.keys(S.liveMap).find(k => S.liveMap[k] === node); if (label) animRow(label, text, cls); }

/* ================================================================== minigráfica de la suscripción */
function sparkline(h) {
  if (!h || h.length < 2) return '<span class="gr small">—</span>';
  const vs = h.map(x => x.v); const lo = Math.min(...vs), hi = Math.max(...vs); const W = 120, H = 26;
  const pts = vs.map((v, i) => `${(i / (vs.length - 1) * W).toFixed(1)},${(hi === lo ? H / 2 : H - 2 - (v - lo) / (hi - lo) * (H - 4)).toFixed(1)}`).join(' ');
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}"><polyline points="${pts}"/><circle cx="${W}" cy="${pts.split(' ').pop().split(',')[1]}" r="2.5"/></svg><span class="gr small"> ${vs.length} muestras · ${fmtVal(lo)}…${fmtVal(hi)}</span>`;
}

/* ================================================================== tabla a entregar */
function tableAdd(m) {
  const row = { n: m.n, hora: new Date(m.t * 1000).toLocaleTimeString('es-EC', { hour12: false }), dir: m.dir === 'query' ? 'cliente → servidor' : 'servidor → cliente', tipo: m.type, servicio: m.service || '', resumen: m.summary || '', bytes: m.size };
  S.optable.push(row); if (S.optable.length > 500) S.optable.shift();
  const tb = $('#optable tbody'); if (!tb) return;
  const tr = document.createElement('tr'); tr.className = 'new ' + (m.dir === 'query' ? 'q' : 'r');
  tr.innerHTML = `<td>${row.n}</td><td class="mono">${row.hora}</td><td><span class="tr-${m.dir === 'query' ? 'q' : 'r'}">${m.dir === 'query' ? 'Request' : 'Response'}</span><br><span class="gr small">${row.dir}</span></td><td class="mono">${esc(row.tipo)}</td><td>${esc(row.servicio)}</td><td class="mono small">${esc(row.resumen)}</td><td class="mono">${row.bytes}</td>`;
  tb.prepend(tr); while (tb.children.length > 500) tb.lastChild.remove();
}
function tableCsv() {
  const head = ['#', 'hora', 'sentido', 'tipo', 'servicio', 'resumen', 'bytes'];
  const rows = S.optable.map(r => [r.n, r.hora, r.dir, r.tipo, r.servicio, r.resumen, r.bytes].map(v => `"${String(v).replace(/"/g, '""')}"`).join(','));
  const blob = new Blob(['﻿' + [head.join(','), ...rows].join('\n')], { type: 'text/csv' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'tabla_opcua.csv'; a.click();
}

/* ================================================================== diagrama de secuencia */
function renderSeq() {
  const svg = $('#seq'); if (!svg) return;
  const mode = ($('input[name=seqmode]:checked') || {}).value || 'handshake';
  let list = S.msgs.filter(m => !m.bg);
  if (mode === 'handshake') {
    const start = list.map(m => m.type).lastIndexOf('HEL');
    const sub = start >= 0 ? list.slice(start) : list;
    const end = sub.findIndex(m => m.service === 'ActivateSessionResponse');
    list = end >= 0 ? sub.slice(0, end + 1) : sub.slice(0, 8);
  } else list = list.slice(-14);
  const ROW = 34, top = 44, H = top + Math.max(1, list.length) * ROW + 16, L = 150, R = 610;
  let h = `<text class="life" x="${L}" y="26" text-anchor="middle">cliente asyncua</text><text class="life" x="${R}" y="26" text-anchor="middle">servidor</text>
    <line class="ll" x1="${L}" y1="34" x2="${L}" y2="${H - 6}"/><line class="ll" x1="${R}" y1="34" x2="${R}" y2="${H - 6}"/>`;
  if (!list.length) h += `<text class="gr" x="380" y="${top + 16}" text-anchor="middle" font-size="14">sin mensajes todavía: conéctese en «Cliente asyncua»</text>`;
  list.forEach((m, i) => {
    const y = top + i * ROW; const q = m.dir === 'query';
    const dt = i ? ((m.t - list[i - 1].t) * 1000).toFixed(0) + ' ms' : '';
    h += `<g class="arr ${q ? 'q' : 'r'}${S.msgSel === m.n ? ' sel' : ''}" data-msg="${m.n}"><line x1="${q ? L : R}" y1="${y}" x2="${q ? R - 8 : L + 8}" y2="${y}" marker-end="url(#${q ? 'sq' : 'sr'})"/>
      <text x="380" y="${y - 6}" text-anchor="middle">${esc(m.service || m.type)}<tspan class="sm"> ${esc((m.summary || '').slice(0, 42))}</tspan></text>
      <text class="dt" x="${R + 14}" y="${y + 4}">${m.size} B${dt ? ' · +' + dt : ''}</text></g>`;
  });
  svg.setAttribute('viewBox', `0 0 760 ${H}`);
  svg.innerHTML = `<defs><marker id="sq" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="#002856"/></marker><marker id="sr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="#A51008"/></marker></defs>` + h;
}

/* ================================================================== captura → Wireshark */
function capRender(c) {
  S.capRunning = !!c.running;
  const chip = $('#chip-capture'); if (!chip) return;
  chip.textContent = c.running ? `Captura · ${c.seconds}s · ${c.bytes} B` : (c.file ? `Captura · ${c.file}` : 'Captura');
  chip.className = 'chip' + (c.running ? ' bad rec' : (c.file ? ' ok' : ''));
  $('#cap-status').textContent = c.running ? `tcpdump activo · ${c.file} · ${c.bytes} bytes` : (c.file ? `detenida · ${c.file} · ${c.bytes} bytes` : (c.tcpdump ? 'lista para capturar (puertos 4840, 50000, 62541)' : 'tcpdump no disponible'));
  const ready = !c.running && c.file && c.bytes > 24;
  $('#cap-ready').classList.toggle('hidden', !ready);
  if (ready) $('#btn-wireshark').href = `/api/capture/file/${c.file}`;
  $('#btn-cap-start').disabled = c.running; $('#btn-cap-stop').disabled = !c.running;
}
async function capRefresh() { try { capRender(await api('/api/capture')); } catch (e) { } }
async function capList() { try { const j = await api('/api/capture/list'); $('#cap-files').innerHTML = j.files.length ? j.files.map(f => `<li><a href="/api/capture/file/${f.name}" download>${esc(f.name)}</a><span class="gr mono small">${f.bytes} B · ${f.mtime.replace('T', ' ')}</span></li>`).join('') : '<li class="gr small">todavía ninguna · están en ot-lab/captures/</li>'; } catch (e) { } }

/* ================================================================== extras: endpoints, call, captura, tabla, secuencia */
function bindExtras() {
  $('#btn-endpoints').onclick = async e => {
    const t = targetById($('#target').value); const url = t ? t.url : $('#custom-url').value.trim();
    busy(e.target, true);
    try {
      const r = await api('/api/endpoints?url=' + encodeURIComponent(url));
      showPy(r, `${r.endpoints.length} endpoints`);
      const tb = $('#endpoints tbody'); $('#endpoints').classList.remove('hidden');
      tb.innerHTML = r.endpoints.map(ep => `<tr class="${ep.policy === 'None' ? 'acc-r' : 'acc-rw'}"><td>${esc(ep.policy)}</td><td>${esc(ep.mode)}</td><td class="mono">${ep.level}</td><td>${ep.tokens.map(x => esc(x)).join(' · ')}</td><td><button class="btn mini gris" data-useep="${esc(ep.policy)}|${esc(ep.mode)}">usar</button></td></tr>`).join('') || '<tr><td colspan="5" class="gr">el servidor no devolvió endpoints</td></tr>';
      tb.querySelectorAll('[data-useep]').forEach(b => b.onclick = () => { const [pn, md] = b.dataset.useep.split('|'); if (S.policies.includes(pn)) { $('#sec-policy').value = pn; $('#sec-policy').onchange(); $('#sec-mode').value = md === 'None' ? 'None' : md; toast(`Seguridad ${pn} · ${md} seleccionada: pulse Conectar`); } else toast(`La política ${pn} no está disponible en este cliente`, true); });
    } catch (x) { toast(x.message, true); } finally { busy(e.target, false); }
  };
  $('#btn-call').onclick = async e => {
    const n = $('#node-input').value.trim(); const obj = S.parentOf[n];
    if (!obj) return toast('Seleccione el método desde el árbol (necesito saber a qué objeto pertenece).', true);
    busy(e.target, true);
    try { const r = await api('/api/call', { obj, method: n, args: [] }); showPy(r, r.ok ? `CallResponse · salida ${JSON.stringify(r.output)}` : ''); if (!r.ok) toast(r.error, true); }
    catch (x) { toast(x.message, true); } finally { busy(e.target, false); }
  };
  $('#aspace').addEventListener('click', async e => {
    const b = e.target.closest('[data-call]'); if (!b) return;
    if (!S.session.connected || !opcuaPy()) return toast('Conéctese a opcua-py para llamar al método.', true);
    const obj = `ns=2;s=${b.dataset.call}`, met = `${obj}.Reiniciar`;
    busy(b, true);
    try { const r = await api('/api/call', { obj, method: met, args: [] }); showPy(r, r.ok ? `CallResponse · reiniciadas ${JSON.stringify(r.output)}` : ''); if (!r.ok) toast(r.error === 'BadNodeIdUnknown' ? 'El método aún no existe en el servidor: guarde y reinicie opcua-py.' : r.error, true); }
    catch (x) { toast(x.message, true); } finally { busy(b, false); }
  });
  $('#btn-cap-start').onclick = async e => { busy(e.target, true); try { capRender(await api('/api/capture/start', { ports: [4840, 50000, 62541] })); toast('Capturando: conecte u opere ahora'); } catch (x) { toast(x.message, true); } finally { busy(e.target, false); } };
  $('#btn-cap-stop').onclick = async e => { busy(e.target, true); try { capRender(await api('/api/capture/stop', {})); capList(); toast('Captura detenida: «Abrir en Wireshark»'); } catch (x) { toast(x.message, true); } finally { busy(e.target, false); } };
  $('#btn-csv').onclick = tableCsv;
  $('#btn-tbl-clear').onclick = () => { S.optable = []; $('#optable tbody').innerHTML = ''; };
  $$('input[name=seqmode]').forEach(r => r.onchange = renderSeq);
  $('#seq').addEventListener('click', e => { const g = e.target.closest('[data-msg]'); if (g) { showMsg(+g.dataset.msg); renderSeq(); } });
}

/* ================================================================== disposición: bloques plegables y movibles, pestaña / panel, auto-ocultar, zoom */
const LAYOUT_KEY = 'opcua-layout-v1';
function $$in(sel, root) { return Array.from(root.querySelectorAll(sel)); }
function layoutSave() {
  const lay = {}; $$('[data-drop]').forEach(c => { lay[c.dataset.drop] = $$in(':scope > [data-block]', c).map(b => b.dataset.block); });
  try { localStorage.setItem(LAYOUT_KEY, JSON.stringify(lay)); } catch (e) { }
}
function layoutApply() {
  let lay = null; try { lay = JSON.parse(localStorage.getItem(LAYOUT_KEY) || 'null'); } catch (e) { }
  if (!lay) return;
  for (const [cid, ids] of Object.entries(lay)) { const c = document.querySelector(`[data-drop="${cid}"]`); if (!c) continue; ids.forEach(id => { const b = document.querySelector(`[data-block="${id}"]`); if (b) c.appendChild(b); }); }
}
function layoutInit() {
  let collapsed = []; try { collapsed = JSON.parse(localStorage.getItem('opcua-collapsed') || '[]'); } catch (e) { }
  $$('[data-block]').forEach(b => {
    const bh = document.createElement('div'); bh.className = 'bh';
    const inTab = !!b.closest('.tab');
    bh.innerHTML = `<span class="hd" title="Arrastre para mover este bloque" draggable="true">⠿</span><span class="bt">${esc(b.dataset.title || '')}</span><button class="op col">Ocultar</button>${inTab ? '' : '<button class="op open" title="Abrir este bloque solo, en una pestaña nueva">↗ pestaña</button>'}`;
    b.prepend(bh);
    const ob = bh.querySelector('.open'); if (ob) ob.onclick = () => window.open(`${location.pathname}?block=${encodeURIComponent(b.dataset.block)}`, '_blank');
    const colBtn = bh.querySelector('.col');
    const setCol = on => { b.classList.toggle('collapsed', on); colBtn.textContent = on ? 'Mostrar' : 'Ocultar'; };
    setCol(collapsed.includes(b.dataset.block));
    colBtn.onclick = () => { const on = !b.classList.contains('collapsed'); setCol(on); try { let c = JSON.parse(localStorage.getItem('opcua-collapsed') || '[]'); c = on ? [...new Set([...c, b.dataset.block])] : c.filter(x => x !== b.dataset.block); localStorage.setItem('opcua-collapsed', JSON.stringify(c)); } catch (e) { } };
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
      const m = document.createElement('div'); m.className = 'drop-marker'; if (after) c.insertBefore(m, after); else c.appendChild(m);
    };
    c.ondragleave = e => { if (!c.contains(e.relatedTarget)) c.classList.remove('dropping'); };
    c.ondrop = e => { e.preventDefault(); if (!S.drag) return; const m = c.querySelector(':scope > .drop-marker'); if (m) { c.insertBefore(S.drag, m); m.remove(); } else c.appendChild(S.drag); c.classList.remove('dropping'); layoutSave(); };
  });
  $$('#tabs button[data-tab]').forEach(t => {
    t.ondragenter = e => { if (!S.drag) return; e.preventDefault(); t.classList.add('droptarget'); t.click(); };
    t.ondragover = e => { if (S.drag) e.preventDefault(); };
    t.ondragleave = () => t.classList.remove('droptarget');
    t.ondrop = e => { e.preventDefault(); t.classList.remove('droptarget'); const c = document.getElementById(t.dataset.tab); if (c && S.drag) { c.appendChild(S.drag); layoutSave(); } };
  });
  $('#btn-layout-reset').onclick = () => { try { localStorage.removeItem(LAYOUT_KEY); localStorage.removeItem('opcua-collapsed'); } catch (e) { } location.reload(); };
  layoutApply();
  const qs = new URLSearchParams(location.search); const solo = qs.get('block'); const soloPanel = qs.get('panel');
  if (soloPanel) { document.body.classList.add('solo', 'solo-panel'); $('#solo').appendChild($('#right')); document.title = 'Panel · Explorador OPC UA'; }
  else if (solo) { const b = document.querySelector(`[data-block="${solo}"]`); if (b) { document.body.classList.add('solo'); $('#solo').appendChild(b); document.title = `${b.dataset.title} · Explorador OPC UA`; } }
}
function drawerInit() {
  const KEY = 'opcua-autohide'; const right = $('#right'); let auto = false, timer = null;
  try { auto = localStorage.getItem(KEY) === '1'; } catch (e) { }
  if (new URLSearchParams(location.search).get('panel')) auto = false;
  const apply = () => { document.body.classList.toggle('autohide', auto); right.classList.remove('open'); try { localStorage.setItem(KEY, auto ? '1' : '0'); } catch (e) { } };
  const open = () => { clearTimeout(timer); right.classList.add('open'); };
  const close = ms => { clearTimeout(timer); timer = setTimeout(() => right.classList.remove('open'), ms == null ? 700 : ms); };
  $('#btn-drawer').onclick = () => { auto = true; apply(); };
  $('#rail-pin').onclick = () => { auto = false; apply(); };
  $$('#rail [data-railtab]').forEach(b => b.onclick = () => { openTab(b.dataset.railtab); $$('#rail [data-railtab]').forEach(x => x.classList.toggle('on', x === b)); open(); });
  right.addEventListener('mouseenter', () => { if (auto) open(); });
  right.addEventListener('mouseleave', () => { if (auto) close(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && auto) close(0); });
  apply();
}
function zoomInit() {
  const KEY = 'opcua-zoom'; let z = 1;
  try { z = parseFloat(sessionStorage.getItem(KEY)) || 1; } catch (e) { }
  const apply = () => { z = Math.min(2.5, Math.max(0.5, Math.round(z * 20) / 20)); document.documentElement.style.zoom = z; document.documentElement.style.setProperty('--z', z); $('#zoom-val').textContent = Math.round(z * 100) + ' %'; try { sessionStorage.setItem(KEY, String(z)); } catch (e) { } };
  $('#zoom-in').onclick = () => { z += 0.1; apply(); };
  $('#zoom-out').onclick = () => { z -= 0.1; apply(); };
  $('#zoom-val').onclick = () => { z = 1; apply(); };
  document.addEventListener('keydown', e => { if (!(e.metaKey || e.ctrlKey)) return; if (e.key === '+' || e.key === '=') { e.preventDefault(); z += 0.1; apply(); } else if (e.key === '-') { e.preventDefault(); z -= 0.1; apply(); } else if (e.key === '0') { e.preventDefault(); z = 1; apply(); } });
  document.addEventListener('wheel', e => { if (e.ctrlKey || e.metaKey) { e.preventDefault(); z += e.deltaY < 0 ? 0.05 : -0.05; apply(); } }, { passive: false });
  apply();
}
