"""Control de OpenPLC (panel web :8080) y análisis de su sondeo Modbus (lámina 36).

- Configura OpenPLC como lo haría una persona en el panel: login, subir y compilar
  el .st, (re)crear el Slave Device apuntando a modbus-sim y Start PLC.
- Captura EN VIVO el sondeo de OpenPLC (172.28.0.10 -> 172.28.0.30:5020) con tcpdump
  en Docker, lo decodifica aquí mismo (tabla de la lámina 36) y guarda el pcap.
"""
import base64
import html
import json
import os
import re
import struct
import subprocess
import threading
import time

# El panel se usa DESDE la red Docker (contenedor ot-client -> 172.28.0.10:8080):
# en el host el puerto 8080 lo comparten Docker, wslrelay y otros servicios de
# Windows (p. ej. ApplicationWebServer.exe), y según la IP responde otro servidor.
URL = os.environ.get("OPENPLC_URL", "http://172.28.0.10:8080")
VIA = os.environ.get("OT_CLIENT", "ot-client")
USER = os.environ.get("OPENPLC_USER", "openplc")
PASSWORD = os.environ.get("OPENPLC_PASS", "openplc")
CONTAINER = os.environ.get("OPENPLC_CONTAINER", "openplc")
PLC_IP = os.environ.get("OPENPLC_IP", "172.28.0.10")

# Slave Device de la lámina 36 para los tableros de las láminas 30 y 31
DEVICE = {
    "device_name": "modbus-sim", "device_protocol": "TCP", "device_id": "1",
    "device_ip": "172.28.0.30", "device_port": "5020",
    "device_cport": "", "device_baud": "115200", "device_parity": "None",
    "device_data": "8", "device_stop": "1",
    "di_start": "0", "di_size": "4",      # FC 02 -> %IX100.0..3
    "do_start": "0", "do_size": "5",      # FC 15 -> %QX100.0..4
    "ai_start": "0", "ai_size": "4",      # FC 04 -> %IW100..103
    "aor_start": "0", "aor_size": "5",    # FC 03 -> %IW104..108
    "aow_start": "5", "aow_size": "3",    # FC 16 -> %QW100..102 en HR 5-7 (no pisa las consignas)
}

# Cliente HTTP que corre dentro de ot-client; la cookie de sesión vive en su /tmp.
HTTP_RUNNER = r'''
import sys, json, base64, uuid, urllib.request, urllib.parse, http.cookiejar
a = json.loads(sys.stdin.read())
jar = http.cookiejar.MozillaCookieJar("/tmp/openplc.cookies")
try: jar.load(ignore_discard=True)
except Exception: pass
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
if a.get("files"):
    b = uuid.uuid4().hex; body = b""
    for k, v in (a.get("data") or {}).items():
        body += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    for k, (fn, c) in a["files"].items():
        body += (f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{fn}"\r\n'
                 'Content-Type: application/octet-stream\r\n\r\n').encode() + base64.b64decode(c) + b"\r\n"
    body += f"--{b}--\r\n".encode()
    req = urllib.request.Request(a["url"], body, {"Content-Type": "multipart/form-data; boundary=" + b})
elif a.get("data") is not None:
    req = urllib.request.Request(a["url"], urllib.parse.urlencode(a["data"]).encode())
else:
    req = urllib.request.Request(a["url"])
with op.open(req, timeout=a.get("timeout", 20)) as r:
    sys.stdout.write(r.read().decode("utf-8", "replace"))
jar.save(ignore_discard=True)
'''


# ------------------------------------------------------------- panel web ---
def _req(path, data=None, files=None, timeout=20):
    payload = {"url": URL + path, "data": data, "timeout": timeout,
               "files": {k: [fn, base64.b64encode(c).decode()] for k, (fn, c) in (files or {}).items()}}
    p = subprocess.run(["docker", "exec", "-i", VIA, "python", "-c", HTTP_RUNNER],
                       input=json.dumps(payload), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout + 15)
    if p.returncode != 0:
        raise RuntimeError("panel OpenPLC: " + (p.stderr.strip().splitlines() or ["sin respuesta"])[-1])
    return p.stdout


