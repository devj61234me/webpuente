"""
Database design (all tables belong to one MigrationProject, which belongs to one user):

  MigrationProject --< URLImportBatch      (one row per upload/paste: provenance + error report)
  MigrationProject --< OldURL / NewURL     (the pages being compared; original + normalised URL)
  MigrationProject --< AnalysisRun         (one matching job: status, progress, stats)
  AnalysisRun      --< MappingRecommendation  (what the engine suggested for each old URL in that run)
  OldURL           --1 MappingReview       (the human decision for that old URL; survives re-runs)
  MigrationProject --< RedirectRisk        (quality-check findings)
  MigrationProject --< ExportJob           (generated files, kept so history is reproducible)
  MigrationProject --< AuditLog            (who did what, when)

MySQL note: long URLs cannot be indexed, so uniqueness uses a fixed-length SHA-256 `url_hash`.
"""
import hashlib

from django.conf import settings
from django.db import models

from .defaults import merged_settings


def url_hash(normalized_url):
    return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()


class MigrationProject(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="migration_projects")
    name = models.CharField(max_length=120)
    old_site_url = models.URLField(max_length=500)
    new_site_url = models.URLField(max_length=500)
    description = models.CharField(max_length=500, blank=True)
    settings = models.JSONField(default=dict, blank=True)
    last_decision_at = models.DateTimeField(null=True, blank=True)  # used to tell if quality results are stale
    quality_checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["owner", "name"], name="uniq_project_name_per_owner")]

    def __str__(self):
        return self.name

    @property
    def config(self):
        return merged_settings(self.settings)


class URLImportBatch(models.Model):
    class Kind(models.TextChoices):
        OLD = "old", "Old URLs"
        NEW = "new", "New URLs"

    class Mode(models.TextChoices):
        APPEND = "append", "Add to existing URLs"
        REPLACE = "replace", "Replace existing URLs"

    project = models.ForeignKey(MigrationProject, on_delete=models.CASCADE, related_name="import_batches")
    kind = models.CharField(max_length=3, choices=Kind.choices)
    mode = models.CharField(max_length=8, choices=Mode.choices, default=Mode.APPEND)
    source = models.CharField(max_length=10, default="file")  # file | paste
    filename = models.CharField(max_length=255, blank=True)
    file_sha256 = models.CharField(max_length=64, blank=True)  # proves which file was imported; the file itself is not kept
    column_map = models.JSONField(default=dict, blank=True)
    total_rows = models.PositiveIntegerField(default=0)
    imported_count = models.PositiveIntegerField(default=0)   # new URLs added
    updated_count = models.PositiveIntegerField(default=0)    # existing URLs whose details were updated
    invalid_count = models.PositiveIntegerField(default=0)
    duplicate_count = models.PositiveIntegerField(default=0)
    removed_count = models.PositiveIntegerField(default=0)    # only in replace mode
    errors = models.JSONField(default=list, blank=True)       # first rows that were skipped, with reasons
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class PageURL(models.Model):
    """Shared columns of OldURL and NewURL."""

    original_url = models.TextField()      # exactly what the user supplied (never changed)
    normalized_url = models.TextField()    # used only for comparing
    url_hash = models.CharField(max_length=64)  # sha256 of normalized_url, for fast unique lookups
    host = models.CharField(max_length=255, blank=True)
    path_key = models.TextField(blank=True)      # normalised path + query (host-independent)
    title = models.CharField(max_length=500, blank=True)
    meta_description = models.CharField(max_length=1000, blank=True)
    h1 = models.CharField(max_length=500, blank=True)
    canonical_url = models.TextField(blank=True)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    row_number = models.PositiveIntegerField(null=True, blank=True)  # row in the uploaded file
    source = models.CharField(max_length=10, default="import")       # import | manual | fetch
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class OldURL(PageURL):
    project = models.ForeignKey(MigrationProject, on_delete=models.CASCADE, related_name="old_urls")
    batch = models.ForeignKey(URLImportBatch, null=True, blank=True, on_delete=models.SET_NULL, related_name="old_urls")

    class Meta:
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["project", "url_hash"], name="uniq_old_url_per_project")]
        indexes = [models.Index(fields=["project", "host"], name="idx_old_project_host")]


class NewURL(PageURL):
    project = models.ForeignKey(MigrationProject, on_delete=models.CASCADE, related_name="new_urls")
    batch = models.ForeignKey(URLImportBatch, null=True, blank=True, on_delete=models.SET_NULL, related_name="new_urls")

    class Meta:
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["project", "url_hash"], name="uniq_new_url_per_project")]
        indexes = [models.Index(fields=["project", "host"], name="idx_new_project_host")]


class AnalysisRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    project = models.ForeignKey(MigrationProject, on_delete=models.CASCADE, related_name="runs")
    triggered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED, db_index=True)
    progress = models.PositiveSmallIntegerField(default=0)  # 0-100
    old_count = models.PositiveIntegerField(default=0)
    new_count = models.PositiveIntegerField(default=0)
    config_snapshot = models.JSONField(default=dict, blank=True)  # settings used, so the run can be explained later
    stats = models.JSONField(default=dict, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)  # updated while running; stale runs are failed

    class Meta:
        ordering = ["-created_at", "-id"]


class MappingRecommendation(models.Model):
    """The engine's suggestion for one old URL in one run. Never edited afterwards."""

    class Band(models.TextChoices):
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        LOW = "low", "Low"
        UNMATCHED = "unmatched", "Unmatched"

    project = models.ForeignKey(MigrationProject, on_delete=models.CASCADE, related_name="recommendations")
    run = models.ForeignKey(AnalysisRun, on_delete=models.CASCADE, related_name="recommendations")
    old_url = models.ForeignKey(OldURL, on_delete=models.CASCADE, related_name="recommendations")
    new_url = models.ForeignKey(NewURL, null=True, blank=True, on_delete=models.SET_NULL, related_name="recommendations")
    new_url_text = models.TextField(blank=True)  # copy of the suggested URL, kept even if the NewURL row is removed later
    score = models.PositiveSmallIntegerField(default=0)  # 0-100
    band = models.CharField(max_length=10, choices=Band.choices, db_index=True)
    match_type = models.CharField(max_length=20, default="none")
    reasons = models.JSONField(default=list, blank=True)       # plain-language explanation
    components = models.JSONField(default=dict, blank=True)    # score of each kind of evidence
    alternatives = models.JSONField(default=list, blank=True)  # next best candidates
    evidence = models.CharField(max_length=12, default="url_only")  # url_only | metadata | semantic
    ambiguous = models.BooleanField(default=False)             # two candidates were almost equally good
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["run", "old_url"], name="uniq_recommendation_per_run")]
        indexes = [models.Index(fields=["project", "band"], name="idx_rec_project_band")]


class MappingReview(models.Model):
    """The human decision for one old URL. It survives re-runs when still valid."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    class Origin(models.TextChoices):
        AUTO = "auto", "Suggested by engine"
        MANUAL = "manual", "Assigned manually"

    project = models.ForeignKey(MigrationProject, on_delete=models.CASCADE, related_name="reviews")
    old_url = models.OneToOneField(OldURL, on_delete=models.CASCADE, related_name="review")
    recommendation = models.ForeignKey(MappingRecommendation, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviews")
    final_new_url = models.ForeignKey(NewURL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviews")
    final_url_text = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    origin = models.CharField(max_length=6, choices=Origin.choices, default=Origin.AUTO)
    redirect_status = models.PositiveSmallIntegerField(default=301)
    note = models.CharField(max_length=500, blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    prev_state = models.JSONField(null=True, blank=True)  # one-step undo
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["project", "status"], name="idx_review_project_status")]


class RedirectRisk(models.Model):
    class Severity(models.TextChoices):
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        LOW = "low", "Low"
        INFO = "info", "Info"

    project = models.ForeignKey(MigrationProject, on_delete=models.CASCADE, related_name="risks")
    kind = models.CharField(max_length=30, db_index=True)
    severity = models.CharField(max_length=6, choices=Severity.choices)
    # proposal = found by looking at the proposed mappings; supplied_data = found in crawl data the user imported
    source = models.CharField(max_length=14, default="proposal")
    old_url = models.ForeignKey(OldURL, null=True, blank=True, on_delete=models.CASCADE, related_name="risks")
    new_url = models.ForeignKey(NewURL, null=True, blank=True, on_delete=models.CASCADE, related_name="risks")
    review = models.ForeignKey(MappingReview, null=True, blank=True, on_delete=models.CASCADE, related_name="risks")
    message = models.CharField(max_length=500)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["project", "severity"], name="idx_risk_project_severity")]


class ExportJob(models.Model):
    project = models.ForeignKey(MigrationProject, on_delete=models.CASCADE, related_name="exports")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    fmt = models.CharField(max_length=10)
    options = models.JSONField(default=dict, blank=True)
    row_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    warnings = models.JSONField(default=list, blank=True)
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    content = models.BinaryField(editable=False)  # the file is kept in the database (hosts often have no permanent disk)
    sha256 = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    project = models.ForeignKey(MigrationProject, null=True, blank=True, on_delete=models.CASCADE, related_name="audit_logs")
    action = models.CharField(max_length=40, db_index=True)
    target_type = models.CharField(max_length=30, blank=True)
    target_id = models.PositiveBigIntegerField(null=True, blank=True)
    detail = models.JSONField(default=dict, blank=True)  # never contains passwords or tokens
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["project", "created_at"], name="idx_audit_project_time")]
