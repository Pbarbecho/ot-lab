# Explorador OPC UA · ot-lab (editor del servidor opcua-py + cliente asyncua con mensajes decodificados)
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py generator.py uatap.py ./
COPY static ./static
EXPOSE 8600
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8600"]
