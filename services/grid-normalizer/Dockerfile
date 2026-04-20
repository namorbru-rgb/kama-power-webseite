FROM python:3.12-slim AS base
WORKDIR /app
RUN pip install --no-cache-dir --upgrade pip

FROM base AS dev
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]

FROM base AS prod
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
USER nobody
CMD ["python", "main.py"]
