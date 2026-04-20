FROM python:3.12-slim AS base
WORKDIR /app
RUN pip install --no-cache-dir uv

FROM base AS dev
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt
COPY . .
CMD ["python", "main.py"]

FROM base AS prod
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt
COPY . .
CMD ["python", "main.py"]
