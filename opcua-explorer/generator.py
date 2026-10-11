"""
Modelo del servidor OPC UA (opcua/modelo.json) → código Python de opcua/server.py.

El editor gráfico del explorador solo cambia el modelo; este módulo lo valida y escribe un server.py
legible, con una línea por cosa (objeto, variable, set_writable, simulación) para que se vea qué
línea nace de cada elemento. Devuelve también el rango de líneas de cada elemento («spans»).

Ampliable: «sim.forma» admite hoy ninguna/seno/coseno/rampa/aleatorio/pulso; la física del tanque
y el origen Modbus (pasarela) se añadirán como formas nuevas sin cambiar el resto.
"""
from __future__ import annotations

import re
from typing import Any

TYPES = {   # tipo OPC UA → (VariantType, conversión del valor, literal por defecto)
    "Boolean": ("Boolean", bool, False),
    "Int16": ("Int16", int, 0),
    "UInt16": ("UInt16", int, 0),
    "Int32": ("Int32", int, 0),
    "Float": ("Float", float, 0.0),
    "Double": ("Double", float, 0.0),
    "String": ("String", str, ""),
}
NUMERIC = {"Int16", "UInt16", "Int32", "Float", "Double"}
RANGES = {"Int16": (-32768, 32767), "UInt16": (0, 65535), "Int32": (-2**31, 2**31 - 1)}
FORMS = {"ninguna", "seno", "coseno", "rampa", "aleatorio", "pulso"}
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")

DEFAULT_MODEL: dict[str, Any] = {
    "servidor": {"nombre": "Lab OPC UA Python", "endpoint": "opc.tcp://0.0.0.0:4840/lab/",
                 "namespace": "http://lab.local", "ciclo_ms": 1000},
    "objetos": [
        {"nombre": "Tanque1", "icono": "tank", "variables": [
            {"nombre": "Nivel", "tipo": "Double", "valor": 0.0, "escribible": False, "icono": "drop", "unidad": "%",
             "sim": {"forma": "seno", "centro": 50, "amplitud": 30, "periodo_s": 63}},
            {"nombre": "Temperatura", "tipo": "Double", "valor": 20.0, "escribible": False, "icono": "thermo", "unidad": "°C",
             "sim": {"forma": "coseno", "centro": 20, "amplitud": 5, "periodo_s": 94}},
            {"nombre": "Valvula", "tipo": "Boolean", "valor": False, "escribible": True, "icono": "valve", "unidad": "",
             "sim": {"forma": "ninguna"}},
        ]},
        {"nombre": "PLC1", "icono": "plc", "variables": [
            {"nombre": "Temperatura", "tipo": "Double", "valor": 23.5, "escribible": False, "icono": "thermo", "unidad": "°C",
             "sim": {"forma": "aleatorio", "min": 22, "max": 26}},
            {"nombre": "LED", "tipo": "Boolean", "valor": False, "escribible": True, "icono": "led", "unidad": "",
             "sim": {"forma": "ninguna"}},
        ]},
    ],
}


class ModelError(ValueError):
    pass


def _num(x: Any, campo: str) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ModelError(f"{campo}: debe ser un número.")
    return float(x)


def _lit(x: float) -> str:
    """Número en el código: 50 en vez de 50.0 cuando es entero."""
    return str(int(x)) if float(x).is_integer() else repr(float(x))


