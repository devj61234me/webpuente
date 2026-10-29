"""Runs the redirect risk checks for a project and stores the findings."""
from django.utils import timezone

from services import risks as risk_rules

from .models import MappingReview, NewURL, RedirectRisk


def mapping_rows(project):
    """One dict per old URL: everything the risk rules and the exporters need."""
    reviews = MappingReview.objects.filter(project=project).select_related("old_url", "final_new_url", "recommendation")
    rows = []
    for rv in reviews:
        final = rv.final_new_url
        rows.append(
            {
                "review_id": rv.id,
                "old_id": rv.old_url_id,
                "old_full": rv.old_url.normalized_url,
                "old_path_key": rv.old_url.path_key,
                "old_original": rv.old_url.original_url,
                "final_new_id": final.id if final else None,
                "final_full": final.normalized_url if final else "",
                "final_path_key": final.path_key if final else "",
                "final_original": final.original_url if final else "",
                "final_status_code": final.status_code if final else None,
                "status": rv.status,
                "origin": rv.origin,
                "score": rv.recommendation.score if rv.recommendation else 0,
                "band": rv.recommendation.band if rv.recommendation else "unmatched",
                "match_type": "manual" if rv.origin == MappingReview.Origin.MANUAL else (rv.recommendation.match_type if rv.recommendation else "none"),
                "reasons": rv.recommendation.reasons if rv.recommendation else [],
                "redirect_status": rv.redirect_status,
                "note": rv.note,
            }
        )
    return rows


def refresh_quality(project):
    """Recompute the findings from scratch (old findings are replaced) and return a summary."""
    rows = mapping_rows(project)
    new_pages = [{"id": n.id, "full": n.normalized_url} for n in NewURL.objects.filter(project=project).only("id", "normalized_url")]
    findings = risk_rules.evaluate(rows, new_pages, project.config)
    RedirectRisk.objects.filter(project=project).delete()
    RedirectRisk.objects.bulk_create(
        [
            RedirectRisk(
                project=project, kind=f["kind"], severity=f["severity"], source=f["source"], old_url_id=f["old_id"],
                new_url_id=f["new_id"], review_id=f["review_id"], message=f["message"], detail=f["detail"],
            )
            for f in findings
        ],
        batch_size=500,
    )
    project.quality_checked_at = timezone.now()
    project.save(update_fields=["quality_checked_at"])
    return risk_rules.summarize(findings)
