from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from django.conf import settings

from core.exceptions import ServiceError
from core.pagination import StandardPagination
from core.throttles import AnalysisThrottle

from . import audit, jobs
from .common import get_project
from .maintenance import renormalize
from .models import (
    AnalysisRun, AuditLog, MappingRecommendation, MappingReview, MigrationProject, NewURL, OldURL, RedirectRisk,
)
from .serializers import (
    AuditSerializer, NewURLSerializer, OldURLSerializer, ProjectSerializer, ProjectWriteSerializer, RunSerializer,
)


def annotated_projects(qs):
    return qs.annotate(
        old_count=Count("old_urls", distinct=True),
        new_count=Count("new_urls", distinct=True),
        pending_count=Count("reviews", filter=Q(reviews__status="pending"), distinct=True),
        approved_count=Count("reviews", filter=Q(reviews__status="approved"), distinct=True),
    )


class ProjectListCreateView(APIView):
    @extend_schema(responses=ProjectSerializer(many=True))
    def get(self, request):
        qs = annotated_projects(MigrationProject.objects.filter(owner=request.user))
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs.order_by("-updated_at", "-id"), request)
        return paginator.get_paginated_response(ProjectSerializer(page, many=True).data)

    @extend_schema(request=ProjectWriteSerializer, responses=ProjectSerializer)
    def post(self, request):
        if MigrationProject.objects.filter(owner=request.user).count() >= settings.MAX_PROJECTS_PER_USER:
            raise ServiceError(f"You can have at most {settings.MAX_PROJECTS_PER_USER} projects.", code="project_limit", status_code=400)
        serializer = ProjectWriteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        project = serializer.save(owner=request.user)
        audit.log(request.user, "project.created", project, project, name=project.name)
        project = annotated_projects(MigrationProject.objects.filter(pk=project.pk)).get()
        return Response(ProjectSerializer(project).data, status=status.HTTP_201_CREATED)


class ProjectDetailView(APIView):
    def _fresh(self, project):
        return annotated_projects(MigrationProject.objects.filter(pk=project.pk)).get()

    @extend_schema(responses=ProjectSerializer)
    def get(self, request, pk):
        project = get_project(request, pk)
        return Response(ProjectSerializer(self._fresh(project)).data)

    @extend_schema(request=ProjectWriteSerializer, responses=ProjectSerializer)
    def patch(self, request, pk):
        project = get_project(request, pk)
        before_norm = project.config["normalization"]
        serializer = ProjectWriteSerializer(project, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        project = serializer.save()
        result = {"needs_reanalysis": False}
        if project.config["normalization"] != before_norm or "old_site_url" in request.data or "new_site_url" in request.data:
            if project.old_urls.exists() or project.new_urls.exists():
                result = {**renormalize(project), "needs_reanalysis": True}
        if "settings" in request.data:
            result["needs_reanalysis"] = True  # weights/thresholds only apply to new runs
        audit.log(request.user, "project.updated", project, project, fields=sorted(request.data.keys()))
        return Response({**ProjectSerializer(self._fresh(project)).data, "update_info": result})

    @extend_schema(request=OpenApiTypes.OBJECT, responses={204: None})
    def delete(self, request, pk):
        """Deleting a project removes all of its data, so the exact project name must be typed to confirm."""
        project = get_project(request, pk)
        if request.data.get("confirm_name") != project.name:
            raise ServiceError("Type the exact project name to confirm deletion.", code="confirmation_required",
                               details={"confirm_name": ["Type the exact project name."]})
        audit.log(request.user, "project.deleted", None, None, name=project.name, project_id=project.pk)
        project.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class UrlListView(APIView):
    """List/search imported URLs (used by the manual-destination picker)."""

    @extend_schema(responses=OldURLSerializer(many=True))
    def get(self, request, pk):
        project = get_project(request, pk)
        side = request.query_params.get("side", "new")
        Model, Serializer = (OldURL, OldURLSerializer) if side == "old" else (NewURL, NewURLSerializer)
        qs = Model.objects.filter(project=project)
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(Q(original_url__icontains=search) | Q(title__icontains=search))
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs.order_by("id"), request)
        return paginator.get_paginated_response(Serializer(page, many=True).data)


# ---------------------------------------------------------------- analysis runs
class AnalyzeView(APIView):
    throttle_classes = [AnalysisThrottle]

    @extend_schema(request=None, responses={202: RunSerializer})
    def post(self, request, pk):
        project = get_project(request, pk)
        run = jobs.start_analysis(project, request.user)
        audit.log(request.user, "analysis.started", project, run)
        run.refresh_from_db()
        return Response(RunSerializer(run).data, status=status.HTTP_202_ACCEPTED)


class RunListView(APIView):
    @extend_schema(responses=RunSerializer(many=True))
    def get(self, request, pk):
        project = get_project(request, pk)
        jobs.fail_stale_runs(project)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(project.runs.all(), request)
        return paginator.get_paginated_response(RunSerializer(page, many=True).data)


class RunDetailView(APIView):
    @extend_schema(responses=RunSerializer)
    def get(self, request, pk, run_id):
        project = get_project(request, pk)
        jobs.fail_stale_runs(project)
        run = project.runs.filter(pk=run_id).first()
        if run is None:
            raise ServiceError("Run not found.", code="not_found", status_code=404)
        return Response(RunSerializer(run).data)


