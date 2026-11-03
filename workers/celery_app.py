from celery import Celery
from backend.app.config import config

app = Celery("emailos", broker=config().redis_url, backend=config().redis_url, include=["workers.tasks"])
app.conf.update(
    timezone="UTC", enable_utc=True, task_acks_late=True,
    task_reject_on_worker_lost=True, worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_serializer="json", accept_content=["json"], result_serializer="json",
    beat_schedule={
        "dispatch": {"task": "workers.tasks.dispatch", "schedule": 30.0},
        "notifications": {"task": "workers.tasks.push", "schedule": 30.0},
        "mailbox": {"task": "workers.tasks.mailbox", "schedule": 60.0},
        "recover": {"task": "workers.tasks.recover", "schedule": 120.0}})
