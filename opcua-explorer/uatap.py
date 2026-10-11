"""
Escucha los bytes que el cliente asyncua envía y recibe, los separa en mensajes OPC UA Binary
(cabecera de 8 bytes: tipo + chunk + tamaño) y los decodifica con las propias clases de asyncua.

No modifica la librería: envuelve el transporte en connection_made y lee data_received.
Con seguridad None el cuerpo viaja en claro y se decodifica entero; con Sign&Encrypt solo se
verían las cabeceras (el explorador conecta hoy siempre con None).
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import enum
import struct
import time
from collections import deque
from typing import Any, Callable

from asyncua import ua
from asyncua.client.ua_client import UASocketProtocol
from asyncua.ua.ua_binary import nodeid_from_binary, struct_from_binary

MSG_TYPES = {"HEL": "Hello", "ACK": "Acknowledge", "OPN": "OpenSecureChannel", "MSG": "Message",
             "CLO": "CloseSecureChannel", "ERR": "Error", "RHE": "ReverseHello"}
CHUNKS = {"F": "Final", "C": "Intermedio", "A": "Abortado"}


class Recorder:
    """Anillo con los últimos mensajes; cada uno lleva un número correlativo para pedir «desde n»."""

    def __init__(self, size: int = 600) -> None:
        self.items: deque[dict[str, Any]] = deque(maxlen=size)
        self.seq = 0
        self._keepalive: set[int] = set()   # RequestId de las lecturas de vigilancia del propio cliente

    def add(self, direction: str, raw: bytes) -> None:
        self.seq += 1
        try:
            info = decode(raw)
        except Exception as e:  # noqa: BLE001 — un mensaje raro no debe tumbar la sesión
            info = {"type": raw[:3].decode(errors="replace"), "error": f"{type(e).__name__}: {e}", "fields": []}
        # Tráfico de fondo: Publish de la suscripción y el keep-alive de asyncua (lee ServerStatus.State, i=2259, cada pocos s)
        svc, rid = info.get("service", ""), info.get("request_id")
        bg = svc in ("PublishRequest", "PublishResponse")
        if svc == "ReadRequest" and info.get("summary") == "i=2259·Value":
            self._keepalive.add(rid)
            bg, info["summary"] = True, "i=2259·Value · keep-alive del cliente (ServerStatus.State)"
        elif svc == "ReadResponse" and rid in self._keepalive:
            self._keepalive.discard(rid)
            bg, info["summary"] = True, f"{info.get('summary', '')} · keep-alive: 0 = Running"
        self.items.append({"n": self.seq, "t": time.time(), "dir": direction, "size": len(raw), "bg": bg,
                           "hex": raw[:2048].hex(" "), "truncated": len(raw) > 2048, **info})

    def since(self, n: int) -> list[dict[str, Any]]:
        return [m for m in self.items if m["n"] > n]

    def clear(self) -> None:
        self.items.clear()


RECORDER = Recorder()


def _split(state: dict[str, bytes], data: bytes, direction: str, sink: Callable[[str, bytes], None]) -> None:
    buf = state.get(direction, b"") + data
    while len(buf) >= 8:
        size = int.from_bytes(buf[4:8], "little")
        if size < 8 or len(buf) < size:
            break
        sink(direction, buf[:size])
        buf = buf[size:]
    state[direction] = buf


class _TapTransport:
    def __init__(self, transport: Any, state: dict[str, bytes]) -> None:
        self._t, self._st = transport, state

    def write(self, data: Any) -> None:
        _split(self._st, bytes(data), "query", RECORDER.add)
        self._t.write(data)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._t, name)


def install() -> None:
    if getattr(UASocketProtocol, "_ot_lab_tap", False):
        return
    cm, dr = UASocketProtocol.connection_made, UASocketProtocol.data_received

    def connection_made(self: Any, transport: Any) -> None:
        self._tap_state = {}
        cm(self, _TapTransport(transport, self._tap_state))

    def data_received(self: Any, data: bytes) -> None:
        _split(self._tap_state, bytes(data), "response", RECORDER.add)
        dr(self, data)

    UASocketProtocol.connection_made, UASocketProtocol.data_received = connection_made, data_received
    UASocketProtocol._ot_lab_tap = True


# ---------------------------------------------------------------- decodificación
def plain(o: Any, depth: int = 0) -> Any:
    """Objeto asyncua → JSON legible (recortado: listas largas, bytes y profundidad)."""
    if depth > 6:
        return "…"
    if o is None or isinstance(o, (bool, int, float, str)):
        return o if not isinstance(o, str) or len(o) <= 200 else o[:200] + "…"
    if isinstance(o, enum.Enum):
        return o.name
    if isinstance(o, (bytes, bytearray)):
        return f"<{len(o)} bytes> " + o[:16].hex(" ") + (" …" if len(o) > 16 else "")
    if isinstance(o, _dt.datetime):
        return o.isoformat(timespec="milliseconds")
    if isinstance(o, (ua.NodeId, ua.ExpandedNodeId)):
        return o.to_string()
    if isinstance(o, ua.QualifiedName):
        return o.to_string()
    if isinstance(o, ua.LocalizedText):
        return o.Text
    if isinstance(o, ua.StatusCode):
        return o.name
    if isinstance(o, ua.Variant):
        return {"Value": plain(o.Value, depth + 1), "VariantType": o.VariantType.name}
    if isinstance(o, (list, tuple)):
        out = [plain(x, depth + 1) for x in o[:12]]
        if len(o) > 12:
            out.append(f"… y {len(o) - 12} más")
        return out
    if dataclasses.is_dataclass(o):
        return {f.name: plain(getattr(o, f.name), depth + 1) for f in dataclasses.fields(o) if f.name != "TypeId"}
    return str(o)[:200]


def _name(cls: type) -> str:
    return cls.__name__


def decode(raw: bytes) -> dict[str, Any]:
    """Cabecera OPC UA Binary campo a campo (con offsets para colorear los bytes) + cuerpo decodificado."""
    mt = raw[:3].decode(errors="replace")
    chunk = chr(raw[3])
    fields: list[dict[str, Any]] = [
        {"name": "MessageType", "from": 0, "to": 3, "value": f"{mt} · {MSG_TYPES.get(mt, '?')}", "cls": "fc"},
        {"name": "ChunkType", "from": 3, "to": 4, "value": f"{chunk} · {CHUNKS.get(chunk, '?')}", "cls": "hdr"},
        {"name": "MessageSize", "from": 4, "to": 8, "value": f"{len(raw)} bytes", "cls": "hdr"},
    ]
    out: dict[str, Any] = {"type": mt, "fields": fields, "service": MSG_TYPES.get(mt, mt), "body": None}
    if mt in ("HEL", "ACK", "ERR"):
        cls = {"HEL": ua.Hello, "ACK": ua.Acknowledge, "ERR": ua.ErrorMessage}[mt]
        body = struct_from_binary(cls, ua.utils.Buffer(raw[8:]))
        fields.append({"name": _name(cls), "from": 8, "to": len(raw), "value": "", "cls": "body"})
        out["body"] = plain(body)
        if mt == "HEL":
            out["summary"] = body.EndpointUrl
        elif mt == "ACK":
            out["summary"] = f"buffers {body.ReceiveBufferSize}/{body.SendBufferSize} · MaxMessageSize {body.MaxMessageSize}"
        return out

    chan = struct.unpack_from("<I", raw, 8)[0]
    fields.append({"name": "SecureChannelId", "from": 8, "to": 12, "value": chan, "cls": "hdr"})
    pos = 12
    if mt == "OPN":   # cabecera asimétrica: política, certificado del emisor, huella del certificado del receptor
        for name in ("SecurityPolicyUri", "SenderCertificate", "ReceiverCertificateThumbprint"):
            n = struct.unpack_from("<i", raw, pos)[0]
            ln = max(n, 0)
            val = raw[pos + 4:pos + 4 + ln]
            shown = val.decode(errors="replace") if name == "SecurityPolicyUri" else (f"{ln} bytes" if n >= 0 else "null")
            if name == "SecurityPolicyUri":
                out["policy"] = shown.rsplit("#", 1)[-1]
                shown = out["policy"]
            fields.append({"name": name, "from": pos, "to": pos + 4 + ln, "value": shown, "cls": "sec"})
            pos += 4 + ln
    else:             # cabecera simétrica: solo el token del canal seguro
        token = struct.unpack_from("<I", raw, pos)[0]
        fields.append({"name": "TokenId", "from": pos, "to": pos + 4, "value": token, "cls": "sec"})
        pos += 4
    seq, req = struct.unpack_from("<II", raw, pos)
    fields += [{"name": "SequenceNumber", "from": pos, "to": pos + 4, "value": seq, "cls": "seq"},
               {"name": "RequestId", "from": pos + 4, "to": pos + 8, "value": req, "cls": "seq"}]
    out.update({"channel": chan, "seqnum": seq, "request_id": req})
    pos += 8
    if out.get("policy") not in (None, "None") or chunk != "F":
        fields.append({"name": "Cuerpo", "from": pos, "to": len(raw), "value": "cifrado o en varios chunks: no se decodifica", "cls": "body"})
        return out
    b = ua.utils.Buffer(raw[pos:])
    nid = nodeid_from_binary(b)
    tid_to = pos + (len(raw) - pos - len(b))
    cls = ua.extension_objects_by_typeid.get(nid)
    service = _name(cls) if cls else f"? {nid.to_string()}"
    fields.append({"name": "TypeId (servicio)", "from": pos, "to": tid_to, "value": f"{nid.to_string()} · {service}", "cls": "fc"})
    fields.append({"name": "Cuerpo", "from": tid_to, "to": len(raw), "value": service, "cls": "body"})
    out["service"] = service
    if cls:
        body = struct_from_binary(cls, ua.utils.Buffer(raw[pos:]))   # las clases de asyncua leen su propio TypeId
        out["body"] = plain(body)
        out["summary"] = summarize(body)
    return out


def summarize(body: Any) -> str:
    """Una línea con lo esencial de cada servicio (lo que un estudiante busca en Wireshark)."""
    n = type(body).__name__
    try:
        if n == "ReadRequest":
            return ", ".join(f"{r.NodeId.to_string()}·{ua.AttributeIds(r.AttributeId).name}" for r in body.Parameters.NodesToRead[:4]) + (" …" if len(body.Parameters.NodesToRead) > 4 else "")
        if n == "ReadResponse":
            return ", ".join(str(plain(r.Value.Value))[:30] if r.Value else str(r.StatusCode.name) for r in body.Results[:4]) + (" …" if len(body.Results) > 4 else "")
        if n == "WriteRequest":
            return ", ".join(f"{w.NodeId.to_string()} ← {w.Value.Value.Value!r}" for w in body.Parameters.NodesToWrite[:4])
        if n == "WriteResponse":
            return ", ".join(s.name for s in body.Results)
        if n == "BrowseRequest":
            return ", ".join(d.NodeId.to_string() for d in body.Parameters.NodesToBrowse[:4])
        if n == "BrowseResponse":
            return f"{sum(len(r.References or []) for r in body.Results)} referencias"
        if n == "PublishResponse":
            items = [i for nm in (body.Parameters.NotificationMessage.NotificationData or []) for i in getattr(nm, "MonitoredItems", None) or []]
            return f"sub {body.Parameters.SubscriptionId} · {len(items)} cambio(s)" + (": " + ", ".join(str(plain(i.Value.Value.Value))[:16] for i in items[:4]) if items else " (keep-alive)")
        if n == "CreateSubscriptionRequest":
            return f"PublishingInterval {body.Parameters.RequestedPublishingInterval} ms"
        if n == "CreateMonitoredItemsRequest":
            return ", ".join(i.ItemToMonitor.NodeId.to_string() for i in body.Parameters.ItemsToCreate[:4])
        if n == "OpenSecureChannelRequest":
            return f"{body.Parameters.RequestType.name} · SecurityMode {body.Parameters.SecurityMode.name.rstrip('_')}"
        if n == "CreateSessionRequest":
            return body.Parameters.EndpointUrl or ""
        if n == "ActivateSessionRequest":
            tok = body.Parameters.UserIdentityToken
            return type(tok).__name__ if tok else ""
        if n.endswith("Response") and hasattr(body, "ResponseHeader"):
            return body.ResponseHeader.ServiceResult.name
    except Exception:  # noqa: BLE001
        return ""
    return ""
