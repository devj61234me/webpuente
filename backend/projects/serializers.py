from urllib.parse import urlsplit

from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .defaults import DEFAULT_SETTINGS, QUERY_MODES, REDIRECT_STATUSES, merged_settings
from .models import (
    AnalysisRun, AuditLog, ExportJob, MappingReview, MigrationProject, NewURL, OldURL, RedirectRisk, URLImportBatch,
)


def http_url(value):
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise serializers.ValidationError("Enter a full address starting with http:// or https://")
    return value


def validate_project_settings(data):
    """Check the settings object. Unknown keys are dropped; every value is range-checked."""
    if not isinstance(data, dict):
        raise serializers.ValidationError("Settings must be an object.")
    merged = merged_settings(data)
    errors = {}
    norm = merged["normalization"]
    if norm.get("query_mode") not in QUERY_MODES:
        errors["normalization"] = f"query_mode must be one of {', '.join(QUERY_MODES)}."
    drop = norm.get("drop_params", [])
    if not isinstance(drop, list) or len(drop) > 50 or not all(isinstance(p, str) and 0 < len(p) <= 60 for p in drop):
        errors["normalization"] = "drop_params must be a list of up to 50 short names."
    norm_clean = {
        "ignore_case": bool(norm.get("ignore_case")), "strip_trailing_slash": bool(norm.get("strip_trailing_slash")),
        "query_mode": norm.get("query_mode"), "drop_params": [p.lower() for p in drop] if isinstance(drop, list) else [],
        "ignore_www": bool(norm.get("ignore_www")),
    }
    weights = {}
    for key, default in DEFAULT_SETTINGS["weights"].items():
        try:
            value = float(merged["weights"].get(key, default))
        except (TypeError, ValueError):
            value = -1
        if not 0 <= value <= 1:
            errors["weights"] = f"Weight '{key}' must be a number from 0 to 1."
        weights[key] = value
    if not errors.get("weights") and sum(weights[k] for k in ("slug", "path", "hierarchy")) <= 0:
        errors["weights"] = "At least one of slug, path or hierarchy weights must be above 0."
    t = merged["thresholds"]
    try:
        thresholds = {k: int(t[k]) for k in ("high", "medium", "min_accept", "ambiguity_gap", "fuzzy_cap")}
    except (KeyError, TypeError, ValueError):
        thresholds = {}
        errors["thresholds"] = "Thresholds must be whole numbers."
    if thresholds:
        if not (100 >= thresholds["high"] > thresholds["medium"] > thresholds["min_accept"] >= 1):
            errors["thresholds"] = "Use: 100 >= high > medium > minimum accepted score >= 1."
        elif not 0 <= thresholds["ambiguity_gap"] <= 50 or not 50 <= thresholds["fuzzy_cap"] <= 100:
            errors["thresholds"] = "Ambiguity gap must be 0-50 and the approximate-match cap 50-100."
    try:
        status = int(merged.get("redirect_status"))
    except (TypeError, ValueError):
        status = 0
    if status not in REDIRECT_STATUSES:
        errors["redirect_status"] = f"Redirect status must be one of {', '.join(map(str, REDIRECT_STATUSES))}."
    patterns = merged.get("excluded_patterns", [])
    if not isinstance(patterns, list) or len(patterns) > 100 or not all(isinstance(p, str) and p.startswith("/") and len(p) <= 200 for p in patterns):
        errors["excluded_patterns"] = "Excluded patterns must start with / (for example /wp-admin/*), up to 100 of them."
    if errors:
        raise serializers.ValidationError(errors)
    return {
        "normalization": norm_clean, "weights": weights, "thresholds": thresholds, "redirect_status": status,
        "excluded_patterns": patterns, "use_embeddings": bool(merged.get("use_embeddings")),
    }


