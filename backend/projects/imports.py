"""Saving an uploaded/pasted URL list into the database: validate, normalise, de-duplicate, report."""
from django.conf import settings
from django.db import transaction

from core.exceptions import ServiceError
from services import importer
from services.urlnorm import NormRules, normalize_url

from . import audit
from .models import MappingReview, NewURL, OldURL, URLImportBatch, url_hash

MAX_ERRORS_STORED = 200
CHUNK = 400  # keeps "WHERE hash IN (...)" lists small enough for every database


def _to_int(value):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if 100 <= number <= 599 else None


def _model_for(kind):
    return OldURL if kind == URLImportBatch.Kind.OLD else NewURL


def reset_reviews_pointing_to(project, new_url_ids):
    """If destination pages are removed, decisions that used them go back to 'pending' (never left half-valid)."""
    if not new_url_ids:
        return 0
    reviews = MappingReview.objects.filter(project=project, final_new_url_id__in=new_url_ids)
    count = 0
    for review in reviews:
        review.status = MappingReview.Status.PENDING
        review.final_new_url = None
        review.final_url_text = ""
        review.origin = MappingReview.Origin.AUTO
        review.decided_at = None
        review.prev_state = None
        review.save()
        count += 1
    return count


def run_import(project, user, kind, table, column_map, mode, source, filename, sha256):
    rules = NormRules.from_dict(project.config["normalization"])
    base = project.old_site_url if kind == URLImportBatch.Kind.OLD else project.new_site_url
    Model = _model_for(kind)

    errors, seen, candidates = [], {}, []
    total = invalid = duplicates = 0

    # ---- 1. read and validate every row (nothing is saved yet)
    for row in importer.rows_with_mapping(table, column_map):
        total += 1
        raw = row.values.get("url", "")
        result = normalize_url(raw, rules, base)
        if not result.ok:
            invalid += 1
            errors.append({"row": row.row_number, "value": str(raw)[:200], "reason": result.error, "type": "invalid"})
            continue
        digest = url_hash(result.full)
        if digest in seen:
            duplicates += 1
            errors.append({"row": row.row_number, "value": str(raw)[:200], "reason": f"Duplicate of row {seen[digest]}.", "type": "duplicate"})
            continue
        seen[digest] = row.row_number
        status_raw = row.values.get("status_code")
        status_code = _to_int(status_raw) if status_raw else None
        if status_raw and status_code is None:
            errors.append({"row": row.row_number, "value": str(status_raw)[:50], "reason": "Status code is not a number from 100 to 599; ignored.", "type": "warning"})
        candidates.append(
            {
                "original_url": str(raw).strip(),
                "normalized_url": result.full,
                "url_hash": digest,
                "host": result.host,
                "path_key": result.path_key,
                "title": row.values.get("title", "")[:500],
                "meta_description": row.values.get("meta_description", "")[:1000],
                "h1": row.values.get("h1", "")[:500],
                "canonical_url": row.values.get("canonical_url", "")[: settings.MAX_URL_LENGTH],
                "status_code": status_code,
                "row_number": row.row_number,
            }
        )

    if not candidates:
        raise ServiceError(
            "No valid URLs were found, so nothing was imported.", code="no_valid_urls",
            details={"errors": errors[:20], "invalid": invalid, "duplicates": duplicates},
        )

    # ---- 2. save everything in one transaction, so a failure never leaves a half-imported list
    with transaction.atomic():
        existing = {}
        hashes = list(seen)
        for start in range(0, len(hashes), CHUNK):
            for obj in Model.objects.filter(project=project, url_hash__in=hashes[start : start + CHUNK]):
                existing[obj.url_hash] = obj
        if Model.objects.filter(project=project).count() + (len(candidates) - len(existing)) > settings.MAX_URLS_PER_PROJECT:
            raise ServiceError(
                f"A project can hold at most {settings.MAX_URLS_PER_PROJECT} URLs per list.", code="too_many_urls", status_code=413
            )

        batch = URLImportBatch.objects.create(
            project=project, kind=kind, mode=mode, source=source, filename=filename[:255], file_sha256=sha256,
            column_map=column_map, total_rows=total, invalid_count=invalid, duplicate_count=duplicates,
            errors=errors[:MAX_ERRORS_STORED], created_by=user,
        )
        to_create, to_update = [], []
        for item in candidates:
            current = existing.get(item["url_hash"])
            if current is None:
                to_create.append(Model(project=project, batch=batch, **item))
                continue
            changed = False  # existing URL: only fill in details that were supplied (never blank anything out)
            for key in ("title", "meta_description", "h1", "canonical_url", "status_code"):
                if item[key] not in ("", None) and getattr(current, key) != item[key]:
                    setattr(current, key, item[key])
                    changed = True
            if changed:
                to_update.append(current)
        Model.objects.bulk_create(to_create, batch_size=500)
        if to_update:
            Model.objects.bulk_update(to_update, ["title", "meta_description", "h1", "canonical_url", "status_code"], batch_size=500)

        removed = 0
        if mode == URLImportBatch.Mode.REPLACE:
            stale = Model.objects.filter(project=project).exclude(url_hash__in=hashes) if len(hashes) <= 900 else None
            if stale is None:  # long lists: compare in Python instead of a huge NOT IN
                keep = set(hashes)
                stale_ids = [i for i, h in Model.objects.filter(project=project).values_list("id", "url_hash") if h not in keep]
            else:
                stale_ids = list(stale.values_list("id", flat=True))
            if kind == URLImportBatch.Kind.NEW:
                reset_reviews_pointing_to(project, stale_ids)
            for start in range(0, len(stale_ids), CHUNK):
                Model.objects.filter(id__in=stale_ids[start : start + CHUNK]).delete()
            removed = len(stale_ids)

        batch.imported_count = len(to_create)
        batch.updated_count = len(to_update)
        batch.removed_count = removed
        batch.save(update_fields=["imported_count", "updated_count", "removed_count"])
        audit.log(user, "import.completed", project, batch, kind=kind, imported=batch.imported_count,
                  invalid=invalid, duplicates=duplicates, removed=removed, filename=filename[:100])
    return batch, len(errors) > MAX_ERRORS_STORED


def create_manual_new_url(project, user, raw):
    """A reviewer typed a destination that is not in the imported list."""
    rules = NormRules.from_dict(project.config["normalization"])
    result = normalize_url(raw, rules, project.new_site_url)
    if not result.ok:
        raise ServiceError(result.error, code="invalid_url", details={"url": [result.error]})
    digest = url_hash(result.full)
    obj, created = NewURL.objects.get_or_create(
        project=project, url_hash=digest,
        defaults={"original_url": str(raw).strip(), "normalized_url": result.full, "host": result.host,
                  "path_key": result.path_key, "source": "manual"},
    )
    return obj, created
