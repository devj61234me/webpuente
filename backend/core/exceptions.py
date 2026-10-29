"""One error format for the whole API:
{"error": {"code": "...", "message": "...", "details": {...}}}
The frontend reads `message` for toasts and `details` for form fields."""
import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


class ServiceError(APIException):
    """An expected problem with a clear message for the user (bad input, conflict, limit reached...)."""

    def __init__(self, message, code="error", status_code=400, details=None):
        super().__init__(detail=message)
        self.code = code
        self.status_code = status_code
        self.extra_details = details or {}


def _flatten(value):
    """Turn DRF's nested error structure into plain strings."""
    if isinstance(value, dict):
        return {key: _flatten(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_flatten(item) for item in value]
    return str(value)


def _first_message(details):
    if isinstance(details, dict):
        for item in details.values():
            found = _first_message(item)
            if found:
                return found
    elif isinstance(details, list):
        for item in details:
            found = _first_message(item)
            if found:
                return found
    elif isinstance(details, str):
        return details
    return None


def api_exception_handler(exc, context):
    if isinstance(exc, Http404):
        return Response({"error": {"code": "not_found", "message": "Not found.", "details": {}}}, status=404)
    if isinstance(exc, DjangoPermissionDenied):
        return Response({"error": {"code": "forbidden", "message": "You do not have access.", "details": {}}}, status=403)

    response = drf_exception_handler(exc, context)
    if response is None:
        # A bug on our side: log it (without request data) and hide the details from the user.
        logger.exception("Unhandled error in API view")
        return Response(
            {"error": {"code": "server_error", "message": "Something went wrong on our side. Please try again.", "details": {}}},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, ServiceError):
        body = {"code": exc.code, "message": str(exc.detail), "details": exc.extra_details}
    elif isinstance(exc, ValidationError):
        details = _flatten(exc.detail)
        body = {"code": "validation_error", "message": _first_message(details) or "Please check the form.", "details": details}
    elif response.status_code == 401:
        body = {"code": "not_authenticated", "message": "Your session has expired. Please sign in again.", "details": {}}
    elif response.status_code == 429:
        body = {"code": "rate_limited", "message": "Too many requests. Please wait a moment and try again.", "details": {}}
    else:
        message = _first_message(_flatten(response.data)) or "Request failed."
        body = {"code": getattr(exc, "default_code", "error"), "message": message, "details": {}}
    response.data = {"error": body}
    return response
