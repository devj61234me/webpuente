"""
Running one matching job (an AnalysisRun). Called by projects/jobs.py, in a thread, a worker or inline.

Order of work:  load URLs -> (optional) embeddings -> match every old URL -> save results in ONE transaction
-> update reviews (keeping valid human decisions) -> run quality checks.
If anything fails the run is marked "failed" with a readable reason; no partial results are left behind.
"""
import logging
import time

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.exceptions import ServiceError
from services import embeddings
from services.matcher import Matcher, Page

from . import quality
from .models import AnalysisRun, MappingRecommendation, MappingReview

logger = logging.getLogger(__name__)
PROGRESS_EVERY = 50


def _page(obj):
    return Page(obj.id, obj.normalized_url, obj.path_key, obj.title, obj.meta_description, obj.h1)


def _touch(run_id, progress):
    AnalysisRun.objects.filter(pk=run_id).update(progress=progress, heartbeat_at=timezone.now())


def _semantic_vectors(old_pages, matcher, warnings):
    """Embed only what is needed: old pages that need fuzzy matching and the new pages shortlisted for them."""
    needs_fuzzy = [o for o in old_pages if o.full not in matcher.by_full and o.path_key not in matcher.by_path_key]
    shortlist = {o.id: matcher.candidates(o) for o in needs_fuzzy}
    new_ids = sorted({cid for ids in shortlist.values() for cid in ids})
    if len(needs_fuzzy) + len(new_ids) > settings.EMBEDDINGS_MAX_PAGES:
        warnings.append(f"Semantic matching was skipped: more than {settings.EMBEDDINGS_MAX_PAGES} pages would need embeddings.")
        return {}, {}
    try:
        old_vectors = embeddings.embed_texts([embeddings.embedding_text(o) for o in needs_fuzzy])
        new_vectors = embeddings.embed_texts([embeddings.embedding_text(matcher.new_pages[i]) for i in new_ids])
    except embeddings.EmbeddingError as exc:
        warnings.append(f"Semantic matching was skipped: {exc} Results use URL and page-detail matching only.")
        return {}, {}
    return {o.id: v for o, v in zip(needs_fuzzy, old_vectors)}, dict(zip(new_ids, new_vectors))


def execute_run(run_id):
    # Claim the run. If another worker already took it, do nothing (protects against double execution).
    claimed = AnalysisRun.objects.filter(pk=run_id, status=AnalysisRun.Status.QUEUED).update(
        status=AnalysisRun.Status.RUNNING, started_at=timezone.now(), heartbeat_at=timezone.now()
    )
    if not claimed:
        return
    run = AnalysisRun.objects.select_related("project").get(pk=run_id)
    try:
        _run(run)
    except ServiceError as exc:
        _fail(run, str(exc.detail))
    except Exception:  # noqa: BLE001 - never let a job crash silently
        logger.exception("Analysis run %s failed", run_id)
        _fail(run, "The analysis could not be completed. Please try again; if it keeps failing, contact support.")


def _fail(run, message):
    AnalysisRun.objects.filter(pk=run.pk).update(
        status=AnalysisRun.Status.FAILED, error_message=message[:500], finished_at=timezone.now()
    )


