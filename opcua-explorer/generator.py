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
    "UInt32": ("UInt32", int, 0),
    "Int64": ("Int64", int, 0),
    "Float": ("Float", float, 0.0),
    "Double": ("Double", float, 0.0),
    "String": ("String", str, ""),
}
NUMERIC = {"Int16", "UInt16", "Int32", "UInt32", "Int64", "Float", "Double"}
RANGES = {"Int16": (-32768, 32767), "UInt16": (0, 65535), "Int32": (-2**31, 2**31 - 1), "UInt32": (0, 2**32 - 1), "Int64": (-2**63, 2**63 - 1)}
FORMS = {"ninguna", "seno", "coseno", "rampa", "aleatorio", "pulso", "modbus"}
MODBUS_TABLES = {"hr": "read_holding_registers", "ir": "read_input_registers", "coils": "read_coils", "di": "read_discrete_inputs"}
POLICIES = ["Basic256Sha256", "Aes128_Sha256_RsaOaep", "Aes256_Sha256_RsaPss", "Basic128Rsa15", "Basic256"]
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")

DEFAULT_MODEL: dict[str, Any] = {
    "servidor": {"nombre": "Lab OPC UA Python", "endpoint": "opc.tcp://0.0.0.0:4840/lab/",
                 "namespace": "http://lab.local", "ciclo_ms": 1000,
                 "seguridad": {"none": True, "politicas": [], "usuarios": []}},
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
    seg = dict(srv.get("seguridad") or {})
    pols = [p for p in (seg.get("politicas") or []) if p in POLICIES]
    users = []
    for u in seg.get("usuarios") or []:
        name, pw = str(u.get("usuario", "")).strip(), str(u.get("clave", ""))
        if name and not re.match(r"^[A-Za-z0-9_.@-]{1,32}$", name):
            raise ModelError(f"Usuario «{name}»: solo letras, números y . _ @ -")
        if name and not pw:
            raise ModelError(f"Usuario «{name}»: falta la clave.")
        if name:
            users.append({"usuario": name, "clave": pw})
    none_ok = bool(seg.get("none", True))
    if not none_ok and not pols:
        raise ModelError("servidor.seguridad: si quita la política None, elija al menos una política cifrada.")
    srv["seguridad"] = {"none": none_ok, "politicas": pols, "usuarios": users}
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
            if forma == "modbus" and tipo == "String":
                raise ModelError(f"{where}: la pasarela Modbus necesita un tipo numérico o Boolean.")
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
            elif forma == "modbus":
                orig = sim
                tabla = str(orig.get("tabla", "hr"))
                if tabla not in MODBUS_TABLES:
                    raise ModelError(f"{where}: tabla Modbus «{tabla}» (use hr, ir, coils o di).")
                if tabla in ("coils", "di") and tipo != "Boolean":
                    raise ModelError(f"{where}: las tablas de bits (coils, di) van en una variable Boolean.")
                if tabla in ("hr", "ir") and tipo == "Boolean":
                    raise ModelError(f"{where}: los registros (hr, ir) van en una variable numérica.")
                host = str(orig.get("host", "172.28.0.30")).strip()
                if not re.match(r"^[A-Za-z0-9_.-]+$", host):
                    raise ModelError(f"{where}: host Modbus no válido.")
                sim = {"forma": "modbus", "host": host, "puerto": int(_num(orig.get("puerto", 5020), f"{where}.puerto")),
                       "unit": int(_num(orig.get("unit", 1), f"{where}.unit")), "tabla": tabla,
                       "direccion": int(_num(orig.get("direccion", 0), f"{where}.direccion")),
                       "escala": _num(orig.get("escala", 1), f"{where}.escala")}
                if not 0 <= sim["direccion"] <= 65535 or not 1 <= sim["puerto"] <= 65535:
                    raise ModelError(f"{where}: dirección o puerto Modbus fuera de rango.")
            else:
                sim = {"forma": "ninguna"}
            rango = v.get("rango")
            if rango is not None and rango != "":
                try:
                    lo, hi = float(rango[0]), float(rango[1])
                except (TypeError, ValueError, IndexError):
                    raise ModelError(f"{where}: el rango debe ser [mínimo, máximo].")
                if lo >= hi:
                    raise ModelError(f"{where}: rango mínimo < máximo.")
                rango = [lo, hi]
            elif sim["forma"] in ("seno", "coseno"):
                rango = [sim["centro"] - sim["amplitud"], sim["centro"] + sim["amplitud"]]
            elif sim["forma"] in ("rampa", "aleatorio"):
                rango = [sim["min"], sim["max"]]
            else:
                rango = None
            if sim.get("periodo_s", 1) <= 0:
                raise ModelError(f"{where}: el periodo debe ser mayor que 0.")
            vars_.append({"nombre": vname, "tipo": tipo, "valor": valor, "escribible": bool(v.get("escribible")),
                          "icono": str(v.get("icono") or "gauge"), "unidad": str(v.get("unidad") or ""), "sim": sim,
                          "rango": rango if tipo in NUMERIC else None})
        objs.append({"nombre": name, "icono": str(o.get("icono") or "plc"), "variables": vars_, "metodo_reset": bool(o.get("metodo_reset"))})
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
    elif f == "modbus":
        fn = MODBUS_TABLES[s["tabla"]]
        bits = s["tabla"] in ("coils", "di")
        e = f"leer_modbus({s['host']!r}, {s['puerto']}, {s['unit']}, {fn!r}, {s['direccion']}, {_lit(s['escala'])}, {bits})"
        if tipo == "Boolean":
            return e
    else:
        return None
    if tipo == "Double":
        return e
    if tipo == "Float":
        return f"ua.Variant({e}, ua.VariantType.Float)"
    return f"ua.Variant(round({e}), ua.VariantType.{tipo})"


def _sim_comment(v: dict[str, Any]) -> str:
    s = v["sim"]
    if s["forma"] == "modbus":
        return f"pasarela Modbus: {s['tabla'].upper()} {s['direccion']} de {s['host']}:{s['puerto']}" + (f" ×{_lit(s['escala'])}" if s["escala"] != 1 else "")
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

    seg = srv["seguridad"]
    uses_modbus = any(v["sim"]["forma"] == "modbus" for o in m["objetos"] for v in o["variables"])
    L += ['"""',
          "opcua-py · servidor OPC UA del laboratorio (asyncua)",
          "GENERADO por el Explorador OPC UA (http://localhost:8600) a partir de opcua/modelo.json.",
          "Si lo edita a mano, el editor lo sobrescribe al guardar: cambie el modelo, no este archivo.",
          '"""',
          "import asyncio",
          "import math",
          "import random",
          "",
          "from asyncua import Server, ua"]
    if seg["politicas"]:
        L += ["from asyncua.crypto.cert_gen import setup_self_signed_certificate",
              "from cryptography.x509.oid import ExtendedKeyUsageOID",
              "from pathlib import Path"]
    if seg["usuarios"]:
        L += ["from asyncua.server.user_managers import UserManager",
              "from asyncua.crypto.permission_rules import User, UserRole"]
    if uses_modbus:
        L += ["from pymodbus.client import ModbusTcpClient"]
    L += ["", ""]
    if seg["usuarios"]:
        L += ["USUARIOS = {" + ", ".join(f"{u['usuario']!r}: {u['clave']!r}" for u in seg["usuarios"]) + "}   # usuario → clave (solo laboratorio)",
              "",
              "",
              "class Usuarios(UserManager):",
              '    """ActivateSession con UserNameIdentityToken: acepta solo los usuarios de la tabla (y el anónimo si está permitido)."""',
              "",
              "    def get_user(self, iserver, username=None, password=None, certificate=None):",
              "        if username is None:" + ("" if seg["none"] else "   # sin token de usuario"),
              "            return " + ("User(role=UserRole.User)   # anónimo permitido" if seg["none"] else "None   # anónimo rechazado: BadIdentityTokenRejected"),
              "        if USUARIOS.get(username) == password:",
              "            return User(role=UserRole.Admin if username == 'admin' else UserRole.User)",
              "        return None   # clave incorrecta",
              "", ""]
    if uses_modbus:
        L += ["_modbus = {}",
              "",
              "",
              "def leer_modbus(host, puerto, unit, funcion, direccion, escala, bits):",
              '    """Pasarela: lee un registro o bit Modbus TCP y lo entrega como valor OPC UA (None si el esclavo no responde)."""',
              "    c = _modbus.get((host, puerto))",
              "    if c is None or not c.connected:",
              "        c = ModbusTcpClient(host, port=puerto, timeout=1, retries=0)",
              "        c.connect()",
              "        _modbus[(host, puerto)] = c",
              "    r = getattr(c, funcion)(direccion, count=1, device_id=unit)",
              "    if r.isError():",
              "        return None",
              "    return bool(r.bits[0]) if bits else r.registers[0] * escala",
              "", ""]
    L += ["async def main():"]
    s0 = len(L) + 1
    L += ["    srv = Server(" + ("user_manager=Usuarios()" if seg["usuarios"] else "") + ")",
          "    await srv.init()",
          f"    srv.set_endpoint({srv['endpoint']!r})",
          f"    srv.set_server_name({srv['nombre']!r})",
          "    await srv.set_application_uri('urn:ot-lab:opcua-py')   # debe coincidir con el certificado del servidor"]
    if seg["politicas"]:
        L += ["    # certificado autofirmado del servidor (se crea una vez en /app/certs y se reutiliza)",
              "    certs = Path('/app/certs'); certs.mkdir(exist_ok=True)",
              "    await setup_self_signed_certificate(certs / 'server_key.pem', certs / 'server_cert.der', 'urn:ot-lab:opcua-py', 'opcua-py',",
              "                                        [ExtendedKeyUsageOID.SERVER_AUTH], {'countryName': 'EC', 'organizationName': 'Universidad de Cuenca', 'commonName': 'opcua-py'})",
              "    await srv.load_certificate(str(certs / 'server_cert.der'))",
              "    await srv.load_private_key(str(certs / 'server_key.pem'))",
              "    srv.set_security_policy([" + ", ".join((["ua.SecurityPolicyType.NoSecurity"] if seg["none"] else [])
                                                         + [f"ua.SecurityPolicyType.{p}_{mode}" for p in seg["politicas"] for mode in ("Sign", "SignAndEncrypt")]) + "])",
              "    srv.set_identity_tokens([ua.AnonymousIdentityToken, ua.UserNameIdentityToken])" if (seg["usuarios"] and seg["none"]) else
              ("    srv.set_identity_tokens([ua.UserNameIdentityToken])" if seg["usuarios"] else "    srv.set_identity_tokens([ua.AnonymousIdentityToken])")]
    elif seg["usuarios"]:
        L += ["    srv.set_identity_tokens([ua.AnonymousIdentityToken, ua.UserNameIdentityToken])" if seg["none"] else "    srv.set_identity_tokens([ua.UserNameIdentityToken])"]
    L += [f"    ns = await srv.register_namespace({srv['namespace']!r})   # índice 2: el primero tras los de la norma",
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
            if v["unidad"]:
                L.append(f'    await {vv}.add_property(f"ns={{ns}};s={oname}.{v["nombre"]}.EngineeringUnits", "EngineeringUnits", {v["unidad"]!r})   # unidad visible en UaExpert/Ignition')
            if v.get("rango"):
                lo, hi = v["rango"]
                L.append(f'    await {vv}.add_property(f"ns={{ns}};s={oname}.{v["nombre"]}.EURange", "EURange", ua.Range(Low={_lit(lo)}, High={_lit(hi)}))   # rango de ingeniería')
            mark(f"var:{i}:{j}", s1)
            spans[f"obj:{i}"][1] = len(L)
        if o["metodo_reset"]:
            s1 = len(L) + 1
            inits = [(_pyname(oname, v["nombre"]), repr(v["valor"]), TYPES[v["tipo"]][0]) for v in o["variables"] if v["escribible"]]
            L.append(f"    async def {ov}_reiniciar(parent):   # método Reiniciar: devuelve las variables escribibles a su valor inicial")
            for vv, init, vt in inits:
                L.append(f"        await {vv}.write_value(ua.Variant({init}, ua.VariantType.{vt}))")
            if not inits:
                L.append("        pass   # (sin variables escribibles)")
            L.append(f"        return [ua.Variant({len(inits)}, ua.VariantType.Int32)]   # cuántas se reiniciaron")
            L.append(f'    await {ov}.add_method(f"ns={{ns}};s={oname}.Reiniciar", f"{{ns}}:Reiniciar", {ov}_reiniciar, [], [ua.VariantType.Int32])')
            mark(f"met:{i}", s1)
            spans[f"obj:{i}"][1] = len(L)

    sims = [(i, j, v) for i, o in enumerate(m["objetos"]) for j, v in enumerate(o["variables"]) if _sim_expr(v)]
    dt = srv["ciclo_ms"] / 1000
    L += ["",
          "    t = 0.0   # segundos desde el arranque",
          "    async with srv:",
          "        while True:"]
    if sims:
        L.append(f"            # simulación y pasarela: un valor nuevo cada {srv['ciclo_ms']} ms")
    for i, j, v in sims:
        s1 = len(L) + 1
        vv = _pyname(m["objetos"][i]["nombre"], v["nombre"])
        if v["sim"]["forma"] == "modbus":
            L.append(f"            _v = {_sim_expr(v)}   # {_sim_comment(v)}")
            L.append(f"            if _v is not None:")
            L.append(f"                await {vv}.write_value(ua.Variant({'bool(_v)' if v['tipo'] == 'Boolean' else ('float(_v)' if v['tipo'] in ('Float', 'Double') else 'round(_v)')}, ua.VariantType.{TYPES[v['tipo']][0]}))")
        else:
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
