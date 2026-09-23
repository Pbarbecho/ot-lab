#!/usr/bin/env bash
# Taller 4 · OT-LAB · §4.5.1 — Comprobación 3: el servidor OPC UA publica datos
# Lee (o escribe) una variable de un objeto OPC UA desde un contenedor temporal en la red Docker del laboratorio.
# Resultado esperado con los valores por defecto:  Tanque1.Nivel = 48.01 (Double)   [entre 20 y 80, cambia cada segundo]
#
# Uso:  ./scripts/comprobacion3_opcua.sh [-n RED] [-e ENDPOINT] [-o OBJETO] [-v VARIABLE] [-s NS] [-w VALOR] [-l]
#   -n  red Docker en la que vive el servidor  (por defecto: ot-lab_ot-lab, la que crea compose)
#   -e  endpoint OPC UA                        (por defecto: opc.tcp://172.28.0.21:4840/lab/)
#   -o  objeto bajo Objects                    (por defecto: Tanque1)
#   -v  variable del objeto                    (por defecto: Nivel)
#   -s  índice de namespace del objeto         (por defecto: 2 = http://lab.local)
#   -w  escribir VALOR en la variable antes de leerla (solo las escribibles, p. ej. Valvula true)
#   -l  listar las variables del objeto en lugar de leer una
#   -h  esta ayuda
# Ej.:  ./scripts/comprobacion3_opcua.sh                          # Tanque1.Nivel
#       ./scripts/comprobacion3_opcua.sh -v Temperatura            # otra variable
#       ./scripts/comprobacion3_opcua.sh -l                        # ¿qué hay en Tanque1?
#       ./scripts/comprobacion3_opcua.sh -v Valvula -w true        # escribir y releer
#       ./scripts/comprobacion3_opcua.sh -e opc.tcp://172.28.0.20:50000 -s 0 -o Server -v ServerStatus   # opc-plc
set -euo pipefail

NETWORK="ot-lab_ot-lab"; ENDPOINT="opc.tcp://172.28.0.21:4840/lab/"; OBJ="Tanque1"; VAR="Nivel"; NS="2"; WRITE=""; LIST="0"
IMAGE="${PY_IMAGE:-python:3.12-slim}"

usage() { sed -n '6,19p' "$0" | sed 's/^# \{0,1\}//'; }

while getopts ":n:e:o:v:s:w:lh" opt; do
  case "$opt" in
    n) NETWORK="$OPTARG" ;;
    e) ENDPOINT="$OPTARG" ;;
    o) OBJ="$OPTARG" ;;
    v) VAR="$OPTARG" ;;
    s) NS="$OPTARG" ;;
    w) WRITE="$OPTARG" ;;
    l) LIST="1" ;;
    h) usage; exit 0 ;;
    :) echo "ERROR: la opción -$OPTARG necesita un valor." >&2; usage >&2; exit 1 ;;
    *) echo "ERROR: opción desconocida -$OPTARG." >&2; usage >&2; exit 1 ;;
  esac
done

command -v docker >/dev/null || { echo "ERROR: docker no está instalado o no está en el PATH." >&2; exit 1; }
docker network inspect "$NETWORK" >/dev/null 2>&1 || {
  echo "ERROR: no existe la red Docker '$NETWORK'." >&2
  echo "       Redes disponibles:" >&2; docker network ls --format '         {{.Name}}' >&2
  echo "       ¿Levantaste el laboratorio (docker compose up -d)? Si la red se llama distinto, usa -n <red>." >&2
  exit 1; }

if [ "$LIST" = "1" ]; then echo ">> $NETWORK · $ENDPOINT · Objects/$NS:$OBJ · listar variables"
else echo ">> $NETWORK · $ENDPOINT · Objects/$NS:$OBJ/$NS:$VAR${WRITE:+ · escribir $WRITE}"; fi

docker run --rm -i --network "$NETWORK" \
  -e ENDPOINT="$ENDPOINT" -e OBJ="$OBJ" -e VAR="$VAR" -e NS="$NS" -e WRITE="$WRITE" -e LIST="$LIST" \
  "$IMAGE" sh -c "pip -q install --root-user-action=ignore --disable-pip-version-check asyncua && python -" <<'PY'
import asyncio, logging, os, sys
from asyncua import Client, ua
logging.getLogger("asyncua").setLevel(logging.ERROR)   # silencia el aviso del session timeout

ep, obj, var, ns = os.environ["ENDPOINT"], os.environ["OBJ"], os.environ["VAR"], os.environ["NS"]
write, listar = os.environ["WRITE"], os.environ["LIST"] == "1"

def nombre(e):
    return str(e).rsplit("(", 1)[-1].rstrip(")") or str(e)

def convertir(texto, actual):
    if isinstance(actual, bool): return texto.strip().lower() in ("1", "true", "on", "si", "sí")
    if isinstance(actual, int): return int(texto)
    if isinstance(actual, float): return float(texto)
    return texto

async def main():
    try:
        async with Client(ep, timeout=5) as c:
            try:
                nodo_obj = await c.nodes.root.get_child(["0:Objects", f"{ns}:{obj}"])
            except ua.UaStatusCodeError as e:
                print(f"ERROR OPC UA: no existe Objects/{ns}:{obj} ({nombre(e)})", file=sys.stderr); sys.exit(3)
            if listar:
                for hijo in await nodo_obj.get_children():
                    bn = (await hijo.read_browse_name()).Name
                    try:
                        v = await hijo.read_value(); print(f"  {obj}.{bn} = {v!r} ({type(v).__name__})")
                    except ua.UaStatusCodeError:
                        print(f"  {obj}.{bn} (sin valor)")
                return
            try:
                nodo = await nodo_obj.get_child([f"{ns}:{var}"])
            except ua.UaStatusCodeError as e:
                print(f"ERROR OPC UA: no existe {ns}:{var} en {obj} ({nombre(e)})", file=sys.stderr); sys.exit(3)
            if write:
                actual = await nodo.read_value()
                try:
                    await nodo.write_value(ua.Variant(convertir(write, actual), await nodo.read_data_type_as_variant_type()))
                except ua.UaStatusCodeError as e:
                    print(f"ERROR OPC UA: {var} no admite escritura ({nombre(e)})", file=sys.stderr); sys.exit(4)
            v = await nodo.read_value()
            print(f"{obj}.{var} = {v!r} ({type(v).__name__})")
    except (OSError, asyncio.TimeoutError, ConnectionError) as e:
        print(f"ERROR: no se pudo conectar a {ep} ({e})", file=sys.stderr); sys.exit(2)

asyncio.run(main())
PY