def login():
    page = _req("/login", {"username": USER, "password": PASSWORD})
    if "Bad credentials" in page or 'name="password"' in page and "Dashboard" not in page:
        raise RuntimeError("OpenPLC rechazó usuario/contraseña")


def _authed(path, **kw):
    page = _req(path, **kw)
    if "name='password'" in page or 'name="password"' in page:  # sesión caducada
        login()
        page = _req(path, **kw)
    return page


def status():
    page = _authed("/dashboard")
    st = re.search(r"Status: <i>(\w+)</i>", page)
    prog = re.search(r"<b>Program:</b>\s*([^<]*)<", page)
    f = re.search(r"<b>File:</b>\s*([^<]*)<", page)
    return {"status": st.group(1) if st else "?", "program": (prog.group(1).strip() if prog else ""),
            "file": (f.group(1).strip() if f else "")}


def _sqlite(sql):
    p = subprocess.run(["docker", "exec", CONTAINER, "sqlite3", "-separator", "|",
                        "/root/OpenPLC_v3/webserver/openplc.db", sql],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip())
    return [ln.split("|") for ln in p.stdout.splitlines() if ln]


def devices():
    cols = ["dev_id", "dev_name", "dev_type", "slave_id", "ip_address", "ip_port", "di_start", "di_size",
            "coil_start", "coil_size", "ir_start", "ir_size", "hr_read_start", "hr_read_size",
            "hr_write_start", "hr_write_size"]
    return [dict(zip(cols, r)) for r in _sqlite(f"SELECT {', '.join(cols)} FROM Slave_dev")]


def configure(st_path, log, before_start=None):
    """Sube y compila el .st, deja un único Slave Device hacia modbus-sim y arranca.

    before_start(): se llama con el PLC detenido (p. ej. recargar el tablero, para que
    no queden los ceros que un Slave Device anterior con escritura dejó en el esclavo).
    """
    login()
    log("login en el panel de OpenPLC ✓")
    _authed("/stop_plc")
    log("Stop PLC ✓")

    with open(st_path, "rb") as f:
        content = f.read()
    page = _authed("/upload-program", files={"file": (os.path.basename(st_path), content)})
    stfile = re.search(r"value='(\d+\.st)' id='prog_file'", page)
    if not stfile:
        raise RuntimeError("no se pudo subir el .st (¿PLC compilando?)")
    stfile = stfile.group(1)
    epoch = re.search(r"value='(\d+)' id='epoch_time'", page).group(1)
    _authed("/upload-program-action", data={"prog_name": "tableros (dashboard)",
                                             "prog_descr": "Laminas 30-31 sondeadas por OpenPLC (lamina 36)",
                                             "prog_file": stfile, "epoch_time": epoch})
    _authed(f"/compile-program?file={stfile}")
    log(f"programa subido como {stfile}; compilando…")
    out = ""
    for _ in range(240):
        time.sleep(1)
        out = _authed("/compilation-logs")
        if "Compilation finished" in out:
            break
    tail = [ln for ln in html.unescape(re.sub(r"<[^>]+>", "\n", out)).splitlines() if ln.strip()][-3:]
    if "finished successfully" not in out:
        raise RuntimeError("compilación fallida: " + " | ".join(tail))
    log("Compilation finished successfully ✓")

    for d in devices():
        same_target = d["ip_address"] == DEVICE["device_ip"] and d["ip_port"] == DEVICE["device_port"]
        if same_target or d["dev_name"] == DEVICE["device_name"]:
            _authed(f"/delete-device?dev_id={d['dev_id']}")
            log(f"borrado Slave Device previo «{d['dev_name']}» (Slave ID {d['slave_id']}, "
                f"{d['ip_address']}:{d['ip_port']}) para no sondear dos veces")
    _authed("/add-modbus-device", data=DEVICE)
    log("Slave Device «modbus-sim» creado: ID 1 · 172.28.0.30:5020 · DI 0/4 · Coils 0/5 · "
        "IR 0/4 · HR read 0/5 · HR write 5/3 ✓")
    if before_start:
        log(before_start())
    st = start()
    log(f"Start PLC → {st['status']} ✓")
    return st


