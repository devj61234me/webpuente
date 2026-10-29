import hashlib
import re
from datetime import datetime, timezone

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import ServiceError
from core.pagination import StandardPagination
from core.throttles import ExportThrottle
from services import exporters, risks as risk_rules

from . import audit, quality
from .common import get_project
from .defaults import REDIRECT_STATUSES
from .models import ExportJob, RedirectRisk
from .serializers import ExportSerializer, RiskSerializer

# Rows with these problems never go into an executable server configuration.
BLOCKING_KINDS = {"self_redirect", "redirect_loop", "excluded_pattern", "invalid_destination", "duplicate_source"}
CONFIG_FORMATS = ("htaccess", "nginx")


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "project"


class ExportListCreateView(APIView):
    throttle_classes = [ExportThrottle]

    @extend_schema(responses=ExportSerializer(many=True))
    def get(self, request, pk):
        project = get_project(request, pk)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(project.exports.defer("content"), request)
        return paginator.get_paginated_response(ExportSerializer(page, many=True).data)

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: ExportSerializer})
    def post(self, request, pk):
        project = get_project(request, pk)
        fmt = request.data.get("format")
        if fmt not in exporters.FORMATS:
            raise ServiceError(f"Format must be one of: {', '.join(exporters.FORMATS)}.", code="invalid_format")
        include_pending = bool(request.data.get("include_pending"))
        if include_pending and not request.data.get("confirm_pending"):
            raise ServiceError("Pending mappings have not been approved. Confirm that you want them included.", code="pending_confirmation_required")
        override = request.data.get("redirect_status")
        if override not in (None, ""):
            try:
                override = int(override)
            except (TypeError, ValueError):
                override = 0
            if override not in REDIRECT_STATUSES:
                raise ServiceError("Redirect status must be 301, 302, 307 or 308.", code="invalid_status")
        else:
            override = None

        all_rows = quality.mapping_rows(project)
        statuses = {"approved"} | ({"pending"} if include_pending else set())
        if fmt == "report":
            statuses = {"approved", "pending", "rejected"}
        selected = [r for r in all_rows if r["status"] in statuses and (r["final_new_id"] or fmt == "report")]
        if len(selected) > settings.MAX_EXPORT_ROWS:
            raise ServiceError(f"Too many rows to export at once (limit {settings.MAX_EXPORT_ROWS}).", code="too_many_rows", status_code=413)
        if override:
            for row in selected:
                row["redirect_status"] = override
        warnings, skipped = [], 0

        findings = risk_rules.evaluate([r for r in selected if r["final_new_id"] and r["status"] != "rejected"], [], project.config)
        problem_ids = {}
        for f in findings:
            if f["kind"] in BLOCKING_KINDS and f["review_id"]:
                problem_ids.setdefault(f["review_id"], f["kind"])

        if fmt in CONFIG_FORMATS:
            kept = []
            for row in selected:
                if row["review_id"] in problem_ids:
                    skipped += 1
                    warnings.append(f"Skipped {row['old_original']}: {problem_ids[row['review_id']].replace('_', ' ')}.")
                else:
                    kept.append(row)
            selected = kept
            warnings.append("Generated rules assume a standard server setup. Review them and test on a staging copy before going live.")
        elif problem_ids:
            warnings.append(f"{len(problem_ids)} row(s) have high-severity problems (loops, self-redirects or similar). Check the Quality page before using them.")
        if include_pending:
            warnings.append("This file includes mappings that have NOT been approved.")
        if not selected:
            raise ServiceError("There is nothing to export yet. Approve some mappings first.", code="nothing_to_export")

        for row in selected:  # spreadsheet-friendly copies of the URL columns
            row.update(old_url=row["old_original"], old_normalized=row["old_full"], new_url=row["final_original"],
                       new_normalized=row["final_full"], confidence=row["score"], review_status=row["status"])
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
        meta = {"project": project.name, "old_site": project.old_site_url, "new_site": project.new_site_url,
                "statuses_included": sorted(statuses), "row_count": len(selected)}
        if fmt == "csv":
            content = exporters.build_csv(selected)
        elif fmt == "xlsx":
            content = exporters.build_xlsx(selected, summary={**meta, "statuses_included": ", ".join(sorted(statuses))})
        elif fmt == "report":
            risk_rows = [
                {"severity": r.severity, "kind": r.kind, "source": r.source, "old_url": r.old_url.original_url if r.old_url else "",
                 "new_url": r.new_url.original_url if r.new_url else "", "message": r.message}
                for r in RedirectRisk.objects.filter(project=project).select_related("old_url", "new_url")[: settings.MAX_EXPORT_ROWS]
            ]
            content = exporters.build_xlsx(selected, summary={**meta, "statuses_included": "all", "note": "Report: includes pending and rejected rows."}, risks=risk_rows)
        elif fmt == "json":
            slim = [{k: r[k] for k in ("old_url", "old_normalized", "new_url", "new_normalized", "redirect_status", "confidence", "band",
                                       "match_type", "reasons", "review_status", "origin", "note")} for r in selected]
            content = exporters.build_json(slim, {**meta, "warnings": warnings})
        elif fmt == "htaccess":
            content = exporters.build_htaccess(selected, project.name)
        else:
            content = exporters.build_nginx(selected, project.name, project.config["normalization"]["strip_trailing_slash"])
        if fmt in CONFIG_FORMATS:
            problems = exporters.validate_syntax(fmt, content)
            if problems:
                raise ServiceError("The generated file failed its syntax check, so it was not created: " + "; ".join(problems[:3]), code="export_syntax_error", status_code=500)
            warnings.append("A basic format check passed. It does not replace testing with your own server.")

        job = ExportJob.objects.create(
            project=project, requested_by=request.user, fmt=fmt,
            options={"include_pending": include_pending, "redirect_status": override}, row_count=len(selected), skipped_count=skipped,
            warnings=warnings[:50], filename=f"webpuente-{_slug(project.name)}-{stamp}.{exporters.EXTENSIONS[fmt]}",
            content_type=exporters.CONTENT_TYPES[fmt], content=content, sha256=hashlib.sha256(content).hexdigest(),
        )
        audit.log(request.user, "export.created", project, job, format=fmt, rows=len(selected), skipped=skipped, include_pending=include_pending)
        return Response(ExportSerializer(job).data, status=status.HTTP_201_CREATED)


