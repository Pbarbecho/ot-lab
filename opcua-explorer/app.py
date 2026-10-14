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
import inspect
import json
import logging
import os
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from asyncua import Client, ua
from asyncua.crypto import cert_gen, security_policies as secpol
from asyncua.ua.uaerrors import UaStatusCodeError
from cryptography.x509.oid import ExtendedKeyUsageOID
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
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
CERT_DIR = Path(os.environ.get("CERT_DIR", "/app/certs"))
CAPTURES = Path(os.environ.get("CAPTURES_DIR", "/app/captures"))
APP_URI = "urn:ot-lab:opcua-explorer"
POLICIES = {   # nombre de la norma → clase asyncua
    "None": secpol.SecurityPolicyNone,
    "Basic256Sha256": secpol.SecurityPolicyBasic256Sha256,
    "Aes128_Sha256_RsaOaep": secpol.SecurityPolicyAes128Sha256RsaOaep,
    "Aes256_Sha256_RsaPss": secpol.SecurityPolicyAes256Sha256RsaPss,
    "Basic128Rsa15": secpol.SecurityPolicyBasic128Rsa15,
    "Basic256": secpol.SecurityPolicyBasic256,
}
MODES = {"None": ua.MessageSecurityMode.None_, "Sign": ua.MessageSecurityMode.Sign, "SignAndEncrypt": ua.MessageSecurityMode.SignAndEncrypt}

TARGETS = [
    {"id": "opcua-py", "label": "opcua-py · servidor propio (Python)", "url": "opc.tcp://172.28.0.21:4840/lab/",
     "note": "El que define el editor de esta web · opcua/modelo.json → opcua/server.py"},
    {"id": "opc-plc", "label": "opc-plc · simulador de Microsoft", "url": "opc.tcp://172.28.0.20:50000",
     "note": "Nodos de prueba en Objects/OpcPlc/Telemetry (rampas, aleatorios, picos)"},
    {"id": "ignition", "label": "ignition · servidor OPC UA del gateway", "url": "opc.tcp://172.28.0.50:62541",
     "note": "Viene desactivado: actívelo en http://localhost:8088/web/config/opcua.settings (Config → OPC UA → Server Settings), marque Expose Tag Providers y admita None/Anónimo"},
]

app = FastAPI(title="Explorador OPC UA · ot-lab")
CERT_DIR.mkdir(parents=True, exist_ok=True)
CAPTURES.mkdir(parents=True, exist_ok=True)
CLIENT_KEY, CLIENT_CERT = CERT_DIR / "explorer_key.pem", CERT_DIR / "explorer_cert.der"


async def ensure_client_cert() -> None:
    """Certificado autofirmado del cliente: necesario para cualquier política distinta de None."""
    if CLIENT_KEY.exists() and CLIENT_CERT.exists():
        return
    r = cert_gen.setup_self_signed_certificate(CLIENT_KEY, CLIENT_CERT, APP_URI, socket.gethostname(),
                                               [ExtendedKeyUsageOID.CLIENT_AUTH],
                                               {"countryName": "EC", "organizationName": "Universidad de Cuenca", "commonName": "opcua-explorer"})
    if inspect.isawaitable(r):
        await r


@app.on_event("startup")
async def _startup() -> None:
    try:
        await ensure_client_cert()
    except Exception as e:  # noqa: BLE001
        logging.getLogger("explorer").warning("no se pudo crear el certificado del cliente: %s", e)


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
        self.security: dict[str, Any] = {"policy": "None", "mode": "None", "user": ""}

    @property
    def connected(self) -> bool:
        try:
            proto = self.client.uaclient.protocol if self.client else None
            state = getattr(proto, "state", None)
            return bool(proto and str(getattr(state, "value", state)).lower() == "open")
        except Exception:  # noqa: BLE001
            return False

    def info(self) -> dict[str, Any]:
        return {"connected": self.connected, "url": self.url, "interval": self.interval, "security": self.security}

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
    policy: str = Field("None", pattern="^(None|Basic256Sha256|Aes128_Sha256_RsaOaep|Aes256_Sha256_RsaPss|Basic128Rsa15|Basic256)$")
    mode: str = Field("None", pattern="^(None|Sign|SignAndEncrypt)$")
    user: str = ""
    password: str = ""


class NodeReq(BaseModel):
    node: str


class WatchReq(BaseModel):
    node: str
    sampling: float = Field(0, ge=0, le=60000)
    queue: int = Field(1, ge=1, le=1000)
    deadband: float | None = Field(None, ge=0)


class WriteReq(BaseModel):
    node: str
    value: Any


@app.get("/api/targets")
def targets() -> dict[str, Any]:
    return {"targets": TARGETS, "session": S.info(), "policies": list(POLICIES), "modes": list(MODES)}


