#!/bin/sh
# Worker entrypoint — role selected via WORKER_ROLE env var
# Values: interactive | batch | beat | flower

set -e

ROLE="${WORKER_ROLE:-batch}"
APP="app.workers.celery_app"

echo "PrepLink Worker starting as role=${ROLE}"

case "$ROLE" in

  interactive)
    exec celery -A "$APP" worker \
      --queues=interactive \
      --concurrency="${CELERY_INTERACTIVE_CONCURRENCY:-4}" \
      --prefetch-multiplier=1 \
      --without-heartbeat \
      --without-gossip \
      --loglevel=info \
      --hostname="interactive@%h"
    ;;

  batch)
    exec celery -A "$APP" worker \
      --queues=batch \
      --concurrency="${CELERY_BATCH_CONCURRENCY:-8}" \
      --prefetch-multiplier=1 \
      --without-heartbeat \
      --without-gossip \
      --loglevel=info \
      --hostname="batch@%h"
    ;;

  beat)
    exec celery -A "$APP" beat \
      --scheduler=redbeat.RedBeatScheduler \
      --loglevel=info
    ;;

  flower)
    exec celery -A "$APP" flower \
      --port="${FLOWER_PORT:-5555}" \
      --basic_auth="${FLOWER_USER:-admin}:${FLOWER_PASSWORD:-preplink}" \
      --url_prefix="${FLOWER_URL_PREFIX:-}" \
      --loglevel=info
    ;;

  *)
    echo "Unknown WORKER_ROLE=${ROLE}. Must be: interactive|batch|beat|flower"
    exit 1
    ;;

esac