def start():
    try:
        _authed("/start_plc", timeout=8)
    except RuntimeError as e:  # el runtime arranca aunque el panel tarde en responder
        if "timed out" not in str(e):
            raise
    for _ in range(15):
        time.sleep(1)
        st = status()
        if st["status"] == "Running":
            break
    return st


def stop():
    _authed("/stop_plc")
    time.sleep(1)
    return status()


def monitoring():
    _authed("/monitoring")  # carga las variables del .st activo
    page = _authed("/monitor-update")
    rows = []
    for tr in re.findall(r"<tr style=\"height:60px\".*?</tr>", page, re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(tds) < 5:
            continue
        val = re.sub(r"<[^>]+>", " ", tds[4])
        val = " ".join(val.split())
        rows.append({"name": tds[0], "type": tds[1], "loc": tds[2], "value": val})
    return rows


# ------------------------------------------------------- captura en vivo ---
NAMES = {1: "Read Coils", 2: "Read Discrete Inputs", 3: "Read Holding Registers", 4: "Read Input Registers",
         5: "Write Single Coil", 6: "Write Single Register", 15: "Write Multiple Coils",
         16: "Write Multiple Registers"}
TABLE = {2: "Discrete Inputs", 15: "Coils", 4: "Input Registers", 3: "Holding Registers – Read",
         16: "Holding Registers – Write", 1: "Coils (lectura)", 5: "Coils", 6: "Holding Registers – Write"}


def _packet_frames(pkt, link, t, port):
    """ADU Modbus contenidas en un paquete capturado."""
    l2 = 14 if link == 1 else 16 if link == 113 else 20 if link == 276 else 0
    ip = pkt[l2:]
    if len(ip) < 20 or ip[0] >> 4 != 4 or ip[9] != 6:
        return []
    tcp = ip[(ip[0] & 15) * 4:]
    sport, dport = struct.unpack(">HH", tcp[:4])
    data = tcp[(tcp[12] >> 4) * 4:]
    out = []
    while len(data) >= 8:  # puede haber varias ADU en un segmento
        tid, _, ln = struct.unpack(">HHH", data[:6])
        adu, data = data[:6 + ln], data[6 + ln:]
        q = dport == port
        out.append({"t": t, "dir": "Q" if q else "R", "cport": sport if q else dport, "tid": tid,
                    "fc": adu[7] if len(adu) > 7 else None, "hex": " ".join(f"{b:02X}" for b in adu)})
    return out


class Live:
    """tcpdump continuo (contenedor ot-plcsniff) -> tramas decodificadas en memoria + pcap."""
    NAME = "ot-plcsniff"

    def __init__(self):
        self.proc, self.thread = None, None
        self.frames, self.raw = [], bytearray()
        self.t0, self.error, self.port = None, None, 5020
        self.lock = threading.Lock()

    @property
    def running(self):
        return bool(self.proc and self.proc.poll() is None)

    def start(self, iface, port):
        self.stop()
        subprocess.run(["docker", "rm", "-f", self.NAME], capture_output=True)
        self.frames, self.raw, self.t0, self.error, self.port = [], bytearray(), time.time(), None, port
        self.proc = subprocess.Popen(
            ["docker", "run", "--rm", "--name", self.NAME, "--net", "host", "nicolaka/netshoot",
             "tcpdump", "-i", iface, "-U", "-w", "-", f"host {PLC_IP} and tcp port {port}"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.proc.stdout.read(n - len(buf))
            if not chunk:
                raise EOFError
            buf += chunk
        return buf

    def _read(self):
        try:
            hdr = self._exact(24)
            self.raw += hdr
            nsec = hdr[:4] in (b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d")
            e = "<" if hdr[:4] in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1") else ">"
            link = struct.unpack(e + "I", hdr[20:24])[0]
            while True:
                rec = self._exact(16)
                ts, tf, incl, _ = struct.unpack(e + "IIII", rec)
                pkt = self._exact(incl)
                fr = _packet_frames(pkt, link, ts + tf / (1e9 if nsec else 1e6), self.port)
                with self.lock:
                    self.raw += rec + pkt
                    self.frames.extend(fr)
                    if len(self.frames) > 60000:
                        del self.frames[:10000]
        except EOFError:
            pass
        except Exception as ex:  # noqa: BLE001
            self.error = str(ex)

    def stop(self, save_path=None):
        if self.proc:
            subprocess.run(["docker", "stop", "-t", "2", self.NAME], capture_output=True)
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            if self.thread:
                self.thread.join(timeout=5)
        self.proc = None
        if save_path and len(self.raw) > 24:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(bytes(self.raw))
            return len(self.raw)
        return 0

    def snapshot(self):
        with self.lock:
            return list(self.frames)


def _decode(fc, q, r):
    """Valor interpretado: lecturas desde la Response, escrituras desde la Query."""
    qb = bytes.fromhex(q.replace(" ", "")) if q else b""
    rb = bytes.fromhex(r.replace(" ", "")) if r else b""
    if rb and rb[0] >= 0x80:
        return f"excepción código {rb[1]:02X}"
    if fc in (1, 2) and len(rb) >= 3 and len(qb) >= 5:
        n = struct.unpack(">H", qb[3:5])[0]
        return str([int(bool(rb[2 + i // 8] >> (i % 8) & 1)) for i in range(n) if 2 + i // 8 < len(rb)])
    if fc in (3, 4) and len(rb) >= 2:
        return str([struct.unpack(">H", rb[2 + i:4 + i])[0] for i in range(0, rb[1], 2)])
    if fc == 15 and len(qb) >= 7:
        n = struct.unpack(">H", qb[3:5])[0]
        return f"byte 0x{qb[6]:02X} → " + str([int(bool(qb[6 + i // 8] >> (i % 8) & 1)) for i in range(n)])
    if fc == 16 and len(qb) >= 6:
        return str([struct.unpack(">H", qb[6 + i:8 + i])[0] for i in range(0, qb[5], 2)])
    if fc in (5, 6) and len(qb) >= 5:
        return qb[3:5].hex(" ").upper()
    return ""


def analyze(frames, t0, window=5.0):
    """Tabla de la lámina 36 y respuestas a sus preguntas, sobre los últimos `window` s."""
    pdu = lambda h: " ".join(h.split()[7:])
    now = time.time()
    resp = {(f["cport"], f["tid"]): f for f in frames if f["dir"] == "R"}
    qs_all = [f for f in frames if f["dir"] == "Q"]
    qs = [f for f in qs_all if f["t"] >= now - window]
    span = max(0.5, min(window, now - (qs[0]["t"] if qs else now)))

    rows, order = {}, []
    for q in qs:
        r = resp.get((q["cport"], q["tid"]))
        row = rows.get(q["fc"])
        if not row:
            row = rows[q["fc"]] = {"fc": q["fc"], "name": NAMES.get(q["fc"], f"FC {q['fc']}"),
                                   "table": TABLE.get(q["fc"], ""), "n": 0, "ts": [], "q": "", "r": "",
                                   "lost": 0}
            order.append(q["fc"])
        row["n"] += 1
        row["ts"].append(q["t"])
        if r:
            row["q"], row["r"] = pdu(q["hex"]), pdu(r["hex"])
        elif q["t"] < now - 1.5:
            row["lost"] += 1
            row["q"] = row["q"] or pdu(q["hex"])
    out = []
    for fc in order:
        row = rows[fc]
        ts = row.pop("ts")
        row["per_s"] = round(row["n"] / span, 1)
        row["period_ms"] = round(1000 * (ts[-1] - ts[0]) / (len(ts) - 1)) if len(ts) > 1 else None
        row["value"] = _decode(fc, row["q"], row["r"])
        row["where"] = "Response" if fc in (1, 2, 3, 4) else "Query"
        out.append(row)

    # ciclos: corte cada vez que reaparece la primera FC del orden
    cycles, cur = [], []
    first = order[0] if order else None
    for q in qs:
        if q["fc"] == first and cur:
            cycles.append(cur)
            cur = []
        cur.append(q)
    seqs = {tuple(f["fc"] for f in c) for c in cycles}
    last_cycle = []
    if cycles:
        c = cycles[-1]
        keys = {(f["cport"], f["tid"]) for f in c}
        last_cycle = [f for f in frames if (f["cport"], f["tid"]) in keys and f["t"] >= c[0]["t"] - 0.01]
    starts = [c[0]["t"] for c in cycles]
    cyc_ms = round(1000 * (starts[-1] - starts[0]) / (len(starts) - 1)) if len(starts) > 1 else None

    # conexiones TCP y Transaction ID sobre toda la captura
    conns = []
    for q in qs_all:
        if not conns or conns[-1]["cport"] != q["cport"]:
            conns.append({"cport": q["cport"], "since": round(q["t"] - t0, 1), "tid_first": q["tid"], "n": 0})
        conns[-1]["n"] += 1
        conns[-1]["tid_last"] = q["tid"]
    tids = [q["tid"] for q in qs]
    tid_seq = all((b - a) % 65536 == 1 for a, b in zip(tids, tids[1:]))

    # cambios de valor: «la primera Response con el valor nuevo». Una FC que cambia en
    # casi todos los ciclos (contador del PLC) se resume aparte para no tapar el resto.
    changes, last, nq = [], {}, {}
    for q in qs_all:
        nq[q["fc"]] = nq.get(q["fc"], 0) + 1
        r = resp.get((q["cport"], q["tid"]))
        v = _decode(q["fc"], pdu(q["hex"]), pdu(r["hex"]) if r else "")
        if v and last.get(q["fc"]) != v:
            if q["fc"] in last:
                changes.append({"t": round(q["t"] - t0, 2), "fc": q["fc"], "from": last[q["fc"]], "to": v})
            last[q["fc"]] = v
    per_fc = {}
    for c in changes:
        per_fc[c["fc"]] = per_fc.get(c["fc"], 0) + 1
    counters = [fc for fc, n in per_fc.items() if n > 5 and n > 0.5 * nq.get(fc, 1)]
    changes = [c for c in changes if c["fc"] not in counters]

    # huecos en el sondeo (simulador caído, PLC detenido…)
    gaps = [{"t": round(a["t"] - t0, 1), "s": round(b["t"] - a["t"], 1)}
            for a, b in zip(qs_all, qs_all[1:]) if b["t"] - a["t"] > 1.0]
    return {
        "rows": out, "cycle": last_cycle, "window": window, "elapsed": round(now - t0, 1),
        "n_queries": len(qs_all), "per_cycle": len(cycles[-1]) if cycles else len(qs),
        "same_order": len(seqs) <= 1, "order": [f["fc"] for f in cycles[-1]] if cycles else [],
        "cycle_ms": cyc_ms, "cycles_per_s": round(len(cycles) / span, 1) if cycles else 0,
        "conns": conns[-6:], "n_conns": len(conns), "tid_seq": tid_seq,
        "tid_now": tids[-1] if tids else None, "changes": changes[-12:], "counters": counters,
        "gaps": gaps[-6:],
        "silent_s": round(now - qs_all[-1]["t"], 1) if qs_all else None,
        "lost": sum(r["lost"] for r in out),
    }


