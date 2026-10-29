from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from . import views

admin_path = getattr(settings, "ADMIN_URL", "admin/")

urlpatterns = [
    path(admin_path, admin.site.urls),
    path("api/health/", views.health),
    path("api/config/", views.public_config),
    path("api/auth/", include("accounts.urls")),
    path("api/", include("projects.urls")),
]

if settings.ENABLE_API_DOCS:
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="api-docs"),
    ]
