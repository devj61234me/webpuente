from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from django.conf import settings

from core.exceptions import ServiceError
from core.pagination import StandardPagination

from . import audit
from .common import get_project
from .defaults import REDIRECT_STATUSES
from .imports import create_manual_new_url
from .models import MappingReview, NewURL
from .serializers import MappingSerializer

ORDERINGS = {
    "id": "id", "score": "recommendation__score", "-score": "-recommendation__score",
    "old_url": "old_url__original_url", "-old_url": "-old_url__original_url", "status": "status", "-status": "-status",
}


def review_queryset(project):
    return (
        MappingReview.objects.filter(project=project)
        .select_related("old_url", "recommendation", "final_new_url")
        .annotate(risk_count=Count("risks", filter=Q(risks__severity__in=["high", "medium", "low"]), distinct=True))
    )


def apply_filters(qs, params):
    if search := params.get("search", "").strip():
        qs = qs.filter(Q(old_url__original_url__icontains=search) | Q(final_url_text__icontains=search))
    if band := params.get("band"):
        qs = qs.filter(recommendation__band__in=band.split(","))
    if match_type := params.get("match_type"):
        qs = qs.filter(recommendation__match_type__in=match_type.split(","))
    if state := params.get("status"):
        qs = qs.filter(status__in=state.split(","))
    if params.get("unmatched") == "true":
        qs = qs.filter(final_new_url__isnull=True)
    if params.get("ambiguous") == "true":
        qs = qs.filter(recommendation__ambiguous=True)
    if params.get("origin") in ("auto", "manual"):
        qs = qs.filter(origin=params["origin"])
    if params.get("has_risk") == "true":
        qs = qs.filter(risk_count__gt=0)
    return qs


def get_review(request, pk, review_id):
    project = get_project(request, pk)
    review = review_queryset(project).filter(pk=review_id).first()
    if review is None:
        raise ServiceError("Mapping not found.", code="not_found", status_code=404)
    return project, review


def snapshot(review):
    """What undo restores."""
    return {"status": review.status, "final_new_url_id": review.final_new_url_id, "final_url_text": review.final_url_text,
            "origin": review.origin, "redirect_status": review.redirect_status}


def shared_destination_count(project, review, destination_id):
    """How many OTHER old URLs (not rejected) already point at this destination."""
    if not destination_id:
        return 0
    return MappingReview.objects.filter(project=project, final_new_url_id=destination_id).exclude(pk=review.pk).exclude(status="rejected").count()


def decide(review, user, project, new_status, **changes):
    review.prev_state = snapshot(review)
    review.status = new_status
    for key, value in changes.items():
        setattr(review, key, value)
    review.decided_by, review.decided_at = user, timezone.now()
    review.save()
    project.last_decision_at = timezone.now()
    project.save(update_fields=["last_decision_at"])


def check_approval(project, review, body):
    """Raises if a confirmation is still needed. Used by single and bulk approval."""
    if not review.final_new_url_id:
        raise ServiceError("This URL has no destination. Assign one manually first.", code="no_destination")
    rec = review.recommendation
    if review.origin == "auto" and rec and rec.band == "low" and not body.get("confirm_low_confidence"):
        raise ServiceError(
            f"The match score is low ({rec.score}). Confirm that you checked these pages are equivalent.",
            code="low_confidence_confirmation_required", details={"score": rec.score},
        )
    shared = shared_destination_count(project, review, review.final_new_url_id)
    if shared and not body.get("confirm_many_to_one"):
        raise ServiceError(
            f"{shared} other old URL(s) already point to this destination. Confirm this many-to-one redirect is intended.",
            code="many_to_one_confirmation_required", details={"count": shared},
        )


class MappingListView(APIView):
    @extend_schema(responses=MappingSerializer(many=True))
    def get(self, request, pk):
        project = get_project(request, pk)
        qs = apply_filters(review_queryset(project), request.query_params)
        ordering = ORDERINGS.get(request.query_params.get("ordering", "id"), "id")
        qs = qs.order_by(ordering, "id")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(MappingSerializer(page, many=True).data)


class MappingDetailView(APIView):
    @extend_schema(responses=MappingSerializer)
    def get(self, request, pk, review_id):
        _, review = get_review(request, pk, review_id)
        return Response(MappingSerializer(review).data)

    @extend_schema(request=OpenApiTypes.OBJECT, responses=MappingSerializer)
    def patch(self, request, pk, review_id):
        project, review = get_review(request, pk, review_id)
        changed = []
        if "note" in request.data:
            review.note = str(request.data["note"])[:500]
            changed.append("note")
        if "redirect_status" in request.data:
            try:
                value = int(request.data["redirect_status"])
            except (TypeError, ValueError):
                value = 0
            if value not in REDIRECT_STATUSES:
                raise ServiceError("Redirect status must be 301, 302, 307 or 308.", code="invalid_status")
            review.redirect_status = value
            changed.append("redirect_status")
        review.save()
        audit.log(request.user, "mapping.edited", project, review, fields=changed)
        return Response(MappingSerializer(review_queryset(project).get(pk=review.pk)).data)


class _Action(APIView):
    def respond(self, project, review):
        return Response(MappingSerializer(review_queryset(project).get(pk=review.pk)).data)


class ApproveView(_Action):
    @extend_schema(request=OpenApiTypes.OBJECT, responses=MappingSerializer)
    def post(self, request, pk, review_id):
        project, review = get_review(request, pk, review_id)
        check_approval(project, review, request.data)
        decide(review, request.user, project, MappingReview.Status.APPROVED)
        audit.log(request.user, "mapping.approved", project, review, old=review.old_url.original_url, new=review.final_url_text)
        return self.respond(project, review)


