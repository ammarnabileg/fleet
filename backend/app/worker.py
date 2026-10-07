from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery = Celery(
    "fleet",
    broker=settings.celery_broker_url,
    include=[
        "app.modules.integrations.tasks",
        "app.modules.files.tasks",
        "app.modules.identity.tasks",
        "app.modules.tracking.tasks",
        "app.modules.documents.tasks",
        "app.modules.daily_ops.tasks",
        "app.modules.cash.tasks",
        "app.modules.accidents.tasks",
        "app.modules.finance.tasks",
        "app.modules.approvals.tasks",
        "app.modules.notifications.tasks",
        "app.modules.violations.tasks",
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
    "link-queue": {"task": "identity.send_queued_link", "schedule": 20.0},  # the pace itself is in the settings
    "position-partitions": {"task": "tracking.maintain_partitions", "schedule": crontab(hour=2, minute=10)},
    "document-expiry": {"task": "documents.scan_expiring", "schedule": crontab(hour=7, minute=0)},
    "daily-report-overdue": {"task": "daily_ops.scan_overdue", "schedule": crontab(minute=5)},
    "daily-report-missing": {"task": "daily_ops.scan_missing", "schedule": crontab(hour=23, minute=30)},  # Kuwait
    "ledger-invariants": {"task": "cash.check_invariants", "schedule": crontab(hour=2, minute=0)},
    "police-reports": {"task": "accidents.scan_police_reports", "schedule": crontab(hour=9, minute=15)},
    "finance-entries": {"task": "finance.post_entries", "schedule": crontab(hour=3, minute=30)},
    "approval-escalation": {"task": "approvals.escalate", "schedule": crontab(minute="*/15")},
    "violations-final": {"task": "violations.finalize_due", "schedule": crontab(minute=20)},
    "driver-push": {"task": "notifications.push", "schedule": 30.0},  # does nothing until push is switched on
    "files-to-r2": {"task": "files.copy_to_r2", "schedule": 600.0},  # does nothing until R2 is switched on
}
