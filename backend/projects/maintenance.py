"""Re-applying normalisation rules to URLs that are already imported (when the project's rules change)."""
from django.db import transaction

from services.urlnorm import NormRules, normalize_url

from .models import MappingRecommendation, MappingReview, NewURL, OldURL, url_hash

CHUNK = 500


def renormalize(project):
    """Recompute normalised URLs from the ORIGINAL URLs with the project's current rules.
    URLs that now collapse into one are merged (the first one is kept; decisions and suggestions are moved to it).
    Returns {"updated": n, "merged": n}."""
    rules = NormRules.from_dict(project.config["normalization"])
    updated = merged = 0
    with transaction.atomic():
        for Model, base in ((OldURL, project.old_site_url), (NewURL, project.new_site_url)):
            survivors = {}
            changed, duplicates = [], []
            for obj in Model.objects.filter(project=project).order_by("id"):
                result = normalize_url(obj.original_url, rules, base)
                if not result.ok:
                    survivors[obj.url_hash] = obj  # cannot happen for imported rows; leave untouched
                    continue
                digest = url_hash(result.full)
                if digest in survivors:
                    duplicates.append((obj, survivors[digest]))
                    continue
                survivors[digest] = obj
                if obj.url_hash != digest or obj.normalized_url != result.full:
                    obj.normalized_url, obj.url_hash, obj.host, obj.path_key = result.full, "tmp-" + str(obj.pk), result.host, result.path_key
                    obj._final_hash = digest
                    changed.append(obj)
            for dup, keeper in duplicates:
                if Model is NewURL:
                    MappingReview.objects.filter(project=project, final_new_url=dup).update(final_new_url=keeper, final_url_text=keeper.normalized_url)
                    MappingRecommendation.objects.filter(project=project, new_url=dup).update(new_url=keeper, new_url_text=keeper.normalized_url)
                dup.delete()
                merged += 1
            # Duplicates are removed first, then a two-phase update: free the old hashes, then write the final ones
            # (this order keeps the unique constraint satisfied at every step).
            for start in range(0, len(changed), CHUNK):
                Model.objects.bulk_update(changed[start : start + CHUNK], ["normalized_url", "url_hash", "host", "path_key"])
            for obj in changed:
                obj.url_hash = obj._final_hash
            for start in range(0, len(changed), CHUNK):
                Model.objects.bulk_update(changed[start : start + CHUNK], ["url_hash"])
            updated += len(changed)
    return {"updated": updated, "merged": merged}
