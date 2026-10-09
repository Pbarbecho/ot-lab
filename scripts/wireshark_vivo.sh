#!/usr/bin/env bash
# Taller 5 · OT-LAB · láminas 25 y 36 — Wireshark en vivo pegado a un contenedor del laboratorio.
# Captura con tcpdump (netshoot) en el namespace de red del contenedor y la tubería la lee Wireshark en su PC.
#
# Uso:  ./scripts/wireshark_vivo.sh [contenedor] [filtro-captura]
#   contenedor      modbus-sim (por defecto) · openplc · modbus-explorer · conpot …
#   filtro-captura  por defecto: "tcp port 5020 or tcp port 502"
# Ej.:  ./scripts/wireshark_vivo.sh                      # todo lo que llega al simulador (incluido el sondeo de OpenPLC)
#       ./scripts/wireshark_vivo.sh openplc              # lo que el PLC envía y recibe (lámina 36)
#       ./scripts/wireshark_vivo.sh modbus-explorer      # solo lo que genera la web del explorador
# Windows: ejecútelo desde la terminal de WSL (Ubuntu); PowerShell no pasa bien la tubería binaria.
set -euo pipefail
C="${1:-modbus-sim}"; F="${2:-tcp port 5020 or tcp port 502}"

command -v docker >/dev/null || { echo "ERROR: docker no está en el PATH." >&2; exit 1; }
docker inspect "$C" >/dev/null 2>&1 || { echo "ERROR: no existe el contenedor '$C'. ¿docker compose up -d?" >&2; exit 1; }

WS=""
for cand in wireshark /usr/local/bin/wireshark /Applications/Wireshark.app/Contents/MacOS/Wireshark \
            "/mnt/c/Program Files/Wireshark/Wireshark.exe" "/c/Program Files/Wireshark/Wireshark.exe"; do
  if command -v "$cand" >/dev/null 2>&1 || [ -x "$cand" ]; then WS="$cand"; break; fi
done
[ -n "$WS" ] || { echo "ERROR: no encuentro Wireshark (lámina 24: instálelo y añádalo al PATH)." >&2; exit 1; }

echo ">> tcpdump en $C · filtro \"$F\" · Wireshark: $WS  (cierre Wireshark para terminar)"
docker run --rm --net "container:$C" nicolaka/netshoot tcpdump -i eth0 -U -w - "$F" \
  | "$WS" -k -i - -o mbtcp.tcp.port:5020
