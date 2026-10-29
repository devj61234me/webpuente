"""Run queued analysis jobs. Start with:  python manage.py run_worker   (use JOB_MODE=worker on the web service)."""
import time

from django.core.management.base import BaseCommand

from projects.analysis import execute_run
from projects.jobs import fail_stale_runs
from projects.models import AnalysisRun


class Command(BaseCommand):
    help = "Process queued analysis runs, one after another."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process what is queued, then exit.")
        parser.add_argument("--interval", type=int, default=3, help="Seconds to wait between checks.")

    def handle(self, *args, **options):
        self.stdout.write("Worker started. Press Ctrl+C to stop.")
        while True:
            fail_stale_runs()
            run = AnalysisRun.objects.filter(status=AnalysisRun.Status.QUEUED).order_by("created_at", "id").first()
            if run:
                self.stdout.write(f"Running analysis {run.pk} for project {run.project_id}")
                execute_run(run.pk)  # claims the run itself, so two workers never run the same job
                continue
            if options["once"]:
                return
            time.sleep(options["interval"])
