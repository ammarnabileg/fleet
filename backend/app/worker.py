from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery = Celery(
    "fleet",
    broker=settings.celery_broker_url,
    include=[
        "app.modules.integrations.tasks",
        "app.modules.identity.tasks",
        "app.modules.tracking.tasks",
        "app.modules.documents.tasks",
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
    "signal-loss": {"task": "tracking.scan_signal_loss", "schedule": 60.0},
    "messaging-channel": {"task": "identity.check_messaging_channel", "schedule": 300.0},
    "position-partitions": {"task": "tracking.maintain_partitions", "schedule": crontab(hour=2, minute=10)},
    "document-expiry": {"task": "documents.scan_expiring", "schedule": crontab(hour=7, minute=0)},
}
