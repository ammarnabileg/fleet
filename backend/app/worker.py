from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery = Celery(
    "fleet",
    broker=settings.celery_broker_url,
    include=[
        "app.modules.integrations.tasks",
    ],
)

celery.conf.update(
    timezone="Asia/Kuwait",
    task_acks_late=True,  # a task is not lost if the worker dies mid-run
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_ignore_result=True,
    broker_transport_options={"visibility_timeout": 7200},  # longer than the longest task, or it runs twice
    task_soft_time_limit=600,
    task_time_limit=900,
)

# Every important job also exists as a database row; these messages are only triggers.
# Each module adds its periodic tasks here when it is implemented (spec, appendix H).
celery.conf.beat_schedule = {
    "outbox-relay": {"task": "integrations.relay_outbox", "schedule": 5.0},
}
