"""Dashboard OT-Lab: cada acción ejecuta pymodbus DENTRO de Docker y captura todo.

Flujo de cada ejecución:
  1. docker exec -i ot-client python -   (cliente pymodbus en la red ot-lab_ot-lab)
     -> consola tipo ">>>" + tramas TX/RX reales (trace_packet)
  2. docker logs --since T0 modbus-sim   -> lo que vio el esclavo (recv/send)
  3. lectura de las 4 tablas              -> estado para la topología

Escenarios (scenarios.py): «Cargar tablero» escribe ot-lab/modbus/server.json y
reinicia modbus-sim, igual que el paso 1 de cada reto.

Uso (dos formas, ver README.md):
  - Con el laboratorio:  docker compose -f docker-compose.yml -f docker-compose.dashboard.yml up -d
  - En el PC:            python app.py          (solo stdlib; necesita el CLI de docker)
  ->  http://localhost:8000
"""
import json
import os
import subprocess
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import openplc_ctl as plc
from scenarios import SCENARIOS

HERE = os.path.dirname(os.path.abspath(__file__))
# ot-lab/dashboard/.. = ot-lab (en el contenedor se pasa OT_LAB=/ot-lab con ./modbus y ./captures montados)
OT_LAB = os.path.abspath(os.environ.get("OT_LAB", os.path.join(HERE, "..")))
SERVER_JSON = os.path.join(OT_LAB, "modbus", "server.json")
CAPTURES = os.path.join(OT_LAB, "captures")

CLIENT = os.environ.get("OT_CLIENT", "ot-client")
CAPTURER = "ot-cap"
NETWORK = os.environ.get("OT_NETWORK", "ot-lab_ot-lab")
SLAVE = os.environ.get("OT_SLAVE", "modbus-sim")
TARGET_IP = os.environ.get("MODBUS_HOST", "172.28.0.30")
TARGET_PORT = int(os.environ.get("MODBUS_PORT", "5020"))
WEB_PORT = int(os.environ.get("WEB_PORT", "8000"))
# 127.0.0.1 en el PC. En el contenedor 0.0.0.0, y el compose publica solo en 127.0.0.1:8000.
WEB_HOST = os.environ.get("WEB_HOST", "127.0.0.1")

_BY_SCN = {s["id"]: s for s in SCENARIOS}

# Script que corre dentro de ot-client. argv: <json sentencias> <op|state>
RUNNER = r'''
import sys, json, datetime, traceback
from pymodbus.client import ModbusTcpClient
stmts, mode, ip = json.loads(sys.argv[1]), sys.argv[2], sys.argv[3]
def tr(sending, data):
    print("#FRAME", "TX" if sending else "RX", " ".join(f"{b:02X}" for b in data), flush=True)
    return data
c = ModbusTcpClient(ip, port=%(port)d, timeout=2, retries=0, trace_packet=tr if mode == "op" else None)
if not c.connect():
    print("#ERR no conecta con " + ip + ":%(port)d", flush=True); sys.exit(1)
print("#T0", datetime.datetime.now(datetime.timezone.utc).strftime("%%Y-%%m-%%dT%%H:%%M:%%S.%%fZ"), flush=True)
if mode == "state":
    def bits(r): return None if r.isError() else [int(b) for b in r.bits[:8]]
    def regs(r): return None if r.isError() else list(r.registers)
    print("#STATE", json.dumps({
        "co": bits(c.read_coils(0, count=8, device_id=1)),
        "di": bits(c.read_discrete_inputs(0, count=8, device_id=1)),
        "ir": regs(c.read_input_registers(0, count=8, device_id=1)),
        "hr": regs(c.read_holding_registers(0, count=8, device_id=1))}), flush=True)
else:
    g = {"c": c}
    for s in stmts:
        print(">>> " + s, flush=True)
        try:
            try:
                code = compile(s, "<stdin>", "eval")
            except SyntaxError:
                exec(compile(s, "<stdin>", "exec"), g)
            else:
                r = eval(code, g)
                if r is not None:
                    print(repr(r), flush=True)
        except Exception:
            traceback.print_exc(file=sys.stdout)
            sys.stdout.flush()
c.close()
''' % {"port": TARGET_PORT}

_lock = threading.Lock()
HISTORY = []  # ejecuciones capturadas (para exportar evidencia)
PLC_LIVE = plc.Live()
PLC_PROGRAMS = os.path.join(HERE, "openplc")
CAPTURE = {"file": None}


