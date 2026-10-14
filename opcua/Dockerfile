FROM python:3.12-slim
RUN pip install --no-cache-dir asyncua pymodbus cryptography   # pymodbus: pasarela Modbus → OPC UA · cryptography: políticas cifradas==2.1.0
COPY server.py /app/server.py
CMD ["python", "/app/server.py"]
