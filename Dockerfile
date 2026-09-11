FROM python:3.11-slim

WORKDIR /app

# System deps for Pillow + Redis client
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg-dev \
    zlib1g-dev \
    libwebp-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default entrypoint is overridden by docker-compose service command
# so this is only the fallback
CMD ["celery", "-A", "app.workers.celery_app", "worker", \
     "-Q", "batch", \
     "-c", "8", \
     "--prefetch-multiplier", "1", \
     "--without-heartbeat", \
     "--without-gossip", \
     "--loglevel", "info", \
     "-n", "worker@%h"]