@app.post("/api/connect")
async def connect(req: ConnectReq) -> dict[str, Any]:
    await S.close()
    uatap.RECORDER.clear()
    uatap.SECURITY.update({"policy": req.policy, "mode": req.mode if req.policy != "None" else "None"})
    n0 = uatap.RECORDER.seq
    c = Client(req.url, timeout=5)
    c.session_timeout = 600000
    c.application_uri = APP_URI
    if req.policy != "None":
        if req.mode == "None":
            raise HTTPException(422, "Con una política cifrada elija el modo Sign o SignAndEncrypt.")
        await ensure_client_cert()
        try:
            await c.set_security(POLICIES[req.policy], str(CLIENT_CERT), str(CLIENT_KEY), mode=MODES[req.mode])
        except Exception as e:  # noqa: BLE001
            raise HTTPException(422, f"No se pudo preparar la seguridad {req.policy}/{req.mode}: {status_name(e)}")
    if req.user:
        c.set_user(req.user)
        c.set_password(req.password)
    try:
        await asyncio.wait_for(c.connect(), 15)
    except Exception as e:  # noqa: BLE001
        try:
            c.disconnect_socket()
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(502, f"No se pudo conectar a {req.url}: {status_name(e)}. ¿Está el contenedor arriba y en la red ot-lab?")
    S.client, S.url, S.interval = c, req.url, req.interval
    S.security = {"policy": req.policy, "mode": req.mode if req.policy != "None" else "None", "user": req.user}
    ns = await c.get_namespace_array()
    return {**S.info(), "namespaces": ns, "messages": uatap.RECORDER.since(n0),
            "asyncua": "c = Client(" + repr(req.url) + ")"
                       + (f"\nawait c.set_security(SecurityPolicy{req.policy.replace('_', '')}, 'cert.der', 'key.pem', mode=MessageSecurityMode.{req.mode})" if req.policy != "None" else "")
                       + (f"\nc.set_user({req.user!r}); c.set_password('…')" if req.user else "")
                       + "\nawait c.connect()"}


@app.get("/api/endpoints")
async def endpoints(url: str) -> dict[str, Any]:
    """GetEndpoints sin crear sesión: qué políticas, modos y tokens de usuario ofrece el servidor (lo primero que hace UaExpert)."""
    if not url.startswith("opc.tcp://"):
        raise HTTPException(422, "La URL debe empezar por opc.tcp://")
    n0 = uatap.RECORDER.seq
    c = Client(url, timeout=5)
    try:
        eps = await asyncio.wait_for(c.connect_and_get_server_endpoints(), 10)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"No se pudo pedir los endpoints de {url}: {status_name(e)}")
    out = []
    for e in eps:
        out.append({"url": e.EndpointUrl, "policy": e.SecurityPolicyUri.rsplit("#", 1)[-1], "mode": e.SecurityMode.name.rstrip("_"),
                    "level": e.SecurityLevel, "tokens": [t.TokenType.name for t in e.UserIdentityTokens],
                    "server": e.Server.ApplicationName.Text if e.Server and e.Server.ApplicationName else "",
                    "cert": bool(e.ServerCertificate)})
    return {"endpoints": out, "messages": uatap.RECORDER.since(n0), "asyncua": f"eps = await Client({url!r}).connect_and_get_server_endpoints()"}


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
    res = await S.op(lambda: S.client.get_node(nid).read_data_value(), f"dv = await c.get_node({req.node!r}).read_data_value()   # DataValue: valor, estado y marcas de tiempo")
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
    INT_RANGES = {ua.VariantType.SByte: (-128, 127), ua.VariantType.Byte: (0, 255), ua.VariantType.Int16: (-32768, 32767),
                  ua.VariantType.UInt16: (0, 65535), ua.VariantType.Int32: (-2**31, 2**31 - 1), ua.VariantType.UInt32: (0, 2**32 - 1),
                  ua.VariantType.Int64: (-2**63, 2**63 - 1), ua.VariantType.UInt64: (0, 2**64 - 1)}
    if vt in INT_RANGES:
        try:
            n = int(s)
        except ValueError:
            raise HTTPException(422, f"«{s}» no es un entero ({vt.name}).")
        lo, hi = INT_RANGES[vt]
        if not lo <= n <= hi:
            raise HTTPException(422, f"{n} no cabe en un {vt.name} ({lo} … {hi}): el cliente lo rechaza antes de enviar la WriteRequest.")
        return n
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


class CallReq(BaseModel):
    obj: str
    method: str
    args: list[Any] = []


