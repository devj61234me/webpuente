from django.conf import settings
from django.db import connection
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """Used by hosts as a health check. Returns 200 only if the database answers."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return Response({"status": "ok", "database": "ok"})
    except Exception:  # noqa: BLE001 - any database failure means "not healthy"
        return Response({"status": "error", "database": "unreachable"}, status=503)


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([AllowAny])
def public_config(request):
    """Limits and feature switches the frontend needs to show correct hints. No secrets here."""
    return Response(
        {
            "max_upload_mb": settings.MAX_UPLOAD_MB,
            "max_import_rows": settings.MAX_IMPORT_ROWS,
            "embeddings_enabled": bool(
                settings.EMBEDDINGS_ENABLED and settings.EMBEDDINGS_API_KEY and settings.EMBEDDINGS_MODEL
            ),
            "website_fetch_enabled": settings.ENABLE_WEBSITE_FETCH,
            "fetch_max_urls_per_request": settings.FETCH_MAX_URLS_PER_REQUEST,
            "job_mode": settings.JOB_MODE,
            "password_min_length": 10,
        }
    )
