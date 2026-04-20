FROM python:3.12-slim AS base
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM base AS dev
COPY . .
CMD ["python", "main.py", "--schedule"]

FROM base AS prod
COPY . .
CMD ["python", "main.py", "--schedule"]
