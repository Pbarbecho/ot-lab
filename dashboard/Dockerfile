# Dashboard OT-Lab: Python (solo stdlib) + CLI de Docker.
# Habla con el Docker del host por /var/run/docker.sock (montado en el compose):
# docker exec en ot-client/modbus-sim/openplc, docker logs, docker restart y tcpdump con netshoot.
FROM docker:27-cli

RUN apk add --no-cache python3 tzdata

WORKDIR /app
COPY app.py openplc_ctl.py scenarios.py index.html ./
COPY marca/ ./marca/
COPY openplc/ ./openplc/

ENV OT_LAB=/ot-lab \
    WEB_HOST=0.0.0.0 \
    WEB_PORT=8000 \
    WIRESHARK_MODE=none \
    PYTHONUNBUFFERED=1 \
    TZ=America/Guayaquil

EXPOSE 8000
ENTRYPOINT []
CMD ["python3", "app.py"]
