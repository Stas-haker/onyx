"""Dedicated GPU/LLM pools using Onyx's existing broker and tenant task base."""

from celery import Celery
from celery.signals import worker_init

from onyx.background.celery.apps.app_base import TenantAwareTask
from onyx.db.engine.sql_engine import SqlEngine

celery_app = Celery(__name__)
celery_app.config_from_object("onyx.background.celery.configs.client")
celery_app.Task = TenantAwareTask
celery_app.conf.update(
    worker_pool="threads",
    worker_concurrency=1,
    worker_prefetch_multiplier=1,
    task_ignore_result=True,
    task_acks_late=False,
    imports=("onyx.background.celery.tasks.meetings.tasks",),
)


@worker_init.connect
def initialize_meeting_worker(**kwargs: object) -> None:
    SqlEngine.set_app_name("local_meetings")
    SqlEngine.init_engine(pool_size=2, max_overflow=2)
