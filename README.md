# ot-lab — Laboratorio de redes industriales en Docker

Guía completa (LaTeX/PDF): `docs/latex/guia.pdf`. Versión Markdown: `docs/guia-lab-redes-industriales.md`.

## Arranque rápido

| Sistema | Comando |
|---|---|
| macOS (Docker Desktop, Intel o Apple Silicon) | `docker compose up -d` |
| Windows 10/11 (Docker Desktop + WSL 2) | `docker compose -f docker-compose.windows.yml up -d` |
| Linux nativo | `docker compose -f docker-compose.linux.yml.bak up -d` (ver nota) |

```bash
docker compose ps                 # todos "Up" (Ignition tarda 1-3 min; modbus-explorer se construye la primera vez)
docker compose logs -f ignition
```

Servicios web: **Explorador Modbus :8500** · OpenPLC :8080 (openplc/openplc) · Ignition :8088 (admin/lab1234!) · FUXA :1881 · Node-RED :1880 · Conpot :18800 · MQTT :1883 · OPC UA :4840 y :50000 · Modbus :502 y :5020

Nota Linux: la versión `.bak` es la original y tiene dos fallos conocidos (Conpot `command` y bind mount de Ignition, ver guía §4.7); la versión macOS funciona también en Linux y es la recomendada.

## Explorador Modbus (Taller 5 · prácticas 1a y 1b) · `http://localhost:8500`

Contenedor `modbus-explorer` (172.28.0.40): una web que ejecuta **pymodbus** dentro de la red del laboratorio y muestra lo que viaja por el cable. Arranca con el resto del lab (`docker compose up -d`) y no necesita instalar nada en la laptop.

![Explorador Modbus](docs/figuras/modbus_explorer.jpg)

| Pestaña | Qué hace |
|---|---|
| **Escenario** (arriba a la izquierda) | Réplica de la lámina 18: laptop, red Docker ot-lab, `modbus-explorer`, `modbus-sim` y `openplc`. Los enlaces se iluminan con lo que ocurre (sesión pymodbus, sondeo del PLC cada 100 ms, captura) y cada petición recorre el enlace como un punto. Se puede ocultar. |
| **Tablero** (izquierda) | Réplica dinámica de la lámina 31 del Taller 5 (también los tableros de las láminas 30 y 21). Cada lectura o escritura anima un paquete con su FC por la flecha correspondiente, resalta la tabla del esclavo y actualiza las tarjetas (`antes → después` en rojo). |
| **pymodbus** | Sesión `ModbusTcpClient` contra modbus-sim, OpenPLC, Conpot o un host propio. Lecturas FC 01/02/03/04, escrituras FC 05/06/15/16, los pasos del reto de cada lámina con un botón, y sondeo continuo (100 ms – 2 s) como el runtime de OpenPLC. Cada operación muestra la línea pymodbus equivalente, la **Query y la Response reales (MBAP + PDU, byte a byte)**, y la «tabla a entregar» (FC, dónde viajan los datos, PDU, valor) exportable a CSV. Si pymodbus se queja (p. ej. `70000`) se indica que no viajó ninguna trama; si el esclavo responde excepción se decodifica el código. |
| **OpenPLC** | Automatiza el panel de OpenPLC por dentro de la red: **Preparar todo** = Modbus Server en 502 + Slave Device `modbus-sim` (Start 0, DI 2, coils 2, IR 2, HR-R 2, HR-W 0) + subida y compilación del programa + Start PLC. Plantillas editables `monito.st` (ST) y `secuencia_sfc.st` (**SFC**/Grafcet textual: `STEP`, `TRANSITION`, acciones con cualificador `N`). Start/Stop PLC, alta/baja de Slave Devices, **Monitoring embebido** (misma tabla que OpenPLC, leída vía `monitor-update` y pintada en la web) y botón al Monitoring original. Botones para leer el esclavo interno del PLC con pymodbus (`%IX100.0` = DI 800, `%IW100` = IR 100…). |
| **Wireshark** | **Iniciar captura** arranca `tcpdump` dentro del contenedor (puertos 5020 y 502); **Detener** y **Abrir en Wireshark** descargan el `.pcap`, que queda también en `captures/`. Para Wireshark en vivo pegado a un contenedor (láminas 25 y 36) hay un comando para copiar y el script `scripts/wireshark_vivo.sh`. |
| **Modbus server** | Editor gráfico del esclavo simulado: añada entradas digitales, coils, input y holding registers con nombre, icono, formato/escala (×10 °C, %, ppm, hPa, bit…) y valor inicial; cargue los tableros de las láminas 31, 30 y 21 o el `server.json` actual. Los cambios se ven al instante en el tablero animado. **Guardar** escribe `modbus/server.json` (y `modbus/tablero.json` con nombres e iconos); **Guardar y reiniciar modbus-sim** aplica en el simulador a través del socket de Docker montado. Muestra además el `registers` generado y la equivalencia clave JSON → dirección pymodbus → SCADA. |

