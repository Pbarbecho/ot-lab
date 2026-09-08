# ot-lab — Laboratorio de redes industriales en Docker

Guía completa: `docs/guia-lab-redes-industriales.pdf` (también en Markdown).

## Arranque rápido
```bash
docker compose up -d
docker compose ps
```
Servicios web: OpenPLC :8080 · Ignition :8088 · FUXA :1881 · Node-RED :1880 · Conpot :10080 · MQTT :1883

## Estructura
- `docker-compose.yml`       — todos los servicios (red ot-lab 172.28.0.0/24)
- `modbus/server.json`       — registros del esclavo Modbus simulado
- `opcua/`                   — servidor OPC UA propio en Python (asyncua)
- `mosquitto/mosquitto.conf` — broker MQTT (sin auth, solo laboratorio)
- `ignition-data/`, `fuxa-data/`, `nodered-data/` — datos persistentes
- `captures/`                — volcados pcap generados con netshoot
- `docs/`                    — guía PDF/MD y figuras
