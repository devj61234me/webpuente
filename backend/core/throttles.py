"""Rate limits. The rate text comes from settings at request time, so it can be changed
through environment variables (and overridden in tests)."""
from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle


class _SettingsThrottle(SimpleRateThrottle):
    setting_name = ""
    per_ip = False

    def get_rate(self):
        return getattr(settings, self.setting_name)

    def get_cache_key(self, request, view):
        if not self.per_ip and request.user and request.user.is_authenticated:
            ident = f"user-{request.user.pk}"
        else:
            ident = f"ip-{self.get_ident(request)}"
        return f"throttle_{self.scope}_{ident}"


class AuthThrottle(_SettingsThrottle):
    scope, setting_name, per_ip = "auth", "AUTH_RATE", True


class ImportThrottle(_SettingsThrottle):
    scope, setting_name = "import", "IMPORT_RATE"


class AnalysisThrottle(_SettingsThrottle):
    scope, setting_name = "analysis", "ANALYSIS_RATE"


class ExportThrottle(_SettingsThrottle):
    scope, setting_name = "export", "EXPORT_RATE"


class FetchThrottle(_SettingsThrottle):
    scope, setting_name = "fetch", "FETCH_RATE"
