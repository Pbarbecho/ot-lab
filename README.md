# ot-lab — Laboratorio de redes industriales en Docker

Guía completa (LaTeX/PDF): `docs/latex/guia.pdf`. Versión Markdown: `docs/guia-lab-redes-industriales.md`.

## Arranque rápido

| Sistema | Comando |
|---|---|
| macOS (Docker Desktop, Intel o Apple Silicon) | `docker compose up -d` |
| Windows 10/11 (Docker Desktop + WSL 2) | `docker compose -f docker-compose.windows.yml up -d` |
| Linux nativo | `docker compose -f docker-compose.linux.yml.bak up -d` (ver nota) |

```bash
docker compose ps                 # todos "Up" (Ignition tarda 1-3 min)
docker compose logs -f ignition
```

Servicios web: OpenPLC :8080 (openplc/openplc) · Ignition :8088 (admin/lab1234!) · FUXA :1881 · Node-RED :1880 · Conpot :18800 · MQTT :1883 · OPC UA :4840 y :50000 · Modbus :502 y :5020

Nota Linux: la versión `.bak` es la original y tiene dos fallos conocidos (Conpot `command` y bind mount de Ignition, ver guía §4.7); la versión macOS funciona también en Linux y es la recomendada.

## Estructura
- `docker-compose.yml`          — versión macOS (platform amd64 en openplc/conpot, volumen con nombre para Ignition)
- `docker-compose.windows.yml`  — versión Windows (volúmenes con nombre para Ignition, FUXA y Node-RED; notas sobre puertos reservados y CRLF)
- `docker-compose.linux.yml.bak`— versión original Linux
- `modbus/server.json`          — registros del esclavo Modbus simulado (offsets 0-based)
- `opcua/`                      — servidor OPC UA propio en Python (asyncua)
- `mosquitto/mosquitto.conf`    — broker MQTT (sin auth, solo laboratorio)
- `fuxa-data/`, `nodered-data/` — datos persistentes (bind mounts; solo versión macOS)
- `captures/`                   — volcados pcap generados con netshoot
- `docs/latex/`                 — fuente LaTeX de la guía, figuras y PDF
- `.gitattributes`              — fuerza LF en configs (imprescindible si se clona en Windows)