def validate(model: dict[str, Any]) -> dict[str, Any]:
    """Comprueba el modelo y devuelve una copia normalizada (tipos y valores coherentes)."""
    srv = dict(model.get("servidor") or {})
    for k in ("nombre", "endpoint", "namespace"):
        if not isinstance(srv.get(k), str) or not srv[k].strip():
            raise ModelError(f"servidor.{k}: no puede estar vacío.")
    ep = re.match(r"^opc\.tcp://([^/:]+):(\d+)(/.*)?$", srv["endpoint"].strip())
    if not ep:
        raise ModelError("servidor.endpoint: formato opc.tcp://0.0.0.0:4840/ruta/")
    if ep.group(1) != "0.0.0.0" or ep.group(2) != "4840":
        raise ModelError("servidor.endpoint: mantenga 0.0.0.0:4840 (todas las interfaces del contenedor y el puerto que "
                         "publica docker-compose.yml); la ruta del final sí puede cambiarla.")
    srv["endpoint"] = srv["endpoint"].strip()
    ciclo = int(_num(srv.get("ciclo_ms", 1000), "servidor.ciclo_ms"))
    if not 100 <= ciclo <= 60000:
        raise ModelError("servidor.ciclo_ms: entre 100 y 60000 ms.")
    srv["ciclo_ms"] = ciclo
    objs, seen_obj = [], set()
    for i, o in enumerate(model.get("objetos") or []):
        name = str(o.get("nombre", "")).strip()
        if not NAME_RE.match(name):
            raise ModelError(f"Objeto {i + 1} «{name}»: use letras, números y _ (empezando por letra, sin tildes ni espacios).")
        if name.lower() in seen_obj:
            raise ModelError(f"Objeto «{name}» repetido.")
        seen_obj.add(name.lower())
        vars_, seen_var = [], set()
        for j, v in enumerate(o.get("variables") or []):
            vname = str(v.get("nombre", "")).strip()
            where = f"{name}.{vname or j + 1}"
            if not NAME_RE.match(vname):
                raise ModelError(f"Variable {where}: use letras, números y _ (empezando por letra, sin tildes ni espacios).")
            if vname.lower() in seen_var:
                raise ModelError(f"Variable {where} repetida en {name}.")
            seen_var.add(vname.lower())
            tipo = v.get("tipo", "Double")
            if tipo not in TYPES:
                raise ModelError(f"{where}: tipo «{tipo}» no soportado ({', '.join(TYPES)}).")
            conv = TYPES[tipo][1]
            try:
                valor = conv(v.get("valor", TYPES[tipo][2])) if tipo != "Boolean" else bool(v.get("valor"))
            except (TypeError, ValueError):
                raise ModelError(f"{where}: el valor inicial no es un {tipo}.")
            if tipo in RANGES and not RANGES[tipo][0] <= valor <= RANGES[tipo][1]:
                raise ModelError(f"{where}: {valor} no cabe en un {tipo} ({RANGES[tipo][0]}…{RANGES[tipo][1]}).")
            sim = dict(v.get("sim") or {"forma": "ninguna"})
            forma = sim.get("forma", "ninguna")
            if forma not in FORMS:
                raise ModelError(f"{where}: simulación «{forma}» desconocida.")
            if forma in ("seno", "coseno", "rampa", "aleatorio") and tipo not in NUMERIC:
                raise ModelError(f"{where}: la simulación «{forma}» necesita un tipo numérico.")
            if forma == "pulso" and tipo != "Boolean":
                raise ModelError(f"{where}: «pulso» es para variables Boolean.")
            if forma in ("seno", "coseno"):
                sim = {"forma": forma, "centro": _num(sim.get("centro", 0), f"{where}.centro"),
                       "amplitud": _num(sim.get("amplitud", 1), f"{where}.amplitud"),
                       "periodo_s": _num(sim.get("periodo_s", 60), f"{where}.periodo_s")}
            elif forma in ("rampa", "aleatorio"):
                orig = sim
                sim = {"forma": forma, "min": _num(orig.get("min", 0), f"{where}.min"), "max": _num(orig.get("max", 100), f"{where}.max")}
                if forma == "rampa":
                    sim["periodo_s"] = _num(orig.get("periodo_s", 60), f"{where}.periodo_s")
                if sim["min"] >= sim["max"]:
                    raise ModelError(f"{where}: min debe ser menor que max.")
            elif forma == "pulso":
                sim = {"forma": forma, "periodo_s": _num(sim.get("periodo_s", 2), f"{where}.periodo_s")}
            else:
                sim = {"forma": "ninguna"}
            if sim.get("periodo_s", 1) <= 0:
                raise ModelError(f"{where}: el periodo debe ser mayor que 0.")
            vars_.append({"nombre": vname, "tipo": tipo, "valor": valor, "escribible": bool(v.get("escribible")),
                          "icono": str(v.get("icono") or "gauge"), "unidad": str(v.get("unidad") or ""), "sim": sim})
        objs.append({"nombre": name, "icono": str(o.get("icono") or "plc"), "variables": vars_})
    return {"servidor": srv, "objetos": objs}


