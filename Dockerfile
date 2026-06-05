FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml .
COPY src ./src
COPY config/config.example.json ./config/config.example.json

ENV PYTHONPATH=/app/src

EXPOSE 8000

CMD ["uvicorn", "poliedro_mcp.api:app", "--host", "0.0.0.0", "--port", "8000"]
