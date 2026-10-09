# Explorador Modbus TCP · Taller 5 (prácticas 1a y 1b) · ot-lab
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends tcpdump \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY static ./static
COPY programs ./programs
EXPOSE 8500
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8500"]
