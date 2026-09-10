# Builds for both amd64 (your laptop) and arm64 (the Pi) from one file —
# that's the point of keeping everything in Python with no compiled deps.
FROM python:3.11-slim

WORKDIR /app

# Dependencies first, so editing a job doesn't re-install the world. On a
# Pi this layer is the difference between a 10-second rebuild and a
# five-minute one.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY config.yaml .

# SQLite state lives here; compose mounts a volume over it.
RUN mkdir -p /app/data

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "src.main", "--loop"]