def _run(run):
    started = time.monotonic()
    project = run.project
    config = project.config
    old_objs = list(project.old_urls.all())
    new_objs = list(project.new_urls.all())
    if not old_objs or not new_objs:
        raise ServiceError("Import both the old and the new URL list before running the analysis.", code="lists_missing")

    old_pages = [_page(o) for o in old_objs]
    new_pages = [_page(n) for n in new_objs]
    warnings = []
    matcher = Matcher(new_pages, config, max_candidates=settings.MATCH_MAX_CANDIDATES)

    old_vectors = {}
    if config.get("use_embeddings"):
        if embeddings.is_configured():
            old_vectors, matcher.new_vectors = _semantic_vectors(old_pages, matcher, warnings)
        else:
            warnings.append("Semantic matching was requested but no embedding provider is configured on the server. It was not used.")

    # ---- match every old URL
    results = {}
    total = len(old_pages)
    for index, page in enumerate(old_pages, start=1):
        results[page.id] = matcher.match(page, old_vectors.get(page.id))
        if index % PROGRESS_EVERY == 0:
            _touch(run.pk, min(90, int(index / total * 90)))
    _touch(run.pk, 92)

    # ---- save everything together
    new_by_id = {n.id: n for n in new_objs}
    stats = {"high": 0, "medium": 0, "low": 0, "unmatched": 0, "ambiguous": 0, "exact": 0, "score_sum": 0,
             "evidence": {"url_only": 0, "metadata": 0, "semantic": 0}}
    with transaction.atomic():
        recs = []
        for page in old_pages:
            r = results[page.id]
            stats[r.band] += 1
            stats["ambiguous"] += int(r.ambiguous)
            stats["exact"] += int(r.match_type in ("exact_url", "exact_path"))
            stats["score_sum"] += r.score
            stats["evidence"][r.evidence] += 1
            alternatives = [
                {"new_id": a["new_id"], "url": new_by_id[a["new_id"]].normalized_url, "score": a["score"]} for a in r.alternatives
            ]
            recs.append(
                MappingRecommendation(
                    project=project, run=run, old_url_id=page.id, new_url_id=r.new_id,
                    new_url_text=new_by_id[r.new_id].normalized_url if r.new_id else "",
                    score=r.score, band=r.band, match_type=r.match_type, reasons=r.reasons,
                    components=r.components, alternatives=alternatives, evidence=r.evidence, ambiguous=r.ambiguous,
                )
            )
        MappingRecommendation.objects.bulk_create(recs, batch_size=500)
        # MySQL does not return ids from bulk inserts, so read them back.
        rec_by_old = {rec.old_url_id: rec for rec in MappingRecommendation.objects.filter(run=run)}
        existing = {rv.old_url_id: rv for rv in MappingReview.objects.filter(project=project)}
        stats.update(_update_reviews(project, old_objs, rec_by_old, existing, config))
        AnalysisRun.objects.filter(pk=run.pk).update(progress=96)

    try:
        risk_summary = quality.refresh_quality(project)
    except Exception:  # noqa: BLE001 - a failed quality check must not hide good matching results
        logger.exception("Quality check after run %s failed", run.pk)
        risk_summary = None
        warnings.append("The automatic quality check failed. Run it again from the Quality page.")

    stats["average_score"] = round(stats.pop("score_sum") / total, 1) if total else 0
    stats["total"] = total
    stats["warnings"] = warnings
    stats["risks"] = risk_summary["by_severity"] if risk_summary else None
    stats["seconds"] = round(time.monotonic() - started, 2)
    stats["semantic_used"] = bool(matcher.new_vectors)
    AnalysisRun.objects.filter(pk=run.pk).update(
        status=AnalysisRun.Status.COMPLETED, progress=100, finished_at=timezone.now(), stats=stats,
        old_count=len(old_objs), new_count=len(new_objs),
    )


def _update_reviews(project, old_objs, rec_by_old, existing, config):
    """Create/refresh one review per old URL. Human decisions that are still valid are kept."""
    default_status = config["redirect_status"]
    to_create, to_update = [], []
    created = preserved = reset = refreshed = 0
    for old in old_objs:
        rec = rec_by_old[old.id]
        review = existing.get(old.id)
        if review is None:
            to_create.append(
                MappingReview(project=project, old_url=old, recommendation=rec, final_new_url_id=rec.new_url_id,
                              final_url_text=rec.new_url_text, redirect_status=default_status)
            )
            created += 1
            continue
        keep = False
        if review.status == MappingReview.Status.APPROVED or review.origin == MappingReview.Origin.MANUAL:
            keep = review.final_new_url_id is not None
        elif review.status == MappingReview.Status.REJECTED:
            keep = rec.new_url_id is not None and rec.new_url_id == review.final_new_url_id  # same pair was rejected before
        review.recommendation = rec  # always point at the newest suggestion
        if keep:
            preserved += 1
        elif review.status == MappingReview.Status.PENDING:
            review.final_new_url_id, review.final_url_text, review.origin = rec.new_url_id, rec.new_url_text, MappingReview.Origin.AUTO
            refreshed += 1
        else:  # an old decision that no longer applies goes back to pending with the new suggestion
            review.status = MappingReview.Status.PENDING
            review.final_new_url_id, review.final_url_text, review.origin = rec.new_url_id, rec.new_url_text, MappingReview.Origin.AUTO
            review.decided_at = review.decided_by = review.prev_state = None
            reset += 1
        to_update.append(review)
    MappingReview.objects.bulk_create(to_create, batch_size=500)
    if to_update:
        MappingReview.objects.bulk_update(
            to_update,
            ["recommendation", "final_new_url", "final_url_text", "origin", "status", "decided_at", "decided_by", "prev_state"],
            batch_size=500,
        )
    return {"reviews_created": created, "decisions_preserved": preserved, "decisions_reset": reset, "suggestions_refreshed": refreshed}
