"""
Explorador Modbus TCP · Taller 5 · Prácticas 1a y 1b (ot-lab)
Backend FastAPI que envuelve pymodbus. Cada operación devuelve, además de los valores,
las tramas reales (MBAP + PDU) que viajaron por la red, capturadas con trace_packet.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import re
import struct
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException

STATIC = Path(__file__).parent / "static"
SERVER_JSON = Path(os.environ.get("SERVER_JSON", "/app/server.json"))
CAPTURES = Path(os.environ.get("CAPTURES_DIR", "/app/captures"))
CAPTURES.mkdir(parents=True, exist_ok=True)

TARGETS = [
    {"id": "modbus-sim", "label": "modbus-sim · esclavo simulado", "host": "172.28.0.30", "port": 5020, "unit": 1,
     "note": "oitc/modbus-server · registros de modbus/server.json · clave JSON = dirección + 1"},
    {"id": "openplc", "label": "openplc · esclavo interno del PLC", "host": "172.28.0.10", "port": 502, "unit": 1,
     "note": "Modbus Server de OpenPLC (Settings) · %IX = DI · %QX = coils · %IW = IR · %QW = HR"},
    {"id": "conpot", "label": "conpot · honeypot (Modbus 5020)", "host": "172.28.0.90", "port": 5020, "unit": 1,
     "note": "Plantilla default de Conpot · Bloque 5"},
]

FC_NAMES = {1: "Read Coils", 2: "Read Discrete Inputs", 3: "Read Holding Registers", 4: "Read Input Registers",
            5: "Write Single Coil", 6: "Write Single Register", 15: "Write Multiple Coils", 16: "Write Multiple Registers"}
EXC_NAMES = {1: "Illegal Function", 2: "Illegal Data Address", 3: "Illegal Data Value", 4: "Server Device Failure",
             5: "Acknowledge", 6: "Server Device Busy", 8: "Memory Parity Error", 10: "Gateway Path Unavailable",
             11: "Gateway Target Device Failed to Respond"}

app = FastAPI(title="Explorador Modbus TCP · ot-lab")


# ---------------------------------------------------------------- cliente Modbus con traza de tramas
class Session:
    """Un único cliente pymodbus vivo (como la sesión interactiva de las láminas 22 y 29)."""

    def __init__(self) -> None:
        self.client: ModbusTcpClient | None = None
        self.host = ""
        self.port = 0
        self.unit = 1
        self.lock = threading.Lock()
        self._frames: list[dict[str, Any]] = []   # tramas de la operación en curso
        self.seq = 0

    def _trace(self, sending: bool, data: bytes) -> bytes:
        self._frames.append({"dir": "query" if sending else "response", "hex": data.hex(" "), "t": time.time()})
        return data

    def connect(self, host: str, port: int, unit: int) -> bool:
        self.close()
        self.client = ModbusTcpClient(host, port=port, timeout=3, retries=0, trace_packet=self._trace)
        self.host, self.port, self.unit = host, port, unit
        return bool(self.client.connect())

    def close(self) -> None:
        if self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass
        self.client = None

    @property
    def connected(self) -> bool:
        return self.client is not None and self.client.connected

    def run(self, fn_name: str, *args: Any, **kw: Any) -> dict[str, Any]:
        if self.client is None:
            raise HTTPException(409, "No hay sesión abierta: pulse «Conectar» primero.")
        with self.lock:
            self._frames = []
            t0 = time.perf_counter()
            error: str | None = None
            result = None
            try:
                result = getattr(self.client, fn_name)(*args, **kw)
            except ModbusException as e:          # p. ej. conexión perdida
                error = f"pymodbus: {e}"
            except (ValueError, TypeError, struct.error) as e:   # p. ej. 70000 no cabe en 16 bits
                error = f"pymodbus se queja antes de enviar nada: {type(e).__name__}: {e}"
            except Exception as e:  # noqa: BLE001
                error = f"{type(e).__name__}: {e}"
            elapsed = (time.perf_counter() - t0) * 1000
            frames = list(self._frames)
        self.seq += 1
        return {"seq": self.seq, "elapsed_ms": round(elapsed, 2), "frames": [decode_frame(f) for f in frames],
                "error": error, "result": result}


SESSION = Session()


# ---------------------------------------------------------------- decodificación didáctica de tramas
def decode_frame(f: dict[str, Any]) -> dict[str, Any]:
    raw = bytes.fromhex(f["hex"])
    out: dict[str, Any] = {"dir": f["dir"], "hex": f["hex"], "len": len(raw)}
    if len(raw) < 8:
        return out
    tid, pid, length, uid = int.from_bytes(raw[0:2], "big"), int.from_bytes(raw[2:4], "big"), int.from_bytes(raw[4:6], "big"), raw[6]
    pdu = raw[7:]
    fc = pdu[0]
    out.update({"mbap": {"hex": raw[:7].hex(" "), "transaction_id": tid, "protocol_id": pid, "length": length, "unit_id": uid},
                "pdu": {"hex": pdu.hex(" "), "len": len(pdu)}, "fc": fc & 0x7F, "exception": bool(fc & 0x80)})
    fields: list[dict[str, Any]] = [{"name": "FC", "hex": pdu[:1].hex(), "value": f"{fc & 0x7F} · {FC_NAMES.get(fc & 0x7F, '?')}" + (" · EXCEPCIÓN (+128)" if fc & 0x80 else "")}]
    try:
        if fc & 0x80:
            code = pdu[1]
            fields.append({"name": "Exception Code", "hex": pdu[1:2].hex(), "value": f"{code:02d} · {EXC_NAMES.get(code, '?')}"})
        elif f["dir"] == "query":
            addr = int.from_bytes(pdu[1:3], "big")
            fields.append({"name": "Reference Number", "hex": pdu[1:3].hex(" "), "value": addr})
            if fc in (1, 2, 3, 4):
                fields.append({"name": "Bit Count" if fc in (1, 2) else "Word Count", "hex": pdu[3:5].hex(" "), "value": int.from_bytes(pdu[3:5], "big")})
            elif fc == 5:
                fields.append({"name": "Data", "hex": pdu[3:5].hex(" "), "value": "ON (ff 00)" if pdu[3:5] == b"\xff\x00" else "OFF (00 00)"})
            elif fc == 6:
                fields.append({"name": "Data", "hex": pdu[3:5].hex(" "), "value": int.from_bytes(pdu[3:5], "big")})
            elif fc == 15:
                n = int.from_bytes(pdu[3:5], "big"); bc = pdu[5]; data = pdu[6:6 + bc]
                bits = [(data[i // 8] >> (i % 8)) & 1 for i in range(n)]
                fields += [{"name": "Bit Count", "hex": pdu[3:5].hex(" "), "value": n},
                           {"name": "Byte Count", "hex": pdu[5:6].hex(), "value": bc},
                           {"name": "Data", "hex": data.hex(" "), "value": "bits " + "".join(str(b) for b in bits[::-1]) + " (coil n → bit n)"}]
            elif fc == 16:
                n = int.from_bytes(pdu[3:5], "big"); bc = pdu[5]; data = pdu[6:6 + bc]
                regs = [int.from_bytes(data[i:i + 2], "big") for i in range(0, len(data), 2)]
                fields += [{"name": "Word Count", "hex": pdu[3:5].hex(" "), "value": n},
                           {"name": "Byte Count", "hex": pdu[5:6].hex(), "value": bc},
                           {"name": "Data", "hex": data.hex(" "), "value": regs}]
        else:  # response
            if fc in (1, 2):
                bc = pdu[1]; data = pdu[2:2 + bc]
                bits = [(data[i // 8] >> (i % 8)) & 1 for i in range(bc * 8)]
                fields += [{"name": "Byte Count", "hex": pdu[1:2].hex(), "value": bc},
                           {"name": "Data", "hex": data.hex(" "), "value": "bits " + "".join(str(b) for b in bits[:8][::-1]) + " (bit 0 = primer coil/entrada)"}]
            elif fc in (3, 4):
                bc = pdu[1]; data = pdu[2:2 + bc]
                regs = [int.from_bytes(data[i:i + 2], "big") for i in range(0, len(data), 2)]
                fields += [{"name": "Byte Count", "hex": pdu[1:2].hex(), "value": bc},
                           {"name": "Data", "hex": data.hex(" "), "value": regs}]
            elif fc in (5, 6):
                fields += [{"name": "Reference Number", "hex": pdu[1:3].hex(" "), "value": int.from_bytes(pdu[1:3], "big")},
                           {"name": "Data (eco)", "hex": pdu[3:5].hex(" "), "value": int.from_bytes(pdu[3:5], "big")}]
            elif fc in (15, 16):
                fields += [{"name": "Reference Number", "hex": pdu[1:3].hex(" "), "value": int.from_bytes(pdu[1:3], "big")},
                           {"name": "Count (eco)", "hex": pdu[3:5].hex(" "), "value": int.from_bytes(pdu[3:5], "big")}]
    except IndexError:
        fields.append({"name": "?", "hex": "", "value": "PDU truncada"})
    out["fields"] = fields
    return out


# ---------------------------------------------------------------- modelos
class ConnectReq(BaseModel):
    host: str = "172.28.0.30"
    port: int = 5020
    unit: int = 1


class ReadReq(BaseModel):
    table: str = Field(pattern="^(coils|di|hr|ir)$")
    address: int = Field(ge=0, le=65535)
    count: int = Field(ge=1, le=125)


class WriteReq(BaseModel):
    kind: str = Field(pattern="^(coil|coils|register|registers)$")
    address: int = Field(ge=0, le=65535)
    value: Any = None          # bool | int
    values: list[Any] | None = None


READ_FN = {"coils": ("read_coils", 1), "di": ("read_discrete_inputs", 2), "hr": ("read_holding_registers", 3), "ir": ("read_input_registers", 4)}
WRITE_FN = {"coil": ("write_coil", 5), "register": ("write_register", 6), "coils": ("write_coils", 15), "registers": ("write_registers", 16)}


def pack_result(res: dict[str, Any], fc: int, pyline: str, table: str | None = None, count: int | None = None) -> dict[str, Any]:
    r = res.pop("result")
    out = {**res, "fc": fc, "fc_name": FC_NAMES[fc], "pymodbus": pyline, "ok": False, "values": None, "exception": None}
    if r is None:
        return out
    if r.isError():
        code = getattr(r, "exception_code", None)
        out["exception"] = {"code": code, "name": EXC_NAMES.get(code, "?"), "text": str(r)}
        return out
    out["ok"] = True
    if fc in (1, 2):
        out["values"] = [bool(b) for b in r.bits[:count]]
    elif fc in (3, 4):
        out["values"] = list(r.registers)
    else:  # escrituras: el esclavo devuelve un eco de la Query
        out["values"] = f"OK · eco dir {getattr(r, 'address', '?')}" + (f" · count {r.count}" if fc in (15, 16) else "")
    return out


# ---------------------------------------------------------------- API
@app.get("/api/targets")
def targets() -> dict[str, Any]:
    return {"targets": TARGETS, "session": session_info()}


def session_info() -> dict[str, Any]:
    return {"connected": SESSION.connected, "host": SESSION.host, "port": SESSION.port, "unit": SESSION.unit}


@app.post("/api/connect")
def connect(req: ConnectReq) -> dict[str, Any]:
    ok = SESSION.connect(req.host, req.port, req.unit)
    if not ok:
        SESSION.close()
        raise HTTPException(502, f"No se pudo conectar a {req.host}:{req.port}. ¿Está el contenedor arriba y en la red ot-lab?")
    return {"pymodbus": f"c = ModbusTcpClient('{req.host}', port={req.port}); c.connect()", **session_info()}


@app.post("/api/disconnect")
def disconnect() -> dict[str, Any]:
    SESSION.close()
    return {"pymodbus": "c.close()", **session_info()}


@app.post("/api/read")
def read(req: ReadReq) -> dict[str, Any]:
    fn, fc = READ_FN[req.table]
    pyline = f"c.{fn}({req.address}, count={req.count}, device_id={SESSION.unit})"
    res = SESSION.run(fn, req.address, count=req.count, device_id=SESSION.unit)
    return pack_result(res, fc, pyline, req.table, req.count)


@app.post("/api/write")
def write(req: WriteReq) -> dict[str, Any]:
    fn, fc = WRITE_FN[req.kind]
    if req.kind in ("coil", "register"):
        v = req.value
        if req.kind == "coil":
            v = bool(v) if not isinstance(v, str) else v.lower() in ("1", "true", "on")
        else:
            v = int(v)
        pyline = f"c.{fn}({req.address}, {v}, device_id={SESSION.unit})"
        res = SESSION.run(fn, req.address, v, device_id=SESSION.unit)
    else:
        vals = req.values or []
        if req.kind == "coils":
            vals = [bool(x) if not isinstance(x, str) else x.lower() in ("1", "true", "on") for x in vals]
        else:
            vals = [int(x) for x in vals]
        pyline = f"c.{fn}({req.address}, {vals}, device_id={SESSION.unit})"
        res = SESSION.run(fn, req.address, vals, device_id=SESSION.unit)
    return pack_result(res, fc, pyline)


@app.get("/api/serverjson")
def serverjson() -> dict[str, Any]:
    if not SERVER_JSON.exists():
        return {"available": False, "path": str(SERVER_JSON)}
    try:
        data = json.loads(SERVER_JSON.read_text())
        return {"available": True, "path": str(SERVER_JSON), "registers": data.get("registers", {}),
                "server": data.get("server", {}), "mtime": datetime.fromtimestamp(SERVER_JSON.stat().st_mtime).isoformat(timespec="seconds")}
    except json.JSONDecodeError as e:
        return {"available": True, "path": str(SERVER_JSON), "error": f"JSON roto: {e}"}


# ---------------------------------------------------------------- captura (tcpdump dentro del contenedor)
class Capture:
    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.file: Path | None = None
        self.started: float = 0

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def info(self) -> dict[str, Any]:
        size = self.file.stat().st_size if self.file and self.file.exists() else 0
        return {"running": self.running, "file": self.file.name if self.file else None, "bytes": size,
                "seconds": round(time.time() - self.started, 1) if self.running else 0,
                "tcpdump": shutil.which("tcpdump") is not None}

    def start(self, ports: list[int]) -> dict[str, Any]:
        if self.running:
            return self.info()
        if shutil.which("tcpdump") is None:
            raise HTTPException(500, "tcpdump no está instalado en la imagen.")
        name = f"explorer_{datetime.now():%Y%m%d_%H%M%S}.pcap"
        self.file = CAPTURES / name
        flt = " or ".join(f"tcp port {p}" for p in ports) or "tcp"
        self.proc = subprocess.Popen(["tcpdump", "-i", "any", "-U", "-s", "0", "-w", str(self.file), flt],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.started = time.time()
        time.sleep(0.4)
        if self.proc.poll() is not None:
            err = self.proc.stderr.read().decode(errors="replace") if self.proc.stderr else ""
            self.proc = None
            raise HTTPException(500, f"tcpdump no arrancó: {err.strip()}")
        return self.info()

    def stop(self) -> dict[str, Any]:
        if self.running:
            assert self.proc is not None
            self.proc.send_signal(signal.SIGINT)
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        return self.info()


CAPTURE = Capture()


class CaptureReq(BaseModel):
    ports: list[int] = [5020, 502]


@app.get("/api/capture")
def capture_status() -> dict[str, Any]:
    return CAPTURE.info()


@app.post("/api/capture/start")
def capture_start(req: CaptureReq) -> dict[str, Any]:
    return CAPTURE.start(req.ports)


@app.post("/api/capture/stop")
def capture_stop() -> dict[str, Any]:
    return CAPTURE.stop()


@app.get("/api/capture/file/{name}")
def capture_file(name: str) -> FileResponse:
    p = CAPTURES / Path(name).name
    if not p.exists():
        raise HTTPException(404, "No existe esa captura.")
    return FileResponse(p, media_type="application/vnd.tcpdump.pcap", filename=p.name)


@app.get("/api/capture/list")
def capture_list() -> dict[str, Any]:
    files = sorted(CAPTURES.glob("*.pcap*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return {"files": [{"name": p.name, "bytes": p.stat().st_size,
                       "mtime": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")} for p in files[:30]]}


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "session": session_info(), "capture": CAPTURE.info()}



# ---------------------------------------------------------------- OpenPLC · automatización del panel web (práctica 1b)
OPENPLC_URL = os.environ.get("OPENPLC_URL", "http://172.28.0.10:8080").rstrip("/")
OPENPLC_USER = os.environ.get("OPENPLC_USER", "openplc")
OPENPLC_PASS = os.environ.get("OPENPLC_PASS", "openplc")
PROGRAMS_DIR = Path(__file__).parent / "programs"


class OpenPLC:
    """Cliente HTTP del panel de OpenPLC v3: hace por nosotros lo que el estudiante haría a mano (láminas 33–35)."""

    def __init__(self) -> None:
        self.s = requests.Session()
        self.logged = False
        self.lock = threading.Lock()

    def login(self, user: str | None = None, password: str | None = None) -> bool:
        r = self.s.post(f"{OPENPLC_URL}/login", data={"username": user or OPENPLC_USER, "password": password or OPENPLC_PASS},
                        timeout=8, allow_redirects=True)
        self.logged = r.ok and "Bad credentials" not in r.text and "login" not in r.url
        return self.logged

    def get(self, path: str, **kw: Any) -> requests.Response:
        r = self.s.get(f"{OPENPLC_URL}/{path.lstrip('/')}", timeout=kw.pop("timeout", 10), **kw)
        if "/login" in r.url or "<title>OpenPLC Login" in r.text[:400]:
            if not self.login():
                raise HTTPException(502, "OpenPLC rechazó las credenciales.")
            r = self.s.get(f"{OPENPLC_URL}/{path.lstrip('/')}", timeout=10, **kw)
        return r

    def status(self) -> str:
        r = self.get("dashboard")
        m = re.search(r"Status:\s*<i>(\w+)</i>", r.text)
        return m.group(1) if m else ("Compiling" if "Compiling" in r.text else "Unknown")

    def dashboard(self) -> dict[str, Any]:
        r = self.get("dashboard")
        def grab(label: str) -> str:
            m = re.search(rf"<b>{label}:</b>\s*(.*?)</p>", r.text, re.S)
            return re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""
        m = re.search(r"Status:\s*<i>(\w+)</i>", r.text)
        return {"status": m.group(1) if m else "Unknown", "program": grab("Program"), "description": grab("Description"),
                "file": grab("File")}

    def upload_program(self, name: str, st_text: str, descr: str = "") -> str:
        """Programs → Upload → Upload program → compile. Devuelve el nombre de archivo interno (.st)."""
        r = self.get("programs")  # asegura sesión
        r = self.s.post(f"{OPENPLC_URL}/upload-program", files={"file": (f"{name}.st", st_text.encode())}, timeout=20)
        m = re.search(r"name='prog_file'[^>]*value='([^']+)'|value='([^']+)'[^>]*name='prog_file'", r.text)
        e = re.search(r"value='(\d+)'[^>]*name='epoch_time'|name='epoch_time'[^>]*value='(\d+)'", r.text)
        if not m:
            raise HTTPException(502, "OpenPLC no devolvió el formulario de 'Program Info'. ¿Está compilando?")
        prog_file = m.group(1) or m.group(2)
        epoch = (e.group(1) or e.group(2)) if e else str(int(time.time()))
        self.s.post(f"{OPENPLC_URL}/upload-program-action",
                    data={"prog_name": name, "prog_descr": descr, "prog_file": prog_file, "epoch_time": epoch}, timeout=20)
        self.s.get(f"{OPENPLC_URL}/compile-program", params={"file": prog_file}, timeout=20)
        return prog_file

    def compilation_logs(self) -> str:
        return self.get("compilation-logs").text

    def wait_compile(self, max_s: float = 240) -> str:
        t0 = time.time()
        log = ""
        while time.time() - t0 < max_s:
            log = self.compilation_logs()
            if "Compilation finished" in log:
                break
            time.sleep(1.5)
        return log

    def start(self) -> str:
        self.get("start_plc")
        for _ in range(6):                      # el runtime tarda 1–3 s en abrir el puerto de control (43628)
            time.sleep(1.0)
            if self.status() == "Running":
                break
        return self.status()

    def stop(self) -> str:
        self.get("stop_plc"); time.sleep(0.8); return self.status()

    def devices(self) -> list[dict[str, Any]]:
        r = self.get("modbus")
        rows = []
        for m in re.finditer(r"modbus-edit-device\?table_id=(\d+)'\"?>(.*?)</tr>", r.text, re.S):
            tds = [re.sub(r"<[^>]+>", "", t).strip() for t in re.findall(r"<td[^>]*>(.*?)</td>", m.group(2), re.S)]
            rows.append({"id": int(m.group(1)), "cols": tds})
        return rows

    def add_device(self, d: dict[str, Any]) -> list[dict[str, Any]]:
        form = {"device_name": d.get("name", "modbus-sim"), "device_protocol": "TCP", "device_id": str(d.get("slave_id", 1)),
                "device_ip": d.get("ip", "172.28.0.30"), "device_port": str(d.get("port", 5020)),
                # Aunque sea TCP, el runtime lee estos campos (atoi) y con "" cae con SIGFPE: mismos defaults que el panel
                "device_cport": "COM1", "device_baud": "115200", "device_parity": "None", "device_data": "8", "device_stop": "1",
                "di_start": str(d.get("di_start", 0)), "di_size": str(d.get("di_size", 2)),
                "do_start": str(d.get("coil_start", 0)), "do_size": str(d.get("coil_size", 2)),
                "ai_start": str(d.get("ir_start", 0)), "ai_size": str(d.get("ir_size", 2)),
                "aor_start": str(d.get("hr_read_start", 0)), "aor_size": str(d.get("hr_read_size", 2)),
                "aow_start": str(d.get("hr_write_start", 0)), "aow_size": str(d.get("hr_write_size", 0))}
        self.get("modbus")
        self.s.post(f"{OPENPLC_URL}/add-modbus-device", data=form, timeout=20)
        return self.devices()

    def delete_device(self, dev_id: int) -> list[dict[str, Any]]:
        self.get(f"delete-device?dev_id={dev_id}")
        return self.devices()

    def settings_modbus(self, port: int | None = 502) -> None:
        form = {"dnp3_server_port": "20000", "enip_server_port": "44818", "slave_polling_period": "100",
                "slave_timeout": "1000", "auto_run_text": "false"}
        if port:
            form["modbus_server_port"] = str(port)
        self.get("settings")
        self.s.post(f"{OPENPLC_URL}/settings", data=form, timeout=20)

    def monitor(self, port: int = 502) -> list[dict[str, Any]]:
        r = self.get(f"monitor-update?mb_port={port}")
        rows = []
        for m in re.finditer(r"<tr[^>]*>\s*<td>(.*?)</td><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td><td[^>]*>(.*?)</td>", r.text, re.S):
            name, typ, loc, forced, val = m.groups()
            val = re.sub(r"<[^>]+>", "", val).strip()
            if not loc.strip().startswith("%"):      # línea de comentario que el parser de OpenPLC tomó por variable
                continue
            rows.append({"name": name.strip(), "type": typ.strip(), "location": loc.strip(), "forced": forced.strip(), "value": val})
        return rows


PLC = OpenPLC()


class PlcLogin(BaseModel):
    user: str = OPENPLC_USER
    password: str = OPENPLC_PASS


class PlcProgram(BaseModel):
    name: str = "monito"
    st: str
    descr: str = "Taller 5 · práctica 1b · cargado desde modbus-explorer"
    start: bool = True


class PlcDevice(BaseModel):
    name: str = "modbus-sim"
    slave_id: int = 1
    ip: str = "172.28.0.30"
    port: int = 5020
    di_start: int = 0
    di_size: int = 2
    coil_start: int = 0
    coil_size: int = 2
    ir_start: int = 0
    ir_size: int = 2
    hr_read_start: int = 0
    hr_read_size: int = 2
    hr_write_start: int = 0
    hr_write_size: int = 0
    replace: bool = True


def plc_guard(fn, *a, **kw):
    try:
        with PLC.lock:
            return fn(*a, **kw)
    except requests.RequestException as e:
        raise HTTPException(502, f"No se alcanza OpenPLC en {OPENPLC_URL}: {e.__class__.__name__}. ¿Está arriba el contenedor openplc?")


@app.get("/api/openplc/status")
def plc_status() -> dict[str, Any]:
    def go():
        if not PLC.logged and not PLC.login():
            raise HTTPException(502, "OpenPLC rechazó las credenciales por defecto (openplc/openplc).")
        return {"url": OPENPLC_URL, "public": "http://localhost:8080", **PLC.dashboard(), "devices": PLC.devices()}
    return plc_guard(go)


@app.post("/api/openplc/login")
def plc_login(req: PlcLogin) -> dict[str, Any]:
    ok = plc_guard(PLC.login, req.user, req.password)
    if not ok:
        raise HTTPException(401, "Credenciales rechazadas por OpenPLC.")
    return {"ok": True}


@app.get("/api/openplc/programs")
def plc_programs() -> dict[str, Any]:
    out = []
    for p in sorted(PROGRAMS_DIR.glob("*.st")):
        txt = p.read_text()
        first = txt.strip().splitlines()[0].strip("(* ").strip(" *)") if txt.strip() else ""
        out.append({"id": p.stem, "title": first, "st": txt})
    return {"programs": out}


@app.post("/api/openplc/program")
def plc_program(req: PlcProgram) -> dict[str, Any]:
    def go():
        if not PLC.logged:
            PLC.login()
        if PLC.status() == "Running":
            PLC.stop()
        f = PLC.upload_program(re.sub(r"[^A-Za-z0-9_]", "_", req.name) or "programa", req.st, req.descr)
        log = PLC.wait_compile()
        ok = "Compilation finished successfully" in log
        status = PLC.start() if (ok and req.start) else PLC.status()
        return {"ok": ok, "file": f, "log": log, "status": status}
    return plc_guard(go)


@app.get("/api/openplc/compilation-logs")
def plc_logs() -> dict[str, Any]:
    return plc_guard(lambda: {"log": PLC.compilation_logs()})


@app.post("/api/openplc/start")
def plc_start() -> dict[str, Any]:
    return plc_guard(lambda: {"status": PLC.start()})


@app.post("/api/openplc/stop")
def plc_stop() -> dict[str, Any]:
    return plc_guard(lambda: {"status": PLC.stop()})


@app.post("/api/openplc/device")
def plc_device(req: PlcDevice) -> dict[str, Any]:
    def go():
        if not PLC.logged:
            PLC.login()
        if req.replace:
            for d in PLC.devices():
                if d["cols"] and d["cols"][0] == req.name:
                    PLC.delete_device(d["id"])
        devs = PLC.add_device(req.model_dump())
        return {"devices": devs, "note": "La lista de esclavos se lee al arrancar el runtime: haga Stop → Start PLC (o use «Reiniciar PLC»)."}
    return plc_guard(go)


@app.delete("/api/openplc/device/{dev_id}")
def plc_device_del(dev_id: int) -> dict[str, Any]:
    return plc_guard(lambda: {"devices": PLC.delete_device(dev_id)})


@app.post("/api/openplc/modbus-server")
def plc_modbus_server(port: int = 502) -> dict[str, Any]:
    def go():
        PLC.settings_modbus(port)
        return {"ok": True, "port": port}
    return plc_guard(go)


@app.get("/api/openplc/monitor")
def plc_monitor() -> dict[str, Any]:
    def go():
        if not PLC.logged:
            PLC.login()
        return {"status": PLC.status(), "rows": PLC.monitor()}
    return plc_guard(go)


@app.post("/api/openplc/setup")
def plc_setup(req: PlcProgram) -> dict[str, Any]:
    """Un clic = práctica 1b completa: Modbus Server 502 + Slave Device modbus-sim + programa + Start PLC."""
    def go():
        if not PLC.logged:
            PLC.login()
        if PLC.status() == "Running":
            PLC.stop()
        PLC.settings_modbus(502)
        for d in PLC.devices():
            if d["cols"] and d["cols"][0] == "modbus-sim":
                PLC.delete_device(d["id"])
        devs = PLC.add_device(PlcDevice().model_dump())
        f = PLC.upload_program(re.sub(r"[^A-Za-z0-9_]", "_", req.name) or "programa", req.st, req.descr)
        log = PLC.wait_compile()
        ok = "Compilation finished successfully" in log
        status = PLC.start() if ok else PLC.status()
        return {"ok": ok, "file": f, "log": log, "status": status, "devices": devs}
    return plc_guard(go)


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