def _pyname(*parts: str) -> str:
    return "_".join(re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", p).lower() for p in parts)


def _sim_expr(v: dict[str, Any]) -> str | None:
    s, tipo = v["sim"], v["tipo"]
    f = s["forma"]
    if f in ("seno", "coseno"):
        fn = "sin" if f == "seno" else "cos"
        e = f"{_lit(s['centro'])} + {_lit(s['amplitud'])} * math.{fn}(2 * math.pi * t / {_lit(s['periodo_s'])})"
    elif f == "rampa":
        e = f"{_lit(s['min'])} + {_lit(s['max'] - s['min'])} * (t % {_lit(s['periodo_s'])}) / {_lit(s['periodo_s'])}"
    elif f == "aleatorio":
        e = f"random.uniform({_lit(s['min'])}, {_lit(s['max'])})"
    elif f == "pulso":
        return f"int(t // {_lit(s['periodo_s'])}) % 2 == 1"
    else:
        return None
    if tipo == "Double":
        return e
    if tipo == "Float":
        return f"ua.Variant({e}, ua.VariantType.Float)"
    return f"ua.Variant(round({e}), ua.VariantType.{tipo})"


def _sim_comment(v: dict[str, Any]) -> str:
    s = v["sim"]
    return {"seno": "senoide", "coseno": "cosenoide", "rampa": "diente de sierra", "aleatorio": "ruido uniforme",
            "pulso": "conmuta ON/OFF"}.get(s["forma"], "")


def generate(model: dict[str, Any]) -> dict[str, Any]:
    """Devuelve {"code": str, "spans": {clave: [desde, hasta]}} con líneas 1-based (claves srv, obj:i, var:i:j, sim:i:j)."""
    m = validate(model)
    srv = m["servidor"]
    L: list[str] = []
    spans: dict[str, list[int]] = {}

    def mark(key: str, start: int) -> None:
        spans.setdefault(key, [start, len(L)])
        spans[key][1] = len(L)

    L += ['"""',
          "opcua-py · servidor OPC UA del laboratorio (asyncua)",
          "GENERADO por el Explorador OPC UA (http://localhost:8600) a partir de opcua/modelo.json.",
          "Si lo edita a mano, el editor lo sobrescribe al guardar: cambie el modelo, no este archivo.",
          '"""',
          "import asyncio",
          "import math",
          "import random",
          "",
          "from asyncua import Server, ua",
          "",
          "",
          "async def main():"]
    s0 = len(L) + 1
    L += ["    srv = Server()",
          "    await srv.init()",
          f"    srv.set_endpoint({srv['endpoint']!r})",
          f"    srv.set_server_name({srv['nombre']!r})",
          f"    ns = await srv.register_namespace({srv['namespace']!r})   # índice 2: el primero tras los de la norma",
          "    objetos = srv.nodes.objects   # carpeta Objects (ns=0;i=85)"]
    mark("srv", s0)

    for i, o in enumerate(m["objetos"]):
        L.append("")
        s0 = len(L) + 1
        oname = o["nombre"]
        ov = _pyname(oname)
        L.append(f"    # ── {oname} " + "─" * max(4, 60 - len(oname)))
        L.append(f'    {ov} = await objetos.add_object(f"ns={{ns}};s={oname}", f"{{ns}}:{oname}")')
        mark(f"obj:{i}", s0)
        for j, v in enumerate(o["variables"]):
            s1 = len(L) + 1
            vv = _pyname(oname, v["nombre"])
            vt = TYPES[v["tipo"]][0]
            init = repr(v["valor"])
            unit = f"   # {v['unidad']}" if v["unidad"] else ""
            L.append(f'    {vv} = await {ov}.add_variable(f"ns={{ns}};s={oname}.{v["nombre"]}", f"{{ns}}:{v["nombre"]}", '
                     f"{init}, ua.VariantType.{vt}){unit}")
            if v["escribible"]:
                L.append(f"    await {vv}.set_writable()   # los clientes pueden escribirla")
            mark(f"var:{i}:{j}", s1)
            spans[f"obj:{i}"][1] = len(L)

    sims = [(i, j, v) for i, o in enumerate(m["objetos"]) for j, v in enumerate(o["variables"]) if _sim_expr(v)]
    dt = srv["ciclo_ms"] / 1000
    L += ["",
          "    t = 0.0   # segundos desde el arranque",
          "    async with srv:",
          "        while True:"]
    if sims:
        L.append(f"            # simulación: un valor nuevo cada {srv['ciclo_ms']} ms")
    for i, j, v in sims:
        s1 = len(L) + 1
        vv = _pyname(m["objetos"][i]["nombre"], v["nombre"])
        L.append(f"            await {vv}.write_value({_sim_expr(v)})   # {_sim_comment(v)}")
        mark(f"sim:{i}:{j}", s1)
    L += [f"            await asyncio.sleep({_lit(dt)})",
          f"            t += {_lit(dt)}",
          "",
          "",
          "asyncio.run(main())",
          ""]
    code = "\n".join(L)
    compile(code, "server.py", "exec")   # nunca se escribe un server.py con errores de sintaxis
    return {"code": code, "spans": spans, "model": m}