class RunCompareView(APIView):
    """Compare what two runs suggested: which old URLs got a different destination."""

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, pk):
        project = get_project(request, pk)
        try:
            a, b = int(request.query_params["a"]), int(request.query_params["b"])
        except (KeyError, ValueError):
            raise ServiceError("Give two run numbers: ?a=1&b=2", code="invalid_runs")
        runs = {r.id: r for r in project.runs.filter(id__in=[a, b], status="completed")}
        if len(runs) != 2 and a != b:
            raise ServiceError("Both runs must exist and be completed.", code="invalid_runs", status_code=404)

        def load(run_id):
            return {r["old_url_id"]: r for r in MappingRecommendation.objects.filter(project=project, run_id=run_id).values(
                "old_url_id", "old_url__original_url", "new_url_text", "score", "band")}

        first, second = load(a), load(b)
        same = changed = gained = lost = 0
        changes = []
        for old_id, row_b in second.items():
            row_a = first.get(old_id)
            if row_a is None:
                gained += 1  # URL did not exist in the first run
                continue
            if row_a["new_url_text"] == row_b["new_url_text"]:
                same += 1
                continue
            if not row_a["new_url_text"] and row_b["new_url_text"]:
                gained += 1
            elif row_a["new_url_text"] and not row_b["new_url_text"]:
                lost += 1
            else:
                changed += 1
            if len(changes) < 200:
                changes.append({"old_url": row_b["old_url__original_url"], "before": row_a["new_url_text"], "before_score": row_a["score"],
                                "after": row_b["new_url_text"], "after_score": row_b["score"]})
        return Response({"a": a, "b": b, "same": same, "changed": changed, "newly_matched": gained, "newly_unmatched": lost,
                         "changes": changes, "changes_truncated": changed + gained + lost > len(changes)})


class AuditView(APIView):
    @extend_schema(responses=AuditSerializer(many=True))
    def get(self, request, pk):
        project = get_project(request, pk)
        qs = AuditLog.objects.filter(project=project).select_related("user")
        action = request.query_params.get("action")
        if action:
            qs = qs.filter(action__startswith=action)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(AuditSerializer(page, many=True).data)


# ---------------------------------------------------------------- dashboards (every number comes from the database)
def project_stats(project):
    reviews = MappingReview.objects.filter(project=project)
    total_old = project.old_urls.count()
    total_new = project.new_urls.count()
    by_status = {r["status"]: r["n"] for r in reviews.values("status").annotate(n=Count("id"))}
    by_band = {"high": 0, "medium": 0, "low": 0, "unmatched": 0}
    for row in reviews.values("recommendation__band").annotate(n=Count("id")):
        by_band[row["recommendation__band"] or "unmatched"] += row["n"]
    with_destination = reviews.filter(final_new_url__isnull=False).count()
    approved = by_status.get("approved", 0)
    rejected = by_status.get("rejected", 0)
    pending = by_status.get("pending", 0)
    risk_rows = {r["severity"]: r["n"] for r in RedirectRisk.objects.filter(project=project).values("severity").annotate(n=Count("id"))}
    history = []
    for run in project.runs.filter(status="completed").order_by("-finished_at")[:10]:
        history.append({"run_id": run.id, "finished_at": run.finished_at, "high": run.stats.get("high", 0), "medium": run.stats.get("medium", 0),
                        "low": run.stats.get("low", 0), "unmatched": run.stats.get("unmatched", 0), "average_score": run.stats.get("average_score", 0)})
    history.reverse()
    pct = lambda n: round(n / total_old * 100, 1) if total_old else 0  # noqa: E731
    return {
        "total_old": total_old, "total_new": total_new, "analyzed": reviews.exists(),
        "matched": with_destination, "unmatched": total_old - with_destination if reviews.exists() else 0,
        "bands": by_band, "approved": approved, "rejected": rejected, "pending": pending,
        "manual": reviews.filter(origin="manual").count(),
        "risks": {"high": risk_rows.get("high", 0), "medium": risk_rows.get("medium", 0), "low": risk_rows.get("low", 0), "info": risk_rows.get("info", 0),
                  "actionable": sum(risk_rows.get(k, 0) for k in ("high", "medium", "low"))},
        "coverage_percent": pct(with_destination) if reviews.exists() else 0,
        "review_completion_percent": pct(approved + rejected),
        "quality_checked_at": project.quality_checked_at, "history": history,
    }


class ProjectDashboardView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, pk):
        project = get_project(request, pk)
        return Response(project_stats(project))


class GlobalDashboardView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        projects = annotated_projects(MigrationProject.objects.filter(owner=request.user))
        rows, totals = [], {"projects": 0, "old_urls": 0, "new_urls": 0, "approved": 0, "pending": 0}
        for p in projects[:100]:
            rows.append({"id": p.id, "name": p.name, "old_count": p.old_count, "new_count": p.new_count, "approved": p.approved_count,
                         "pending": p.pending_count, "updated_at": p.updated_at,
                         "review_completion_percent": round(p.approved_count / p.old_count * 100, 1) if p.old_count else 0})
            totals["projects"] += 1
            totals["old_urls"] += p.old_count
            totals["new_urls"] += p.new_count
            totals["approved"] += p.approved_count
            totals["pending"] += p.pending_count
        return Response({"totals": totals, "projects": rows})
