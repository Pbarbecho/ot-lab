FROM python:3.12-slim
RUN pip install --no-cache-dir asyncua
COPY server.py /app/server.py
CMD ["python", "/app/server.py"]
