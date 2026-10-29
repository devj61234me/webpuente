"""
Starting background analysis jobs.

JOB_MODE=thread  (default) a background thread in the web process runs the job. Simple and free to host,
                 but a restart of the server interrupts a running job (it is then marked failed and can be re-run).
JOB_MODE=worker  the web process only queues the run; `python manage.py run_worker` executes it.
JOB_MODE=inline  runs inside the request (automated tests).
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.conf import settings
from django.db import connections, transaction
from django.utils import timezone

from core.exceptions import ServiceError

from .analysis import execute_run
from .models import AnalysisRun, MigrationProject

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="webpuente-job")
ACTIVE = (AnalysisRun.Status.QUEUED, AnalysisRun.Status.RUNNING)


def fail_stale_runs(project=None):
    """A run whose process died stops sending heartbeats. Mark it failed so a new run can start."""
    limit = timezone.now() - timedelta(minutes=settings.JOB_STALE_MINUTES)
    qs = AnalysisRun.objects.filter(status__in=ACTIVE)
    if project is not None:
        qs = qs.filter(project=project)
    stale = qs.filter(heartbeat_at__lt=limit) | qs.filter(heartbeat_at__isnull=True, created_at__lt=limit)
    if settings.JOB_MODE == "worker":
        stale = stale.filter(status=AnalysisRun.Status.RUNNING)  # queued runs may legitimately wait for a worker
    return stale.update(status=AnalysisRun.Status.FAILED, error_message="The job was interrupted (server restart or timeout). Please run the analysis again.", finished_at=timezone.now())


def _thread_main(run_id):
    try:
        execute_run(run_id)
    finally:
        connections.close_all()  # threads own their own database connections


def start_analysis(project, user):
    with transaction.atomic():
        MigrationProject.objects.select_for_update().get(pk=project.pk)  # one submit at a time per project
        fail_stale_runs(project)
        if project.runs.filter(status__in=ACTIVE).exists():
            raise ServiceError("An analysis is already running for this project.", code="analysis_in_progress", status_code=409)
        old_count, new_count = project.old_urls.count(), project.new_urls.count()
        if not old_count or not new_count:
            raise ServiceError("Import both the old and the new URL list before running the analysis.", code="lists_missing")
        run = AnalysisRun.objects.create(
            project=project, triggered_by=user, old_count=old_count, new_count=new_count, config_snapshot=project.config
        )
    # The job starts only after the transaction above is committed, so it can see the new row.
    if settings.JOB_MODE == "inline":
        execute_run(run.pk)
    elif settings.JOB_MODE == "thread":
        _executor.submit(_thread_main, run.pk)
    # "worker" mode: nothing to do, the run stays queued until run_worker picks it up
    return run
