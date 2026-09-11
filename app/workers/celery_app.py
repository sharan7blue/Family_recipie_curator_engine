"""
PrepLink Celery Application
=============================
Factory that creates and configures the Celery app.
Import `celery_app` wherever you need to define or call tasks.

Two queues, two worker pools:
  interactive   priority=9   concurrency=4   Prefetch=1
  batch         priority=1   concurrency=8   Prefetch=1  (long-running)

Worker launch commands (see docker-compose.yml):
  # Interactive worker — low latency, small pool
  celery -A app.workers.celery_app worker -Q interactive -c 4 -n interactive@%h

  # Batch worker — throughput, larger pool
  celery -A app.workers.celery_app worker -Q batch -c 8 --prefetch-multiplier 1 -n batch@%h

  # Beat scheduler — fires periodic maintenance tasks
  celery -A app.workers.celery_app beat --scheduler celery.beat.PersistentScheduler

  # Flower monitoring UI (port 5555)
  celery -A app.workers.celery_app flower --port=5555
"""

from __future__ import annotations

from celery import Celery
from celery.utils.log import get_task_logger
from kombu import Exchange, Queue

from app.core.config import settings

logger = get_task_logger(__name__)

# ─── App factory ─────────────────────────────────────────────────────────────

def create_celery_app() -> Celery:
    app = Celery(
        "preplink",
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
        include=[
            "app.workers.tasks.pipeline",
            "app.workers.tasks.extraction",
            "app.workers.tasks.batch_api",
            "app.workers.tasks.cart",
            "app.workers.beat.schedule",
        ],
    )
    app.config_from_object(_CeleryConfig)
    return app


class _CeleryConfig:
    # ── Serialisation ──────────────────────────────────────────────────────
    task_serializer         = "json"
    result_serializer       = "json"
    accept_content          = ["json"]
    timezone                = "UTC"
    enable_utc              = True

    # ── Queues ─────────────────────────────────────────────────────────────
    # Two separate exchanges so workers can be dedicated per queue type
    task_queues = (
        Queue(
            "interactive",
            Exchange("interactive", type="direct"),
            routing_key="interactive",
            queue_arguments={"x-max-priority": 10},
        ),
        Queue(
            "batch",
            Exchange("batch", type="direct"),
            routing_key="batch",
            queue_arguments={"x-max-priority": 5},
        ),
    )
    task_default_queue         = "interactive"
    task_default_exchange      = "interactive"
    task_default_routing_key   = "interactive"

    # ── Routing — tasks auto-route by module ───────────────────────────────
    task_routes = {
        "app.workers.tasks.pipeline.*":   {"queue": "batch"},
        "app.workers.tasks.extraction.*": {"queue": "batch"},
        "app.workers.tasks.batch_api.*":  {"queue": "batch"},
        "app.workers.tasks.cart.*":       {"queue": "batch"},
        "app.workers.beat.*":             {"queue": "batch"},
    }

    # ── Result backend ─────────────────────────────────────────────────────
    result_expires              = 86400 * 7    # 7 days
    result_compression          = "gzip"
    result_extended             = True         # stores args, kwargs, name in result

    # ── Reliability ────────────────────────────────────────────────────────
    task_acks_late              = True         # ack after task finishes, not before
    task_reject_on_worker_lost  = True         # re-queue if worker dies mid-task
    worker_prefetch_multiplier  = 1            # one task at a time per worker slot
    task_soft_time_limit        = settings.CELERY_TASK_SOFT_TIME_LIMIT   # raises SoftTimeLimitExceeded
    task_time_limit             = settings.CELERY_TASK_TIME_LIMIT        # SIGKILL

    # ── Retries ────────────────────────────────────────────────────────────
    task_max_retries            = 5
    task_default_retry_delay    = 30           # seconds

    # ── Broker transport ───────────────────────────────────────────────────
    broker_transport_options = {
        "visibility_timeout": 43200,           # 12h — longer than any single task
        "priority_steps":     list(range(10)), # Enable priority queues on Redis
    }

    # ── Worker ─────────────────────────────────────────────────────────────
    worker_redirect_stdouts     = False        # let Docker capture stdout/stderr
    worker_log_color            = False        # cleaner in Datadog/CloudWatch


# ─── Singleton ───────────────────────────────────────────────────────────────

celery_app = create_celery_app()