class ProjectWriteSerializer(serializers.ModelSerializer):
    old_site_url = serializers.CharField(max_length=500, validators=[http_url])
    new_site_url = serializers.CharField(max_length=500, validators=[http_url])
    settings = serializers.JSONField(required=False)

    class Meta:
        model = MigrationProject
        fields = ["name", "old_site_url", "new_site_url", "description", "settings"]
        extra_kwargs = {"name": {"max_length": 120}, "description": {"required": False, "allow_blank": True}}

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Enter a project name.")
        qs = MigrationProject.objects.filter(owner=self.context["request"].user, name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("You already have a project with this name.")
        return value

    def validate_settings(self, value):
        return validate_project_settings(value)


class RunSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisRun
        fields = ["id", "status", "progress", "old_count", "new_count", "stats", "error_message", "created_at", "started_at", "finished_at"]


class ProjectSerializer(serializers.ModelSerializer):
    settings = serializers.SerializerMethodField()
    old_count = serializers.IntegerField(read_only=True)
    new_count = serializers.IntegerField(read_only=True)
    pending_count = serializers.IntegerField(read_only=True, default=0)
    approved_count = serializers.IntegerField(read_only=True, default=0)
    latest_run = serializers.SerializerMethodField()

    class Meta:
        model = MigrationProject
        fields = ["id", "name", "old_site_url", "new_site_url", "description", "settings", "old_count", "new_count",
                  "pending_count", "approved_count", "latest_run", "created_at", "updated_at"]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_settings(self, obj):
        return obj.config

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_latest_run(self, obj):
        run = obj.runs.first()
        return RunSerializer(run).data if run else None


class ImportBatchSerializer(serializers.ModelSerializer):
    errors_total = serializers.SerializerMethodField()

    class Meta:
        model = URLImportBatch
        fields = ["id", "kind", "mode", "source", "filename", "file_sha256", "total_rows", "imported_count", "updated_count",
                  "invalid_count", "duplicate_count", "removed_count", "errors_total", "created_at"]

    @extend_schema_field(int)
    def get_errors_total(self, obj):
        return obj.invalid_count + obj.duplicate_count


class PageURLSerializer(serializers.ModelSerializer):
    class Meta:
        fields = ["id", "original_url", "normalized_url", "title", "meta_description", "h1", "canonical_url", "status_code", "source"]


class OldURLSerializer(PageURLSerializer):
    class Meta(PageURLSerializer.Meta):
        model = OldURL


class NewURLSerializer(PageURLSerializer):
    class Meta(PageURLSerializer.Meta):
        model = NewURL


class MappingSerializer(serializers.ModelSerializer):
    old_url = serializers.SerializerMethodField()
    final_url = serializers.CharField(source="final_url_text")
    recommended_url = serializers.SerializerMethodField()
    score = serializers.SerializerMethodField()
    band = serializers.SerializerMethodField()
    match_type = serializers.SerializerMethodField()
    reasons = serializers.SerializerMethodField()
    components = serializers.SerializerMethodField()
    alternatives = serializers.SerializerMethodField()
    evidence = serializers.SerializerMethodField()
    ambiguous = serializers.SerializerMethodField()
    new_suggestion_differs = serializers.SerializerMethodField()
    risk_count = serializers.IntegerField(read_only=True, default=0)
    can_undo = serializers.SerializerMethodField()

    class Meta:
        model = MappingReview
        fields = ["id", "old_url", "recommended_url", "final_url", "final_new_url_id", "score", "band", "match_type", "reasons",
                  "components", "alternatives", "evidence", "ambiguous", "status", "origin", "redirect_status", "note",
                  "decided_at", "new_suggestion_differs", "risk_count", "can_undo"]

    def _rec(self, obj):
        return obj.recommendation

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_old_url(self, obj):
        return {"id": obj.old_url_id, "original": obj.old_url.original_url, "normalized": obj.old_url.normalized_url,
                "title": obj.old_url.title}

    @extend_schema_field(str)
    def get_recommended_url(self, obj):
        return obj.recommendation.new_url_text if obj.recommendation else ""

    @extend_schema_field(int)
    def get_score(self, obj):
        return obj.recommendation.score if obj.recommendation else 0

    @extend_schema_field(str)
    def get_band(self, obj):
        return obj.recommendation.band if obj.recommendation else "unmatched"

    @extend_schema_field(str)
    def get_match_type(self, obj):
        return "manual" if obj.origin == MappingReview.Origin.MANUAL else (obj.recommendation.match_type if obj.recommendation else "none")

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_reasons(self, obj):
        return obj.recommendation.reasons if obj.recommendation else []

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_components(self, obj):
        return obj.recommendation.components if obj.recommendation else {}

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_alternatives(self, obj):
        return obj.recommendation.alternatives if obj.recommendation else []

    @extend_schema_field(str)
    def get_evidence(self, obj):
        return obj.recommendation.evidence if obj.recommendation else "url_only"

    @extend_schema_field(bool)
    def get_ambiguous(self, obj):
        return obj.recommendation.ambiguous if obj.recommendation else False

    @extend_schema_field(bool)
    def get_new_suggestion_differs(self, obj):
        rec = obj.recommendation
        return bool(rec and rec.new_url_id and obj.final_new_url_id and rec.new_url_id != obj.final_new_url_id and obj.status != "rejected")

    @extend_schema_field(bool)
    def get_can_undo(self, obj):
        return bool(obj.prev_state)


class RiskSerializer(serializers.ModelSerializer):
    old_url = serializers.CharField(source="old_url.original_url", default=None, read_only=True)
    new_url = serializers.CharField(source="new_url.original_url", default=None, read_only=True)

    class Meta:
        model = RedirectRisk
        fields = ["id", "kind", "severity", "source", "old_url", "new_url", "review_id", "message", "detail"]


class ExportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExportJob
        fields = ["id", "fmt", "options", "row_count", "skipped_count", "warnings", "filename", "sha256", "created_at"]


class AuditSerializer(serializers.ModelSerializer):
    user = serializers.CharField(source="user.email", default="", read_only=True)

    class Meta:
        model = AuditLog
        fields = ["id", "user", "action", "target_type", "target_id", "detail", "created_at"]
