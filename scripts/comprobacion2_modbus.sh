#!/usr/bin/env bash
# Taller 4 · OT-LAB · §4.5.1 — Comprobación 2: Modbus TCP responde
# Lee holding registers del simulador desde un contenedor temporal en la red Docker del laboratorio.
# Resultado esperado con los valores por defecto:  REGISTROS OBTENIDOS: [25, 72, 0]
#
# Uso:  ./scripts/comprobacion2_modbus.sh [-n RED] [-i IP] [-p PUERTO] [-d DIRECCION] [-c CANTIDAD] [-u UNIT_ID]
#   -n  red Docker en la que vive el simulador   (por defecto: ot-lab_ot-lab, la que crea compose)
#   -i  IP del esclavo Modbus                     (por defecto: 172.28.0.30)
#   -p  puerto TCP                                (por defecto: 5020)
#   -d  dirección del primer registro, 0-based    (por defecto: 0)
#   -c  cantidad de registros a leer              (por defecto: 3)
#   -u  unit/device id                            (por defecto: 1)
#   -h  esta ayuda
# Ej.:  ./scripts/comprobacion2_modbus.sh                      # todo por defecto
#       ./scripts/comprobacion2_modbus.sh -n ot-lab            # si el compose fija name: ot-lab (docker network ls)
#       ./scripts/comprobacion2_modbus.sh -d 0 -c 4            # 4 registros desde el 0
set -euo pipefail

NETWORK="ot-lab_ot-lab"; HOST="172.28.0.30"; PORT="5020"; ADDR="0"; COUNT="3"; DEVICE_ID="1"
IMAGE="${PY_IMAGE:-python:3.12-slim}"

usage() { sed -n '6,16p' "$0" | sed 's/^# \{0,1\}//'; }

while getopts ":n:i:p:d:c:u:h" opt; do
  case "$opt" in
    n) NETWORK="$OPTARG" ;;
    i) HOST="$OPTARG" ;;
    p) PORT="$OPTARG" ;;
    d) ADDR="$OPTARG" ;;
    c) COUNT="$OPTARG" ;;
    u) DEVICE_ID="$OPTARG" ;;
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

echo ">> $NETWORK · $HOST:$PORT · dir=$ADDR count=$COUNT · id=$DEVICE_ID"

docker run --rm -i --network "$NETWORK" \
  -e HOST="$HOST" -e PORT="$PORT" -e ADDR="$ADDR" -e COUNT="$COUNT" -e DEVICE_ID="$DEVICE_ID" \
  "$IMAGE" sh -c "pip -q install --root-user-action=ignore --disable-pip-version-check pymodbus && python -" <<'PY'
import os, sys
from pymodbus.client import ModbusTcpClient

host, port = os.environ["HOST"], int(os.environ["PORT"])
addr, count, dev = int(os.environ["ADDR"]), int(os.environ["COUNT"]), int(os.environ["DEVICE_ID"])

c = ModbusTcpClient(host, port=port)
if not c.connect():
    print(f"ERROR: no se pudo conectar a {host}:{port}", file=sys.stderr); sys.exit(2)
try:
    res = c.read_holding_registers(address=addr, count=count, device_id=dev)
    if res.isError():
        print(f"ERROR Modbus: {res}", file=sys.stderr); sys.exit(3)
    print("REGISTROS OBTENIDOS:", res.registers)
finally:
    c.close()
PY