# --------------------------------------------------------------- Docker ---
def sh(args, stdin=None, timeout=30):
    p = subprocess.run(args, input=stdin, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def ensure_client():
    rc, out, _ = sh(["docker", "inspect", "-f", "{{.State.Running}}", CLIENT])
    if rc == 0 and out.strip() == "true":
        return
    if rc == 0:
        sh(["docker", "start", CLIENT])
    else:
        sh(["docker", "run", "-d", "--name", CLIENT, "--network", NETWORK, "python:3.12-slim",
            "sh", "-c", "pip -q install pymodbus==3.12.1 && touch /tmp/ready && sleep infinity"])
    for _ in range(90):
        if sh(["docker", "exec", CLIENT, "test", "-f", "/tmp/ready"])[0] == 0:
            return
        time.sleep(2)
    raise RuntimeError(f"{CLIENT} no quedó listo (pip install pymodbus)")


def exec_runner(stmts, mode):
    # Las sentencias van desde ot-client por la red (lo que se captura). La lectura de
    # estado para la topología corre dentro de modbus-sim por loopback: no ensucia
    # Wireshark ni el pcap. Si la imagen del esclavo no tuviera pymodbus, usa ot-client.
    where, ip = (SLAVE, "127.0.0.1") if mode == "state" and _slave_py() else (CLIENT, TARGET_IP)
    rc, out, err = sh(["docker", "exec", "-i", where, "python", "-", json.dumps(stmts), mode, ip], stdin=RUNNER)
    t0, state, steps = None, None, []
    for line in out.splitlines():
        if line.startswith("#T0 "):
            t0 = line[4:].strip()
        elif line.startswith("#STATE "):
            state = json.loads(line[7:])
        elif line.startswith("#ERR "):
            raise RuntimeError(line[5:])
        elif line.startswith("#FRAME "):
            _, d, hexs = line.split(" ", 2)
            if steps:
                steps[-1]["frames"].append({"dir": d, "hex": hexs})
        elif line.startswith(">>> "):
            steps.append({"stmt": line[4:], "out": [], "frames": []})
        elif steps:
            steps[-1]["out"].append(line)
    if rc != 0 and not steps and state is None:
        raise RuntimeError((err or out).strip() or f"docker exec rc={rc}")
    return t0, state, steps


_SLAVE_PY = {}


def _slave_py():
    if "ok" not in _SLAVE_PY:
        _SLAVE_PY["ok"] = sh(["docker", "exec", SLAVE, "python", "-c", "import pymodbus.client"])[0] == 0
    return _SLAVE_PY["ok"]


def slave_logs(since):
    if not since:
        return []
    time.sleep(0.15)  # deja que el esclavo vacíe su log
    _, out, err = sh(["docker", "logs", "--since", since, SLAVE])
    return [ln for ln in (out + err).splitlines() if ln.strip()]


def read_state(retries=1):
    for i in range(retries):
        try:
            return exec_runner([], "state")[1]
        except RuntimeError:
            if i == retries - 1:
                raise
            time.sleep(1)


# ---------------------------------------------------- Análisis de tramas ---
READ_FC = {1, 2, 3, 4}


def pdu(hexs):
    return " ".join(hexs.split()[7:])  # quita MBAP (7 bytes)


def exc_fc(frame):
    return int(frame["hex"].split()[7], 16) >= 0x80


def analyze(st):
    """Fila de la tabla de lámina 32 para una sentencia ejecutada."""
    tx = next((f for f in st["frames"] if f["dir"] == "TX"), None)
    rx = next((f for f in st["frames"] if f["dir"] == "RX"), None)
    result = st["out"][-1].strip() if st["out"] else ""
    if not tx:
        err = next((ln.strip() for ln in reversed(st["out"]) if "Error" in ln), result)
        return {"fc": None, "where": "—", "pdu_tx": "", "pdu_rx": "", "value": err,
                "note": "no salió trama: el cliente la rechazó antes de enviar"}
    fc = int(tx["hex"].split()[7], 16)
    rx_fc = int(rx["hex"].split()[7], 16) if rx else None
    exc = rx_fc is not None and rx_fc >= 0x80
    if result.startswith("<pymodbus"):  # escritura: el repr del objeto no aporta
        result = "OK · eco del esclavo" if rx and not exc_fc(rx) else result
    row = {"fc": fc, "where": "Response" if fc in READ_FC else "Query",
           "pdu_tx": pdu(tx["hex"]), "pdu_rx": pdu(rx["hex"]) if rx else "",
           "value": result, "note": ""}
    if exc:
        code = int(rx["hex"].split()[8], 16)
        row["note"] = f"excepción: FC 0x{rx_fc:02X}, código {code:02X}"
    return row


def evaluate(steps, checks):
    res = []
    for ck in checks or []:
        i = ck["i"]
        if i >= len(steps):
            res.append({**ck, "ok": False, "got": "(no ejecutada)"})
            continue
        st = steps[i]
        oks, got = [], []
        if "out" in ck:
            o = st["out"][-1].strip() if st["out"] else ""
            oks.append(o == ck["out"])
            got.append(o)
        if "pdu" in ck:
            f = next((f for f in st["frames"] if f["dir"] == ck["dir"]), None)
            p = pdu(f["hex"]) if f else ""
            oks.append(p == ck["pdu"])
            got.append(p)
        res.append({**ck, "ok": all(oks), "got": " · ".join(got)})
    return res


def run_stmts(stmts, label, checks=None, scenario=None):
    with _lock:
        ensure_client()
        t_start = time.time()
        t0, _, steps = exec_runner(stmts, "op")
        logs = slave_logs(t0)
        state = read_state()
    for st in steps:
        st["row"] = analyze(st)
    entry = {"n": len(HISTORY) + 1, "ts": time.strftime("%H:%M:%S"), "label": label,
             "scenario": scenario, "steps": steps, "logs": logs, "state": state,
             "checks": evaluate(steps, checks), "ms": round((time.time() - t_start) * 1000)}
    HISTORY.append(entry)
    return entry


# ------------------------------------------------------------- Tableros ---
def _board_of(regs):
    return {k: regs.get(k, {}) for k in ("discreteInput", "coils", "inputRegister", "holdingRegister")}


def _norm(board):
    return {k: {str(a): v for a, v in (board.get(k) or {}).items()}
            for k in ("discreteInput", "coils", "inputRegister", "holdingRegister")}


def active_scenario():
    try:
        with open(SERVER_JSON, encoding="utf-8") as f:
            regs = json.load(f).get("registers", {})
    except (OSError, ValueError):
        return None
    cur = _norm(_board_of(regs))
    return next((s["id"] for s in SCENARIOS if _norm(s["board"]) == cur), None)


def write_board(board, description):
    """Escribe «registers» en server.json y reinicia modbus-sim (paso 1 de cada reto)."""
    with open(SERVER_JSON, encoding="utf-8") as f:
        raw = f.read()
    bak = SERVER_JSON + ".bak"
    if not os.path.exists(bak):
        with open(bak, "w", encoding="utf-8") as f:
            f.write(raw)
    cfg = json.loads(raw)
    cfg.setdefault("server", {}).setdefault("logging", {})["logLevel"] = "DEBUG"  # lámina 19
    cfg["registers"] = {"description": description + " Claves = dirección pymodbus + 1 (lámina 20).",
                        "initializeUndefinedRegisters": True, **board}
    with open(SERVER_JSON, "w", encoding="utf-8", newline="\n") as f:  # LF, como pide el repo
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    rc, _, err = sh(["docker", "restart", SLAVE], timeout=60)
    if rc != 0:
        raise RuntimeError(err.strip())
    ensure_client()
    return read_state(retries=15)


def load_board(scn_id):
    s = _BY_SCN[scn_id]
    with _lock:
        state = write_board(s["board"], f"Dashboard · {s['title']} (láminas {s['slides']}).")
    HISTORY.append({"n": len(HISTORY) + 1, "ts": time.strftime("%H:%M:%S"), "scenario": scn_id,
                    "label": f"Cargar tablero «{s['title']}» · docker restart {SLAVE}",
                    "board": s["board"], "steps": [], "logs": [], "state": state, "checks": [], "ms": 0})
    return {"ok": True, "state": state, "active": scn_id, "entry": HISTORY[-1]}


def field_change(ir=None, di=None):
    """Simula el campo: cambia sensores (IR) o pulsadores (DI), que Modbus no deja escribir.

    Conserva coils y holding actuales (p. ej. una consigna cambiada por el operador),
    escribe server.json y reinicia modbus-sim. El maestro (OpenPLC) se reconecta solo.
    """
    with _lock:
        cur = read_state()
        di_v, ir_v = list(cur["di"]), list(cur["ir"])
        for a, v in (di or {}).items():
            di_v[int(a)] = 1 if v else 0
        for a, v in (ir or {}).items():
            ir_v[int(a)] = int(v)
        board = {
            "discreteInput": {str(i + 1): bool(v) for i, v in enumerate(di_v[:4])},
            "coils": {str(i + 1): bool(v) for i, v in enumerate(cur["co"][:5])},
            "inputRegister": {str(i + 1): v for i, v in enumerate(ir_v[:4])},
            "holdingRegister": {str(i + 1): v for i, v in enumerate(cur["hr"][:8])},
        }
        state = write_board(board, "Dashboard · cambio de campo (OpenPLC, lámina 36).")
    parts = [f"IR {a} = {v}" for a, v in (ir or {}).items()] + [f"DI {a} = {int(bool(v))}" for a, v in (di or {}).items()]
    HISTORY.append({"n": len(HISTORY) + 1, "ts": time.strftime("%H:%M:%S"), "scenario": "openplc",
                    "label": "Campo: " + ", ".join(parts) + f" · docker restart {SLAVE}",
                    "board": board, "steps": [], "logs": [], "state": state, "checks": [], "ms": 0})
    return {"ok": True, "state": state, "entry": HISTORY[-1]}


def slave_outage(seconds):
    """Lámina 36: «deténganlo 5 s con docker compose stop modbus-sim». En segundo plano."""
    def go():
        sh(["docker", "stop", SLAVE], timeout=60)
        time.sleep(seconds)
        sh(["docker", "start", SLAVE], timeout=60)
    threading.Thread(target=go, daemon=True).start()
    return {"ok": True, "seconds": seconds}


# ------------------------------------------------------- Captura pcapng ---
# Se captura en el puente de la red ot-lab (netns del host de Docker), no en el eth0
# de modbus-sim: «Cargar tablero» reinicia modbus-sim y su eth0 desaparece
# («pcap_loop: The interface disappeared»); el puente sobrevive y ve todo ot-lab.
LIVE = "ot-ws"
WIRESHARK_EXE = os.environ.get("WIRESHARK_EXE", r"C:\Program Files\Wireshark\Wireshark.exe")
_live = {"procs": None}


_BRIDGE = {}


def bridge_iface():
    if "name" not in _BRIDGE:  # la red no cambia mientras corre el dashboard
        _, out, _ = sh(["docker", "network", "inspect", NETWORK, "-f",
                        '{{index .Options "com.docker.network.bridge.name"}}|{{.Id}}'])
        name, _, nid = out.strip().partition("|")
        _BRIDGE["name"] = name if name and name != "<no value>" else "br-" + nid[:12]
    return _BRIDGE["name"]


def ensure_netshoot():
    if sh(["docker", "image", "inspect", "nicolaka/netshoot"])[0] != 0:
        rc, _, err = sh(["docker", "pull", "nicolaka/netshoot"], timeout=900)
        if rc != 0:
            raise RuntimeError(err.strip())


def tcpdump_cmd(name, out, detach=False):
    # detach (grabar pcap): sin --rm, el archivo se saca con docker cp al detener.
    # Un bind mount de Windows pierde las últimas tramas si el contenedor se para.
    return ["docker", "run", *(["-d"] if detach else ["--rm"]), "--name", name, "--net", "host",
            "nicolaka/netshoot", "tcpdump", "-i", bridge_iface(), "-U", "-w", out, f"tcp port {TARGET_PORT}"]


def capture_start(name):
    name = "".join(ch for ch in name if ch.isalnum() or ch in "-_") or "captura"
    with _lock:
        ensure_netshoot()
        sh(["docker", "rm", "-f", CAPTURER])
        os.makedirs(CAPTURES, exist_ok=True)
        fname = f"{name}.pcapng"
        rc, _, err = sh(tcpdump_cmd(CAPTURER, "/tmp/cap.pcapng", detach=True))
        if rc != 0:
            raise RuntimeError(err.strip())
        CAPTURE["file"] = fname
    return {"ok": True, "capture": capture_status()}


def capture_stop():
    with _lock:
        f, CAPTURE["file"] = CAPTURE["file"], None
        path = os.path.join(CAPTURES, f) if f else None
        sh(["docker", "stop", "-t", "3", CAPTURER])  # SIGTERM: tcpdump cierra el archivo
        if path:
            rc, _, err = sh(["docker", "cp", f"{CAPTURER}:/tmp/cap.pcapng", path])
            if rc != 0:
                raise RuntimeError(err.strip())
        sh(["docker", "rm", "-f", CAPTURER])
    size = os.path.getsize(path) if path and os.path.exists(path) else 0
    return {"ok": True, "saved": path, "bytes": size, "capture": capture_status()}


def wireshark_mode():
    """wsl (preferido) | windows | none. En el contenedor no hay pantalla: WIRESHARK_MODE=none."""
    if "mode" not in _live:
        want = os.environ.get("WIRESHARK_MODE", "wsl")
        if want == "none":
            _live["mode"] = "none"
            return "none"
        has_wsl = want == "wsl" and sh(["wsl", "-e", "sh", "-c", "command -v wireshark"])[0] == 0
        _live["mode"] = "wsl" if has_wsl or not os.path.exists(WIRESHARK_EXE) else "windows"
    return _live["mode"]


def live_running(cleanup=True):
    # docker ps y no docker inspect: inspect se cuelga si la tubería hacia Wireshark se bloqueó
    try:
        _, out, _ = sh(["docker", "ps", "-q", "--filter", f"name=^{LIVE}$"], timeout=5)
    except subprocess.TimeoutExpired:
        return False
    if not out.strip():
        return False
    if not cleanup or time.time() - _live.get("t", 0) < 30:  # gracia: Wireshark tarda en abrir
        return True
    if wireshark_mode() == "none":  # lo lanzó otra instancia (en el PC): no es nuestro
        return True
    # Contenedor sin Wireshark al otro lado (ventana cerrada o que nunca abrió): huérfano.
    # Se borra, porque con la tubería rota Docker termina bloqueándose sobre él.
    if wireshark_mode() == "wsl":
        alive = sh(["wsl", "-e", "sh", "-c", f"pgrep -f 'name {LIVE} ' >/dev/null && pgrep -x wireshark >/dev/null"],
                   timeout=10)[0] == 0
    else:
        alive = any(p.poll() is None for p in (_live.get("procs") or ()))
    if not alive:
        try:
            sh(["docker", "rm", "-f", LIVE], timeout=20)
        except subprocess.TimeoutExpired:
            pass
    return alive


def live_start():
    """Wireshark en vivo (lámina 25): tcpdump en Docker | Wireshark del PC leyendo stdin."""
    if wireshark_mode() == "none":
        raise RuntimeError(
            "el dashboard corre en un contenedor y no puede abrir ventanas. Desde una terminal WSL: "
            f"docker run --rm --net host nicolaka/netshoot tcpdump -i {bridge_iface()} -U -w - "
            f"\"tcp port {TARGET_PORT}\" | wireshark -k -i - -o mbtcp.tcp.port:{TARGET_PORT}  "
            "(o use «Grabar pcap» y abra el archivo de ot-lab/captures)")
    if live_running():
        return {"ok": True, "capture": capture_status()}
    ensure_netshoot()
    sh(["docker", "rm", "-f", LIVE])
    ws_args = ["-k", "-i", "-", "-o", f"mbtcp.tcp.port:{TARGET_PORT}"]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if wireshark_mode() == "wsl":  # Wireshark de WSL (WSLg), como en la lámina 25
        # Sesión WSL nueva: el grupo wireshark ya aplica. Solo lee la tubería (-i -): no ve el PC.
        pipe = " ".join(f"'{a}'" for a in tcpdump_cmd(LIVE, "-")) + " | wireshark " + " ".join(ws_args)
        _live["procs"] = (subprocess.Popen(["wsl", "-e", "bash", "-lc", pipe], creationflags=flags,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),)
    else:  # Wireshark de Windows
        dump = subprocess.Popen(tcpdump_cmd(LIVE, "-"), stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, creationflags=flags)
        ws = subprocess.Popen([WIRESHARK_EXE, *ws_args], stdin=dump.stdout)
        dump.stdout.close()  # si se cierra Wireshark, tcpdump recibe SIGPIPE y el contenedor se borra
        _live["procs"] = (dump, ws)
    _live["t"] = time.time()
    for _ in range(20):
        if live_running(cleanup=False):
            break
        time.sleep(0.5)
    return {"ok": True, "capture": capture_status()}


def live_stop():
    # Primero se corta la tubería (si Wireshark dejó de leer, el docker run queda bloqueado
    # y Docker no responde sobre ese contenedor); luego se borra. Wireshark queda abierto.
    if wireshark_mode() == "wsl":
        sh(["wsl", "-e", "sh", "-c", f"pkill -9 -f 'name {LIVE} '"], timeout=10)
    for proc in _live.get("procs") or ():
        proc.kill()
    try:
        sh(["docker", "rm", "-f", LIVE], timeout=20)
    except subprocess.TimeoutExpired:
        pass
    _live["procs"] = None
    return {"ok": True, "capture": capture_status()}


def capture_status():
    return {"recording": bool(CAPTURE["file"]), "file": CAPTURE["file"], "dir": CAPTURES,
            "live": live_running(), "iface": bridge_iface(),
            "wireshark": {"wsl": "wsl:wireshark", "none": "no disponible en contenedor"}.get(wireshark_mode(), WIRESHARK_EXE)}


# ------------------------------------------------------------- Exportar ---
def export_md():
    o = ["# Evidencia OT-Lab · Práctica 1a", "",
         f"Cliente `{CLIENT}` (python:3.12-slim + pymodbus 3.12.1, red `{NETWORK}`) → "
         f"esclavo `{SLAVE}` {TARGET_IP}:{TARGET_PORT}, unit 1. Generado por el dashboard.", ""]
    for e in HISTORY:
        o += [f"## {e['n']}. {e['label']} · {e['ts']}", ""]
        if e.get("plc_log"):
            o += [f"- {ln}" for ln in e["plc_log"]] + [""]
        if e.get("plc"):
            a = e["plc"]
            o += ["**Tabla lámina 36 · una fila por tabla configurada en el Slave Device:**", "",
                  "| Tabla en OpenPLC | FC | Veces / s | Periodo | PDU Query → Response | Valor |",
                  "|---|---|---|---|---|---|"]
            for r in a["rows"]:
                o.append(f"| {r['table']} | {r['fc']:02d} | {r['per_s']} | {r['period_ms']} ms | "
                         f"`{r['q']}` → `{r['r']}` | {r['value']} |")
            o += ["", f"- Query por ciclo: **{a['per_cycle']}**, orden `{a['order']}`, "
                      f"{'siempre el mismo' if a['same_order'] else 'NO siempre el mismo'}.",
                  f"- Periodo de ciclo: **{a['cycle_ms']} ms** (~{a['cycles_per_s']} ciclos/s).",
                  f"- Conexiones TCP en la captura: **{a['n_conns']}**; Transaction ID "
                  f"{'consecutivo' if a['tid_seq'] else 'con saltos/reinicios'} (último {a['tid_now']}).",
                  f"- Query sin Response (últimos {a['window']} s): {a['lost']}.", ""]
            if a["conns"]:
                o += ["| Puerto cliente | Desde (s) | TID primero → último | Query |", "|---|---|---|---|"]
                o += [f"| {c['cport']} | {c['since']} | {c['tid_first']} → {c['tid_last']} | {c['n']} |"
                      for c in a["conns"]] + [""]
            if a.get("gaps"):
                o += ["**Huecos en el sondeo (> 1 s sin Query):**", ""]
                o += [f"- t={g['t']} s · {g['s']} s sin tráfico" for g in a["gaps"]] + [""]
            if a["changes"]:
                o += ["**Cambios de valor en la red:**", ""]
                o += [f"- t={c['t']} s · FC {c['fc']:02d}: `{c['from']}` → `{c['to']}`" for c in a["changes"]] + [""]
            if a["cycle"]:
                o += ["**Un ciclo completo (MBAP + PDU):**", "", "```"]
                o += [f"{'Q' if f['dir'] == 'Q' else 'R'}  {f['hex']}" for f in a["cycle"]] + ["```", ""]
        if e.get("board"):
            o += ["Tablero cargado en `server.json` (clave = dirección + 1):", "", "```json",
                  json.dumps(e["board"], ensure_ascii=False, indent=2), "```", ""]
        if e["steps"]:
            o += ["**Consola (cliente en Docker):**", "", "```python"]
            for st in e["steps"]:
                o += [">>> " + st["stmt"], *st["out"]]
            o += ["```", "",
                  "| Petición | FC | Datos en | PDU Query | PDU Response | Valor |",
                  "|---|---|---|---|---|---|"]
            for st in e["steps"]:
                r = st["row"]
                fc = f"{r['fc']:02d}" if r["fc"] is not None else "—"
                val = (r["value"] + (f" ({r['note']})" if r["note"] else "")).replace("|", "\\|")
                o.append(f"| `{st['stmt']}` | {fc} | {r['where']} | `{r['pdu_tx']}` | `{r['pdu_rx']}` | {val} |")
            o += ["", "**Tramas completas (MBAP + PDU):**", "", "```"]
            for st in e["steps"]:
                o += [f"{f['dir']}  {f['hex']}" for f in st["frames"]]
            o += ["```", ""]
        if e["checks"]:
            o += ["**Predicción vs captura:**", ""]
            for ck in e["checks"]:
                exp = " · ".join(x for x in (ck.get("out"), ck.get("pdu") and f"{ck['dir']} {ck['pdu']}") if x)
                o.append(f"- {'✅' if ck['ok'] else '❌'} sentencia {ck['i'] + 1}: esperado `{exp}` → obtenido `{ck['got']}`")
            o.append("")
        if e["logs"]:
            o += [f"**Log del esclavo (`docker logs {SLAVE}`):**", "", "```", *e["logs"], "```", ""]
        if e["state"]:
            s = e["state"]
            o += ["**Estado del esclavo tras la acción:**", "",
                  f"- Coils 0-7: `{s['co']}`", f"- Discrete inputs 0-7: `{s['di']}`",
                  f"- Input registers 0-7: `{s['ir']}`", f"- Holding registers 0-7: `{s['hr']}`", ""]
    return "\n".join(o)


# ----------------------------------------------------------------- HTTP ---
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype, code=200, extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8", code)

    def _guard(self, fn):
        try:
            self._json(fn())
        except Exception as e:  # noqa: BLE001
            self._json({"ok": False, "error": str(e)})

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                self._send(f.read(), "text/html; charset=utf-8")
        elif self.path.startswith("/marca/"):  # logos oficiales UCUENCA | DEET (solo .svg de esa carpeta)
            name = os.path.basename(self.path)
            path = os.path.join(HERE, "marca", name)
            if not name.endswith(".svg") or not os.path.isfile(path):
                return self.send_error(404)
            with open(path, "rb") as f:
                self._send(f.read(), "image/svg+xml", extra={"Cache-Control": "max-age=3600"})
        elif self.path == "/api/config":
            self._json({"target": f"{CLIENT} → {SLAVE} {TARGET_IP}:{TARGET_PORT} · unit 1",
                        "scenarios": SCENARIOS, "active": active_scenario(),
                        "capture": capture_status()})
        elif self.path == "/api/state":
            self._guard(lambda: {"ok": True, "state": read_state(), "active": active_scenario()})
        elif self.path == "/api/plc/status":
            self._guard(lambda: {"ok": True, "status": plc.status(), "devices": plc.devices(),
                                 "live": PLC_LIVE.running, "device_cfg": plc.DEVICE})
        elif self.path.startswith("/api/plc/live"):
            def go():
                win = float(urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("w", ["5"])[0])
                return {"ok": True, "running": PLC_LIVE.running, "error": PLC_LIVE.error,
                        "a": plc.analyze(PLC_LIVE.snapshot(), PLC_LIVE.t0 or time.time(), window=win)}
            self._guard(go)
        elif self.path == "/api/plc/monitor":
            self._guard(lambda: {"ok": True, "vars": plc.monitoring()})
        elif self.path == "/api/history":
            self._json({"ok": True, "history": HISTORY})
        elif self.path == "/api/export.md":
            self._send(export_md(), "text/markdown; charset=utf-8",
                       extra={"Content-Disposition": 'attachment; filename="evidencia_practica1a.md"'})
        else:
            self.send_error(404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) or b"{}"
        try:  # el navegador manda UTF-8; algunos clientes (PowerShell 5) mandan Latin-1
            body = json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError:
            body = json.loads(raw.decode("latin-1"))
        except ValueError as e:
            return self._json({"ok": False, "error": f"JSON inválido: {e}"}, 400)
        p = self.path
        if p == "/api/step":
            s = _BY_SCN.get(body.get("scenario"))
            if not s:
                return self._json({"ok": False, "error": "escenario desconocido"}, 404)
            idx = body.get("steps")
            idx = range(len(s["steps"])) if idx == "all" else [int(body.get("step", 0))]

            def go():
                out = []
                for i in idx:
                    st = s["steps"][i]
                    out.append(run_stmts(st["stmts"], st["label"], st.get("checks"), s["id"]))
                return {"ok": True, "entries": out}
            self._guard(go)
        elif p == "/api/run":
            stmts = [x for x in body.get("stmts", []) if x.strip()]
            if not stmts:
                return self._json({"ok": False, "error": "sin sentencias"}, 400)
            self._guard(lambda: {"ok": True, "entries": [
                run_stmts(stmts, body.get("label") or "Generador", body.get("checks"))]})
        elif p == "/api/board":
            if body.get("scenario") not in _BY_SCN:
                return self._json({"ok": False, "error": "escenario desconocido"}, 404)
            self._guard(lambda: load_board(body["scenario"]))
        elif p == "/api/capture/start":
            self._guard(lambda: capture_start(body.get("name") or "captura"))
        elif p == "/api/capture/stop":
            self._guard(capture_stop)
        elif p == "/api/plc/configure":
            def go():
                log = []
                prog = os.path.join(PLC_PROGRAMS, _BY_SCN["openplc"]["program"])

                def reload_board():
                    load_board("openplc")
                    return "tablero de la lámina 36 recargado en modbus-sim con el PLC detenido ✓"
                try:
                    st = plc.configure(prog, lambda m: log.append(m), before_start=reload_board)
                except Exception as e:  # noqa: BLE001
                    return {"ok": False, "error": str(e), "log": log}
                HISTORY.append({"n": len(HISTORY) + 1, "ts": time.strftime("%H:%M:%S"), "scenario": "openplc",
                                "label": "Configurar OpenPLC: tableros.st + Slave Device + Start PLC",
                                "plc_log": log, "steps": [], "logs": [], "state": None, "checks": [], "ms": 0})
                return {"ok": True, "status": st, "log": log, "devices": plc.devices()}
            self._guard(go)
        elif p in ("/api/plc/start", "/api/plc/stop"):
            self._guard(lambda: {"ok": True, "status": plc.start() if p.endswith("start") else plc.stop()})
        elif p == "/api/plc/live/start":
            def go():
                ensure_netshoot()
                PLC_LIVE.start(bridge_iface(), TARGET_PORT)
                return {"ok": True, "running": PLC_LIVE.running}
            self._guard(go)
        elif p == "/api/plc/live/stop":
            def go():
                frames = PLC_LIVE.snapshot()
                a = plc.analyze(frames, PLC_LIVE.t0 or time.time(), window=float(body.get("window", 5)))
                name = "".join(ch for ch in (body.get("name") or "openplc") if ch.isalnum() or ch in "-_")
                path = os.path.join(CAPTURES, f"{name}.pcapng")
                size = PLC_LIVE.stop(path)
                HISTORY.append({"n": len(HISTORY) + 1, "ts": time.strftime("%H:%M:%S"), "scenario": "openplc",
                                "label": f"Captura del sondeo de OpenPLC · {a['elapsed']} s · {path}",
                                "plc": a, "steps": [], "logs": [], "state": None, "checks": [], "ms": 0})
                return {"ok": True, "saved": path if size else None, "bytes": size, "entry": HISTORY[-1]}
            self._guard(go)
        elif p == "/api/plc/field":
            self._guard(lambda: field_change(body.get("ir"), body.get("di")))
        elif p == "/api/plc/outage":
            self._guard(lambda: slave_outage(max(1, min(int(body.get("seconds", 5)), 30))))
        elif p == "/api/wireshark/start":
            self._guard(live_start)
        elif p == "/api/wireshark/stop":
            self._guard(live_stop)
        elif p == "/api/history/clear":
            HISTORY.clear()
            self._json({"ok": True})
        else:
            self.send_error(404)


if __name__ == "__main__":
    print("Preparando contenedor cliente...", flush=True)
    ensure_client()
    print(f"server.json: {SERVER_JSON}", flush=True)
    print(f"captura en el puente {bridge_iface()} · Wireshark: {wireshark_mode()}", flush=True)
    print(f"Dashboard -> http://localhost:{WEB_PORT}", flush=True)
    # Solo localhost: /api/run ejecuta Python (dentro del contenedor cliente).
    ThreadingHTTPServer((WEB_HOST, WEB_PORT), Handler).serve_forever()