class ExportDownloadView(APIView):
    @extend_schema(responses={200: OpenApiTypes.BINARY})
    def get(self, request, pk, export_id):
        project = get_project(request, pk)
        job = project.exports.filter(pk=export_id).first()
        if job is None:
            raise ServiceError("Export not found.", code="not_found", status_code=404)
        response = HttpResponse(bytes(job.content), content_type=job.content_type)
        response["Content-Disposition"] = f'attachment; filename="{job.filename}"'
        response["X-Content-Type-Options"] = "nosniff"
        return response


class QualityView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, pk):
        project = get_project(request, pk)
        qs = RedirectRisk.objects.filter(project=project).select_related("old_url", "new_url")
        if severity := request.query_params.get("severity"):
            qs = qs.filter(severity__in=severity.split(","))
        if kind := request.query_params.get("kind"):
            qs = qs.filter(kind__in=kind.split(","))
        counts = {}
        for r in RedirectRisk.objects.filter(project=project).values("severity", "kind"):
            counts[r["severity"]] = counts.get(r["severity"], 0) + 1
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs.order_by("id"), request)
        data = paginator.get_paginated_response(RiskSerializer(page, many=True).data).data
        stale = bool(project.last_decision_at and (not project.quality_checked_at or project.last_decision_at > project.quality_checked_at))
        data.update({"checked_at": project.quality_checked_at, "stale": stale, "by_severity": counts, "not_checked": risk_rules.NOT_CHECKED})
        return Response(data)


class QualityRunView(APIView):
    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request, pk):
        project = get_project(request, pk)
        summary = quality.refresh_quality(project)
        audit.log(request.user, "quality.checked", project, None, total=summary["total"], **{f"sev_{k}": v for k, v in summary["by_severity"].items()})
        return Response(summary)
