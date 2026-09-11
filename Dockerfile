# Placeholder image for future phases (no runnable service exists yet).
# Kept minimal on purpose - see docker-compose.yml.
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir -e .

CMD ["python", "-c", "print('AI Quant Trading Platform skeleton - no runnable service yet')"]
