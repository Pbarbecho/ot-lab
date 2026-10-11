"""
Explorador OPC UA · ot-lab
Backend FastAPI con dos mitades:
  · Servidor: editor del modelo de opcua-py (opcua/modelo.json) que genera opcua/server.py y reinicia el contenedor.
  · Cliente: una sesión asyncua (navegar, leer, escribir, suscribirse) que devuelve los mensajes OPC UA Binary
    reales que viajaron por la red, decodificados por uatap.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import http.client
import json
import logging
import os
import socket
import time
from pathlib import Path
from typing import Any

from asyncua import Client, ua
from asyncua.ua.uaerrors import UaStatusCodeError
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import generator
import uatap

logging.getLogger("asyncua").setLevel(logging.ERROR)
uatap.install()

STATIC = Path(__file__).parent / "static"
OPCUA_DIR = Path(os.environ.get("OPCUA_DIR", "/app/opcua"))
MODEL_JSON = OPCUA_DIR / "modelo.json"
SERVER_PY = OPCUA_DIR / "server.py"
DOCKER_SOCK = os.environ.get("DOCKER_SOCK", "/var/run/docker.sock")
OPCUA_CONTAINER = os.environ.get("OPCUA_CONTAINER", "opcua-py")
OPCUA_HOST = os.environ.get("OPCUA_HOST", "172.28.0.21")

TARGETS = [
    {"id": "opcua-py", "label": "opcua-py · servidor propio (Python)", "url": "opc.tcp://172.28.0.21:4840/lab/",
     "note": "El que define el editor de esta web · opcua/modelo.json → opcua/server.py"},
    {"id": "opc-plc", "label": "opc-plc · simulador de Microsoft", "url": "opc.tcp://172.28.0.20:50000",
     "note": "Nodos de prueba en Objects/OpcPlc/Telemetry (rampas, aleatorios, picos)"},
    {"id": "ignition", "label": "ignition · servidor OPC UA del gateway", "url": "opc.tcp://172.28.0.50:62541",
     "note": "Viene desactivado: actívelo en el gateway (Config → OPC UA → Server Settings) y admita None/Anónimo"},
]

app = FastAPI(title="Explorador OPC UA · ot-lab")


@app.middleware("http")
async def no_cache_static(request, call_next):
    resp = await call_next(request)
    if not request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


def status_name(e: BaseException) -> str:
    if isinstance(e, UaStatusCodeError):
        try:
            return ua.StatusCode(e.code).name
        except Exception:  # noqa: BLE001
            return str(e)
    return f"{type(e).__name__}: {e}" if str(e) else type(e).__name__


# ---------------------------------------------------------------- sesión asyncua
class Watch:
    """Manejador de la suscripción: guarda el último valor de cada nodo vigilado."""

    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}

    def datachange_notification(self, node: Any, val: Any, data: Any) -> None:
        key = node.nodeid.to_string()
        it = self.items.get(key)
        if it is None:
            return
        dv = data.monitored_item.Value
        it.update({"value": uatap.plain(val), "status": dv.StatusCode.name if dv.StatusCode else "Good",
                   "source_ts": uatap.plain(dv.SourceTimestamp), "server_ts": uatap.plain(dv.ServerTimestamp),
                   "count": it.get("count", 0) + 1, "t": time.time()})

    def status_change_notification(self, status: Any) -> None:
        pass


class Session:
    def __init__(self) -> None:
        self.client: Client | None = None
        self.url = ""
        self.lock = asyncio.Lock()
        self.sub: Any = None
        self.interval = 500
        self.watch = Watch()
        self.handles: dict[str, Any] = {}

    @property
    def connected(self) -> bool:
        try:
            proto = self.client.uaclient.protocol if self.client else None
            state = getattr(proto, "state", None)
            return bool(proto and str(getattr(state, "value", state)).lower() == "open")
        except Exception:  # noqa: BLE001
            return False

    def info(self) -> dict[str, Any]:
        return {"connected": self.connected, "url": self.url, "interval": self.interval}

    async def close(self) -> None:
        c, self.client, self.sub = self.client, None, None
        self.handles.clear()
        self.watch.items.clear()
        if c is not None:
            try:
                await asyncio.wait_for(c.disconnect(), 4)
            except Exception:  # noqa: BLE001
                try:
                    c.disconnect_socket()
                except Exception:  # noqa: BLE001
                    pass

    async def op(self, coro_fn, pyline: str) -> dict[str, Any]:
        """Ejecuta una operación y devuelve los mensajes que generó (los Publish de la suscripción pueden colarse)."""
        if self.client is None:
            raise HTTPException(409, "No hay sesión abierta: pulse «Conectar» primero.")
        async with self.lock:
            n0 = uatap.RECORDER.seq
            t0 = time.perf_counter()
            result, error = None, None
            try:
                result = await asyncio.wait_for(coro_fn(), 8)
            except asyncio.TimeoutError:
                error = "Sin respuesta del servidor en 8 s"
            except (UaStatusCodeError, ua.UaError, ConnectionError, OSError, ValueError, TypeError) as e:
                error = status_name(e)
            await asyncio.sleep(0.03)   # deja entrar la respuesta si llegó partida en varios segmentos TCP
            elapsed = (time.perf_counter() - t0) * 1000
        return {"result": result, "error": error, "elapsed_ms": round(elapsed, 1), "asyncua": pyline,
                "messages": uatap.RECORDER.since(n0), "connected": self.connected}


S = Session()


class ConnectReq(BaseModel):
    url: str = Field("opc.tcp://172.28.0.21:4840/lab/", pattern=r"^opc\.tcp://")
    interval: int = Field(500, ge=50, le=10000)   # PublishingInterval de la suscripción (ms)


class NodeReq(BaseModel):
    node: str


class WriteReq(BaseModel):
    node: str
    value: Any


@app.get("/api/targets")
def targets() -> dict[str, Any]:
    return {"targets": TARGETS, "session": S.info()}


@app.post("/api/connect")
async def connect(req: ConnectReq) -> dict[str, Any]:
    await S.close()
    uatap.RECORDER.clear()
    n0 = uatap.RECORDER.seq
    c = Client(req.url, timeout=5)
    c.session_timeout = 600000
    try:
        await asyncio.wait_for(c.connect(), 10)
    except Exception as e:  # noqa: BLE001
        try:
            c.disconnect_socket()
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(502, f"No se pudo conectar a {req.url}: {status_name(e)}. ¿Está el contenedor arriba y en la red ot-lab?")
    S.client, S.url, S.interval = c, req.url, req.interval
    ns = await c.get_namespace_array()
    return {**S.info(), "namespaces": ns, "messages": uatap.RECORDER.since(n0),
            "asyncua": f"c = Client({req.url!r}); await c.connect()"}


@app.post("/api/disconnect")
async def disconnect() -> dict[str, Any]:
    n0 = uatap.RECORDER.seq
    await S.close()
    await asyncio.sleep(0.05)
    return {**S.info(), "messages": uatap.RECORDER.since(n0), "asyncua": "await c.disconnect()"}


def _nid(node: str) -> ua.NodeId:
    try:
        return ua.NodeId.from_string(node)
    except Exception:  # noqa: BLE001
        raise HTTPException(422, f"NodeId no válido: «{node}» (ej.: i=85, ns=2;s=PLC1.LED)")


@app.get("/api/browse")
async def browse(node: str = "i=85") -> dict[str, Any]:
    nid = _nid(node)

    async def run():
        refs = await S.client.get_node(nid).get_references(refs=ua.ObjectIds.HierarchicalReferences,
                                                           direction=ua.BrowseDirection.Forward)
        return [{"node": r.NodeId.to_string(), "browse": r.BrowseName.to_string(), "name": r.DisplayName.Text,
                 "cls": r.NodeClass.name, "type": r.TypeDefinition.to_string() if r.TypeDefinition else "",
                 "ref": ua.ObjectIdNames.get(r.ReferenceTypeId.Identifier, r.ReferenceTypeId.to_string())
                 if r.ReferenceTypeId.NamespaceIndex == 0 else r.ReferenceTypeId.to_string()} for r in refs]

    res = await S.op(run, f"await c.get_node({node!r}).get_children()")
    res["children"] = res.pop("result") or []
    return res


ATTRS = ["NodeId", "NodeClass", "BrowseName", "DisplayName", "Description", "DataType", "Value",
         "AccessLevel", "UserAccessLevel", "ValueRank", "MinimumSamplingInterval"]


def _access(bits: int) -> str:
    names = [n for b, n in ((1, "Read"), (2, "Write"), (4, "HistoryRead"), (8, "HistoryWrite")) if bits & b]
    return f"{bits} · " + (" + ".join(names) if names else "ninguno")


@app.get("/api/node")
async def node_attrs(node: str) -> dict[str, Any]:
    nid = _nid(node)

    async def run():
        p = ua.ReadParameters()
        for a in ATTRS:
            rv = ua.ReadValueId()
            rv.NodeId, rv.AttributeId = nid, getattr(ua.AttributeIds, a)
            p.NodesToRead.append(rv)
        return await S.client.uaclient.read(p)

    res = await S.op(run, f"nodo = c.get_node({node!r})\nawait nodo.read_attributes([...])   # una sola ReadRequest con {len(ATTRS)} atributos")
    out = []
    writable = False
    for a, dv in zip(ATTRS, res.pop("result") or []):
        st = dv.StatusCode.name if dv.StatusCode else "Good"
        v = dv.Value.Value if dv.Value is not None else None
        shown: Any = uatap.plain(v)
        if a == "NodeClass" and v is not None:
            shown = ua.NodeClass(v).name
        elif a == "DataType" and isinstance(v, ua.NodeId):
            shown = f"{v.to_string()} · {ua.ObjectIdNames.get(v.Identifier, '?')}" if v.NamespaceIndex == 0 else v.to_string()
        elif a in ("AccessLevel", "UserAccessLevel") and isinstance(v, int):
            shown = _access(v)
            if a == "UserAccessLevel":
                writable = bool(v & 2)
        elif a == "Value" and dv.Value is not None:
            shown = {"Value": uatap.plain(v), "VariantType": dv.Value.VariantType.name,
                     "SourceTimestamp": uatap.plain(dv.SourceTimestamp), "ServerTimestamp": uatap.plain(dv.ServerTimestamp)}
        out.append({"attr": a, "value": shown if st.startswith("Good") else None, "status": st})
    res.update({"attrs": out, "writable": writable})
    return res


@app.post("/api/read")
async def read(req: NodeReq) -> dict[str, Any]:
    nid = _nid(req.node)
    res = await S.op(lambda: S.client.get_node(nid).read_data_value(), f"await c.get_node({req.node!r}).read_value()")
    dv = res.pop("result")
    res["value"] = None if dv is None else {"Value": uatap.plain(dv.Value.Value) if dv.Value else None,
                                            "VariantType": dv.Value.VariantType.name if dv.Value else None,
                                            "Status": dv.StatusCode.name if dv.StatusCode else "Good",
                                            "SourceTimestamp": uatap.plain(dv.SourceTimestamp)}
    return res


def convert(text: Any, vt: ua.VariantType) -> Any:
    """Texto del formulario → valor Python del tipo del nodo (sin truncar ni adivinar)."""
    s = str(text).strip()
    if vt == ua.VariantType.Boolean:
        if isinstance(text, bool):
            return text
        if s.lower() in ("1", "true", "t", "on", "si", "sí"):
            return True
        if s.lower() in ("0", "false", "f", "off", "no"):
            return False
        raise HTTPException(422, f"«{s}» no es un Boolean (true/false, 1/0, on/off).")
    if vt in (ua.VariantType.SByte, ua.VariantType.Byte, ua.VariantType.Int16, ua.VariantType.UInt16, ua.VariantType.Int32,
              ua.VariantType.UInt32, ua.VariantType.Int64, ua.VariantType.UInt64):
        try:
            return int(s)
        except ValueError:
            raise HTTPException(422, f"«{s}» no es un entero ({vt.name}).")
    if vt in (ua.VariantType.Float, ua.VariantType.Double):
        try:
            return float(s.replace(",", "."))
        except ValueError:
            raise HTTPException(422, f"«{s}» no es un número ({vt.name}).")
    if vt in (ua.VariantType.String, ua.VariantType.LocalizedText):
        return s
    raise HTTPException(422, f"Escribir el tipo {vt.name} no está soportado en esta web.")


@app.post("/api/write")
async def write(req: WriteReq) -> dict[str, Any]:
    nid = _nid(req.node)
    if S.client is None:
        raise HTTPException(409, "No hay sesión abierta: pulse «Conectar» primero.")
    try:
        vt = await asyncio.wait_for(S.client.get_node(nid).read_data_type_as_variant_type(), 5)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"No se pudo leer el tipo de {req.node}: {status_name(e)}")
    v = convert(req.value, vt)
    res = await S.op(lambda: S.client.get_node(nid).write_value(ua.DataValue(ua.Variant(v, vt))),
                     f"await c.get_node({req.node!r}).write_value(ua.DataValue(ua.Variant({v!r}, ua.VariantType.{vt.name})))")
    res.pop("result")
    res.update({"written": uatap.plain(v), "variant": vt.name, "ok": res["error"] is None})
    return res


# ---------------------------------------------------------------- suscripción
async def _ensure_sub() -> None:
    if S.sub is None:
        S.sub = await S.client.create_subscription(S.interval, S.watch)


async def _watch(nodes: list[tuple[str, str]]) -> dict[str, Any]:
    """nodes: [(nodeid, etiqueta)]; crea los MonitoredItems que falten en una sola petición."""
    new = [(n, label) for n, label in nodes if n not in S.handles]

    async def run():
        await _ensure_sub()
        if not new:
            return []
        objs = [S.client.get_node(n) for n, _ in new]
        for n, label in new:
            S.watch.items[n] = {"node": n, "label": label, "value": None, "status": "—", "count": 0}
        handles = await S.sub.subscribe_data_change(objs)
        if not isinstance(handles, list):
            handles = [handles]
        bad = []
        for (n, _), h in zip(new, handles):
            if isinstance(h, ua.StatusCode) or not isinstance(h, int):
                bad.append(n)
                S.watch.items.pop(n, None)
            else:
                S.handles[n] = h
        return bad

    py = (f"sub = await c.create_subscription({S.interval}, manejador)   # PublishingInterval {S.interval} ms\n"
          f"await sub.subscribe_data_change([{', '.join(repr(n) for n, _ in new[:3])}{', …' if len(new) > 3 else ''}])")
    res = await S.op(run, py)
    res["rejected"] = res.pop("result") or []
    return res


@app.post("/api/watch")
async def watch_add(req: NodeReq) -> dict[str, Any]:
    _nid(req.node)
    return await _watch([(req.node, req.node)])


@app.post("/api/unwatch")
async def watch_del(req: NodeReq) -> dict[str, Any]:
    h = S.handles.pop(req.node, None)
    S.watch.items.pop(req.node, None)
    if h is None or S.sub is None:
        return {"ok": True, "messages": []}
    return await S.op(lambda: S.sub.unsubscribe(h), f"await sub.unsubscribe(handle)   # {req.node}")


@app.get("/api/watch")
def watch_list() -> dict[str, Any]:
    return {"items": list(S.watch.items.values()), "session": S.info()}


@app.post("/api/watch/model")
async def watch_model() -> dict[str, Any]:
    """Vigila todas las variables del modelo guardado (para que el dibujo muestre los valores en vivo)."""
    if S.client is None:
        raise HTTPException(409, "No hay sesión abierta.")
    model = load_model()[0]
    try:
        idx = await S.client.get_namespace_index(model["servidor"]["namespace"])
    except Exception:  # noqa: BLE001
        raise HTTPException(404, f"El servidor conectado no publica el namespace {model['servidor']['namespace']}: ¿es opcua-py?")
    nodes = [(f"ns={idx};s={o['nombre']}.{v['nombre']}", f"{o['nombre']}.{v['nombre']}")
             for o in model["objetos"] for v in o["variables"]]
    res = await _watch(nodes)
    res["map"] = {label: n for n, label in nodes}
    return res


@app.get("/api/messages")
def messages(since: int = 0) -> dict[str, Any]:
    return {"messages": uatap.RECORDER.since(since), "last": uatap.RECORDER.seq}


@app.post("/api/messages/clear")
def messages_clear() -> dict[str, Any]:
    uatap.RECORDER.clear()
    return {"ok": True, "last": uatap.RECORDER.seq}


# ---------------------------------------------------------------- modelo del servidor (editor)
class ModelDoc(BaseModel):
    model: dict[str, Any]


def load_model() -> tuple[dict[str, Any], str]:
    if MODEL_JSON.exists():
        try:
            return generator.validate(json.loads(MODEL_JSON.read_text(encoding="utf-8"))), "modelo.json"
        except (ValueError, json.JSONDecodeError) as e:
            return generator.validate(generator.DEFAULT_MODEL), f"modelo.json no válido ({e}): se muestra el de fábrica"
    return generator.validate(generator.DEFAULT_MODEL), "de fábrica (aún no existe opcua/modelo.json)"


class _UnixConn(http.client.HTTPConnection):
    def __init__(self, path: str) -> None:
        super().__init__("localhost")
        self._path = path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(30)
        self.sock.connect(self._path)


def docker_api(method: str, path: str) -> tuple[int, bytes]:
    c = _UnixConn(DOCKER_SOCK)
    try:
        c.request(method, path)
        r = c.getresponse()
        return r.status, r.read()
    finally:
        c.close()


def container_state() -> dict[str, Any]:
    if not Path(DOCKER_SOCK).exists():
        return {"available": False}
    try:
        st, body = docker_api("GET", f"/containers/{OPCUA_CONTAINER}/json")
    except OSError:
        return {"available": False}
    if st != 200:
        return {"available": True, "status": "no existe"}
    s = json.loads(body).get("State", {})
    started = s.get("StartedAt", "")
    try:
        ts = dt.datetime.fromisoformat(started[:26].rstrip("Z") + "+00:00").timestamp()
    except ValueError:
        ts = 0
    return {"available": True, "status": s.get("Status", "?"), "restarting": s.get("Restarting", False),
            "started": ts, "restarts": json.loads(body).get("RestartCount", 0)}


def container_logs(tail: int = 25) -> str:
    try:
        st, body = docker_api("GET", f"/containers/{OPCUA_CONTAINER}/logs?stdout=1&stderr=1&tail={tail}")
    except OSError:
        return ""
    out, i = [], 0
    while i + 8 <= len(body):   # flujo multiplexado: cabecera de 8 bytes por bloque
        n = int.from_bytes(body[i + 4:i + 8], "big")
        out.append(body[i + 8:i + 8 + n].decode(errors="replace"))
        i += 8 + n
    return "".join(out) or body.decode(errors="replace")


@app.get("/api/model")
def model_get() -> dict[str, Any]:
    model, source = load_model()
    disk = SERVER_PY.read_text(encoding="utf-8") if SERVER_PY.exists() else ""
    saved = MODEL_JSON.stat().st_mtime if MODEL_JSON.exists() else 0
    cs = container_state()
    return {"model": model, "source": source, "code_disk": disk, "saved": saved, "container": cs,
            "pending_restart": bool(cs.get("started")) and max(saved, SERVER_PY.stat().st_mtime if SERVER_PY.exists() else 0) > cs["started"],
            "types": list(generator.TYPES), "forms": sorted(generator.FORMS), "default": generator.DEFAULT_MODEL}


@app.post("/api/model/preview")
def model_preview(doc: ModelDoc) -> dict[str, Any]:
    try:
        g = generator.generate(doc.model)
    except generator.ModelError as e:
        return {"ok": False, "error": str(e)}
    except SyntaxError as e:
        return {"ok": False, "error": f"El código generado no compila: {e}"}
    return {"ok": True, "code": g["code"], "spans": g["spans"], "model": g["model"]}


@app.put("/api/model")
def model_put(doc: ModelDoc) -> dict[str, Any]:
    try:
        g = generator.generate(doc.model)
    except generator.ModelError as e:
        raise HTTPException(422, str(e))
    OPCUA_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_JSON.write_text(json.dumps(g["model"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SERVER_PY.write_text(g["code"], encoding="utf-8")
    return {"ok": True, "code": g["code"], "files": [str(MODEL_JSON.name), str(SERVER_PY.name)]}


async def _port_open(host: str, port: int) -> bool:
    try:
        _, w = await asyncio.wait_for(asyncio.open_connection(host, port), 1)
        w.close()
        return True
    except (OSError, asyncio.TimeoutError):
        return False


@app.post("/api/model/apply")
async def model_apply() -> dict[str, Any]:
    if not Path(DOCKER_SOCK).exists():
        raise HTTPException(501, f"No hay socket de Docker montado: ejecute en la terminal  docker compose restart {OPCUA_CONTAINER}")
    was_ours = S.client is not None and OPCUA_HOST in S.url
    if was_ours:
        await S.close()
    try:
        st, body = await asyncio.to_thread(docker_api, "POST", f"/containers/{OPCUA_CONTAINER}/restart?t=2")
    except OSError as e:
        raise HTTPException(502, f"No se pudo hablar con Docker: {e}")
    if st not in (200, 204):
        raise HTTPException(502, f"Docker respondió {st}: {body[:200]!r}")
    t0 = time.time()
    up = False
    while time.time() - t0 < 20:
        await asyncio.sleep(0.5)
        if await _port_open(OPCUA_HOST, 4840):
            up = True
            break
        if container_state().get("status") not in ("running", "restarting"):
            break
    out = {"ok": up, "seconds": round(time.time() - t0, 1), "container": container_state(), "reconnect": was_ours}
    if not up:
        out["logs"] = container_logs()
    return out


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "session": S.info(), "docker": Path(DOCKER_SOCK).exists()}


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