class RejectView(_Action):
    @extend_schema(request=None, responses=MappingSerializer)
    def post(self, request, pk, review_id):
        project, review = get_review(request, pk, review_id)
        decide(review, request.user, project, MappingReview.Status.REJECTED)
        audit.log(request.user, "mapping.rejected", project, review, old=review.old_url.original_url)
        return self.respond(project, review)


class ResetView(_Action):
    """Back to 'pending' with the engine's own suggestion."""

    @extend_schema(request=None, responses=MappingSerializer)
    def post(self, request, pk, review_id):
        project, review = get_review(request, pk, review_id)
        rec = review.recommendation
        decide(review, request.user, project, MappingReview.Status.PENDING,
               final_new_url_id=rec.new_url_id if rec else None, final_url_text=rec.new_url_text if rec else "", origin="auto")
        audit.log(request.user, "mapping.reset", project, review)
        return self.respond(project, review)


class UndoView(_Action):
    @extend_schema(request=None, responses=MappingSerializer)
    def post(self, request, pk, review_id):
        project, review = get_review(request, pk, review_id)
        previous = review.prev_state
        if not previous:
            raise ServiceError("There is nothing to undo for this mapping.", code="nothing_to_undo")
        destination = NewURL.objects.filter(pk=previous["final_new_url_id"], project=project).first() if previous["final_new_url_id"] else None
        review.status, review.origin, review.redirect_status = previous["status"], previous["origin"], previous["redirect_status"]
        review.final_new_url, review.final_url_text = destination, destination.normalized_url if destination else ""
        review.prev_state = None
        review.save()
        project.last_decision_at = timezone.now()
        project.save(update_fields=["last_decision_at"])
        audit.log(request.user, "mapping.undone", project, review)
        return self.respond(project, review)


class AssignView(_Action):
    """Choose the destination yourself (an imported new URL, or any valid URL you type). Counts as approved."""

    @extend_schema(request=OpenApiTypes.OBJECT, responses=MappingSerializer)
    def post(self, request, pk, review_id):
        project, review = get_review(request, pk, review_id)
        new_id, raw = request.data.get("new_url_id"), request.data.get("url")
        with transaction.atomic():
            if new_id:
                destination = NewURL.objects.filter(pk=new_id, project=project).first()
                if destination is None:
                    raise ServiceError("That destination does not belong to this project.", code="not_found", status_code=404)
            elif raw:
                destination, _ = create_manual_new_url(project, request.user, raw)
            else:
                raise ServiceError("Pick a destination or type a URL.", code="destination_required")
            if destination.normalized_url == review.old_url.normalized_url:
                raise ServiceError("A page cannot redirect to itself.", code="self_redirect")
            shared = shared_destination_count(project, review, destination.id)
            if shared and not request.data.get("confirm_many_to_one"):
                raise ServiceError(f"{shared} other old URL(s) already point to this destination. Confirm this many-to-one redirect is intended.",
                                   code="many_to_one_confirmation_required", details={"count": shared})
            decide(review, request.user, project, MappingReview.Status.APPROVED,
                   final_new_url=destination, final_url_text=destination.normalized_url, origin=MappingReview.Origin.MANUAL)
            audit.log(request.user, "mapping.assigned", project, review, old=review.old_url.original_url, new=destination.normalized_url)
        return self.respond(project, review)


class BulkView(APIView):
    """Approve, reject or reset many rows. Bulk approval must be confirmed and never skips the safety checks silently."""

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request, pk):
        project = get_project(request, pk)
        action = request.data.get("action")
        ids = request.data.get("ids")
        if action not in ("approve", "reject", "reset"):
            raise ServiceError("Action must be approve, reject or reset.", code="invalid_action")
        if not isinstance(ids, list) or not ids or not all(isinstance(i, int) for i in ids):
            raise ServiceError("Select at least one row.", code="ids_required")
        if len(ids) > settings.MAX_BULK_ITEMS:
            raise ServiceError(f"Select at most {settings.MAX_BULK_ITEMS} rows at a time.", code="too_many_items")
        if action == "approve" and not request.data.get("confirm"):
            raise ServiceError("Bulk approval must be confirmed.", code="confirmation_required")
        body = {"confirm_low_confidence": bool(request.data.get("include_low")), "confirm_many_to_one": bool(request.data.get("confirm_many_to_one"))}
        updated, skipped = 0, {"no_destination": 0, "low_confidence": 0, "many_to_one": 0}
        with transaction.atomic():
            for review in review_queryset(project).filter(id__in=ids):  # only this project's rows can be touched
                if action == "approve":
                    try:
                        check_approval(project, review, body)
                    except ServiceError as exc:
                        key = {"no_destination": "no_destination", "low_confidence_confirmation_required": "low_confidence",
                               "many_to_one_confirmation_required": "many_to_one"}.get(exc.code)
                        skipped[key] += 1
                        continue
                    decide(review, request.user, project, MappingReview.Status.APPROVED)
                elif action == "reject":
                    decide(review, request.user, project, MappingReview.Status.REJECTED)
                else:
                    rec = review.recommendation
                    decide(review, request.user, project, MappingReview.Status.PENDING,
                           final_new_url_id=rec.new_url_id if rec else None, final_url_text=rec.new_url_text if rec else "", origin="auto")
                updated += 1
            audit.log(request.user, f"bulk.{action}", project, None, updated=updated, skipped=skipped, requested=len(ids))
        return Response({"updated": updated, "skipped": skipped, "requested": len(ids)})