@app.post("/api/call")
async def call(req: CallReq) -> dict[str, Any]:
    """Servicio Call: ejecuta un método del servidor (CallRequest / CallResponse)."""
    onid, mnid = _nid(req.obj), _nid(req.method)
    res = await S.op(lambda: S.client.get_node(onid).call_method(mnid, *req.args),
                     f"await c.get_node({req.obj!r}).call_method({req.method!r}{''.join(', ' + repr(a) for a in req.args)})")
    r = res.pop("result")
    res.update({"ok": res["error"] is None, "output": uatap.plain(r)})
    return res


# ---------------------------------------------------------------- suscripción
async def _ensure_sub() -> None:
    if S.sub is None:
        S.sub = await S.client.create_subscription(S.interval, S.watch)


async def _watch(nodes: list[tuple[str, str]], sampling: float = 0, queue: int = 1, deadband: float | None = None) -> dict[str, Any]:
    """nodes: [(nodeid, etiqueta)]; crea los MonitoredItems que falten en una sola petición.
    sampling: SamplingInterval en ms (0 = el más rápido que admita el servidor) · queue: QueueSize · deadband: banda muerta absoluta."""
    new = [(n, label) for n, label in nodes if n not in S.handles]

    async def run():
        await _ensure_sub()
        if not new:
            return []
        objs = [S.client.get_node(n) for n, _ in new]
        for n, label in new:
            S.watch.items[n] = {"node": n, "label": label, "value": None, "status": "—", "count": 0,
                                "sampling": sampling, "queue": queue, "deadband": deadband}
        flt = None
        if deadband is not None and deadband > 0:
            flt = ua.DataChangeFilter(Trigger=ua.DataChangeTrigger.StatusValue, DeadbandType=ua.DeadbandType.Absolute, DeadbandValue=float(deadband))
        handles = await S.sub.subscribe_data_change(objs, sampling_interval=sampling, queuesize=queue, **({"datachange_filter": flt} if flt else {}))
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

    extra = f", sampling_interval={sampling}, queuesize={queue}" + (f", datachange_filter=DataChangeFilter(Deadband {deadband})" if deadband else "")
    py = (f"sub = await c.create_subscription({S.interval}, manejador)   # PublishingInterval {S.interval} ms\n"
          f"await sub.subscribe_data_change([{', '.join(repr(n) for n, _ in new[:3])}{', …' if len(new) > 3 else ''}]{extra})")
    res = await S.op(run, py)
    res["rejected"] = res.pop("result") or []
    return res


@app.post("/api/watch")
async def watch_add(req: WatchReq) -> dict[str, Any]:
    _nid(req.node)
    return await _watch([(req.node, req.node)], req.sampling, req.queue, req.deadband)


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


# ---------------------------------------------------------------- captura (tcpdump dentro del contenedor) → Wireshark
class Capture:
    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.file: Path | None = None
        self.started = 0.0

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def info(self) -> dict[str, Any]:
        size = self.file.stat().st_size if self.file and self.file.exists() else 0
        return {"running": self.running, "file": self.file.name if self.file else None, "bytes": size,
                "seconds": round(time.time() - self.started, 1) if self.running else 0, "tcpdump": shutil.which("tcpdump") is not None}

    def start(self, ports: list[int]) -> dict[str, Any]:
        if self.running:
            return self.info()
        if shutil.which("tcpdump") is None:
            raise HTTPException(500, "tcpdump no está instalado en la imagen.")
        self.file = CAPTURES / f"opcua_{dt.datetime.now():%Y%m%d_%H%M%S}.pcap"
        flt = " or ".join(f"tcp port {p}" for p in ports) or "tcp"
        self.proc = subprocess.Popen(["tcpdump", "-i", "any", "-U", "-s", "0", "-w", str(self.file), flt], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        # la tubería de stderr solo se lee si tcpdump muere al arrancar; después no debe llenarse (tcpdump calla con -w)
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
    ports: list[int] = [4840, 50000, 62541]


@app.get("/api/capture")
def capture_status() -> dict[str, Any]:
    return CAPTURE.info()


@app.post("/api/capture/start")
def capture_start(req: CaptureReq) -> dict[str, Any]:
    return CAPTURE.start(req.ports)


@app.post("/api/capture/stop")
def capture_stop() -> dict[str, Any]:
    return CAPTURE.stop()


@app.get("/api/capture/list")
def capture_list() -> dict[str, Any]:
    files = sorted(CAPTURES.glob("*.pcap*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return {"files": [{"name": p.name, "bytes": p.stat().st_size, "mtime": dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")} for p in files[:30]]}


@app.get("/api/capture/file/{name}")
def capture_file(name: str) -> FileResponse:
    p = CAPTURES / Path(name).name
    if not p.exists():
        raise HTTPException(404, "No existe esa captura.")
    return FileResponse(p, media_type="application/vnd.tcpdump.pcap", filename=p.name)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "session": S.info(), "docker": Path(DOCKER_SOCK).exists(), "capture": CAPTURE.info(), "policies": list(POLICIES), "modes": list(MODES)}


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
