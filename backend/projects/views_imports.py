import json

from django.conf import settings
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import ServiceError
from core.pagination import StandardPagination
from core.throttles import FetchThrottle, ImportThrottle
from services import importer, safe_fetch

from . import audit
from .common import get_project
from .imports import run_import
from .models import NewURL, OldURL, URLImportBatch
from .serializers import ImportBatchSerializer


def _read_input(request):
    """Return (table, sha256, filename, source) from an uploaded file or pasted text."""
    upload = request.FILES.get("file")
    text = request.data.get("text")
    if upload is not None:
        if upload.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
            raise ServiceError(f"The file is larger than {settings.MAX_UPLOAD_MB} MB.", code="file_too_large", status_code=413)
        table, sha = importer.table_from_upload(upload.read(settings.MAX_UPLOAD_MB * 1024 * 1024 + 1), upload.name)
        return table, sha, upload.name, "file"
    if isinstance(text, str) and text.strip():
        table, sha = importer.table_from_text(text)
        return table, sha, "", "paste"
    raise ServiceError("Upload a CSV/XLSX file or paste a list of URLs.", code="input_required")


def _kind(request):
    kind = request.data.get("kind")
    if kind not in (URLImportBatch.Kind.OLD, URLImportBatch.Kind.NEW):
        raise ServiceError("Choose whether this is the old or the new URL list.", code="invalid_kind", details={"kind": ["Choose old or new."]})
    return kind


def _column_map(request):
    raw = request.data.get("column_map")
    if raw in (None, ""):
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raise ServiceError("The column choice is not valid.", code="invalid_column_map")
    if not isinstance(raw, dict):
        raise ServiceError("The column choice is not valid.", code="invalid_column_map")
    return {k: (None if v in (None, "", "none") else int(v)) for k, v in raw.items() if v is not None or k == "url"}


class ImportPreviewView(APIView):
    """Step 1: read the file/text and suggest which column is which. Nothing is saved."""

    parser_classes = [MultiPartParser, JSONParser]
    throttle_classes = [ImportThrottle]

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request, pk):
        get_project(request, pk)
        _kind(request)
        table, _, filename, source = _read_input(request)
        return Response({**importer.preview(table), "filename": filename, "source": source})


class ImportView(APIView):
    parser_classes = [MultiPartParser, JSONParser]
    throttle_classes = [ImportThrottle]

    @extend_schema(responses=ImportBatchSerializer(many=True))
    def get(self, request, pk):
        project = get_project(request, pk)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(project.import_batches.all(), request)
        return paginator.get_paginated_response(ImportBatchSerializer(page, many=True).data)

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: ImportBatchSerializer})
    def post(self, request, pk):
        """Step 2: save the URLs using the (possibly corrected) column choice."""
        project = get_project(request, pk)
        kind = _kind(request)
        mode = request.data.get("mode", URLImportBatch.Mode.APPEND)
        if mode not in (URLImportBatch.Mode.APPEND, URLImportBatch.Mode.REPLACE):
            raise ServiceError("Mode must be append or replace.", code="invalid_mode")
        table, sha, filename, source = _read_input(request)
        column_map = _column_map(request) or importer.suggest_mapping(table.headers, table.rows)
        batch, truncated = run_import(project, request.user, kind, table, column_map, mode, source, filename, sha)
        return Response({**ImportBatchSerializer(batch).data, "errors": batch.errors, "errors_truncated": truncated,
                         "needs_reanalysis": project.runs.exists()}, status=status.HTTP_201_CREATED)


class ImportDetailView(APIView):
    @extend_schema(responses=ImportBatchSerializer)
    def get(self, request, pk, batch_id):
        project = get_project(request, pk)
        batch = project.import_batches.filter(pk=batch_id).first()
        if batch is None:
            raise ServiceError("Import not found.", code="not_found", status_code=404)
        return Response({**ImportBatchSerializer(batch).data, "errors": batch.errors})


class FetchMetadataView(APIView):
    """Optional: download a few pages to read their title/description/H1. Off unless the server enables it."""

    throttle_classes = [FetchThrottle]

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request, pk):
        project = get_project(request, pk)
        if not settings.ENABLE_WEBSITE_FETCH:
            raise ServiceError("Website fetching is switched off on this server.", code="fetch_disabled", status_code=403)
        side = request.data.get("side")
        if side not in ("old", "new"):
            raise ServiceError("Choose old or new.", code="invalid_side")
        Model = OldURL if side == "old" else NewURL
        ids = request.data.get("ids")
        limit = settings.FETCH_MAX_URLS_PER_REQUEST
        qs = Model.objects.filter(project=project)
        if isinstance(ids, list) and ids:
            qs = qs.filter(id__in=[i for i in ids if isinstance(i, int)][:limit])
        else:
            qs = qs.filter(title="")  # default: pages that still have no title
        objects = list(qs.order_by("id")[:limit])
        robots = safe_fetch.RobotsCache()
        results, to_update = [], []
        for obj in objects:
            details = safe_fetch.fetch_page_details(obj.normalized_url, robots)
            results.append({"id": obj.id, "url": obj.original_url, "status_code": details.get("status_code"), "error": details.get("error"),
                            "title": details.get("title", "")})
            for field in ("title", "h1", "meta_description", "canonical_url"):
                if details.get(field):
                    setattr(obj, field, details[field])
            if details.get("status_code"):
                obj.status_code = details["status_code"]
            obj.source = "fetch" if details.get("status_code") else obj.source
            to_update.append(obj)
        if to_update:
            Model.objects.bulk_update(to_update, ["title", "h1", "meta_description", "canonical_url", "status_code", "source"])
        audit.log(request.user, "fetch.completed", project, None, side=side, requested=len(objects))
        return Response({"fetched": len([r for r in results if r["status_code"]]), "failed": len([r for r in results if not r["status_code"]]),
                         "limit": limit, "results": results})