El socket de Docker (`/var/run/docker.sock`) se monta solo para el botón «Guardar y reiniciar modbus-sim»; si no lo quiere, quite esa línea del compose y reinicie a mano con `docker compose restart modbus-sim`.

Cada bloque de la web lleva una barra con un asa (⠿) para arrastrarlo a la columna izquierda o a otra pestaña (la disposición se guarda en el navegador; «⟲ disposición» la restablece) y un botón «↗ pestaña» que lo abre solo en una pestaña nueva, sincronizada con la principal: el tablero puede ir al proyector mientras los controles quedan en el portátil.

Limitaciones honestas: un contenedor no puede abrir ventanas en la laptop, así que «Abrir en Wireshark» descarga el archivo (doble clic lo abre) y la captura en vivo se lanza desde la terminal con el script. El iframe del Monitoring original funciona en Chrome/Edge/Firefox tras iniciar sesión dentro del marco; Safari bloquea esa cookie, use el botón externo.

```bash
./scripts/wireshark_vivo.sh                 # Wireshark en vivo pegado a modbus-sim (ve también el sondeo de OpenPLC)
./scripts/wireshark_vivo.sh openplc         # lo que el PLC envía y recibe (lámina 36)
./scripts/wireshark_vivo.sh modbus-explorer # solo lo que genera la web
docker compose up -d --build modbus-explorer   # tras editar modbus-explorer/
```

Dos trampas de OpenPLC que la web ya esquiva: (1) un Slave Device TCP creado con los campos RTU vacíos hace caer el runtime con *Floating point exception* (la web envía 115200/None/8/1 como el panel); (2) Monitoring toma como variable **cualquier línea con la secuencia espacio-AT-espacio**, comentarios incluidos: evítela en los comentarios del `.st`.

## Estructura
- `docker-compose.yml`          — versión macOS (platform amd64 en openplc/conpot, volumen con nombre para Ignition)
- `docker-compose.windows.yml`  — versión Windows (volúmenes con nombre para Ignition, FUXA y Node-RED; notas sobre puertos reservados y CRLF)
- `docker-compose.linux.yml.bak`— versión original Linux
- `modbus-explorer/`            — Explorador Modbus (FastAPI + pymodbus + tcpdump): `app.py`, `static/` (web), `programs/` (plantillas .st para OpenPLC)
- `modbus/server.json`          — registros del esclavo Modbus simulado (clave JSON = dirección + 1); lo escribe el editor «Modbus server» del explorador
- `modbus/tablero.json`         — nombres, iconos y formatos del tablero del editor (acompaña a server.json)
- `opcua/`                      — servidor OPC UA propio en Python (asyncua)
- `mosquitto/mosquitto.conf`    — broker MQTT (sin auth, solo laboratorio)
- `scripts/`                    — `comprobacion2_modbus.sh`, `comprobacion3_opcua.sh`, `wireshark_vivo.sh`, `vacio.st`
- `fuxa-data/`, `nodered-data/` — datos persistentes (bind mounts; solo versión macOS)
- `captures/`                   — volcados pcap (netshoot y el explorador)
- `docs/latex/`                 — fuente LaTeX de la guía, figuras y PDF
- `.gitattributes`              — fuerza LF en configs (imprescindible si se clona en Windows)
