from django.urls import path

from . import views_exports, views_imports, views_mappings, views_projects as vp

urlpatterns = [
    path("dashboard/", vp.GlobalDashboardView.as_view()),
    path("projects/", vp.ProjectListCreateView.as_view()),
    path("projects/<int:pk>/", vp.ProjectDetailView.as_view()),
    path("projects/<int:pk>/dashboard/", vp.ProjectDashboardView.as_view()),
    path("projects/<int:pk>/audit/", vp.AuditView.as_view()),
    path("projects/<int:pk>/urls/", vp.UrlListView.as_view()),
    # importing
    path("projects/<int:pk>/imports/preview/", views_imports.ImportPreviewView.as_view()),
    path("projects/<int:pk>/imports/", views_imports.ImportView.as_view()),
    path("projects/<int:pk>/imports/<int:batch_id>/", views_imports.ImportDetailView.as_view()),
    path("projects/<int:pk>/fetch-metadata/", views_imports.FetchMetadataView.as_view()),
    # analysis
    path("projects/<int:pk>/analyze/", vp.AnalyzeView.as_view()),
    path("projects/<int:pk>/runs/", vp.RunListView.as_view()),
    path("projects/<int:pk>/runs/compare/", vp.RunCompareView.as_view()),
    path("projects/<int:pk>/runs/<int:run_id>/", vp.RunDetailView.as_view()),
    # review workspace
    path("projects/<int:pk>/mappings/", views_mappings.MappingListView.as_view()),
    path("projects/<int:pk>/mappings/bulk/", views_mappings.BulkView.as_view()),
    path("projects/<int:pk>/mappings/<int:review_id>/", views_mappings.MappingDetailView.as_view()),
    path("projects/<int:pk>/mappings/<int:review_id>/approve/", views_mappings.ApproveView.as_view()),
    path("projects/<int:pk>/mappings/<int:review_id>/reject/", views_mappings.RejectView.as_view()),
    path("projects/<int:pk>/mappings/<int:review_id>/reset/", views_mappings.ResetView.as_view()),
    path("projects/<int:pk>/mappings/<int:review_id>/undo/", views_mappings.UndoView.as_view()),
    path("projects/<int:pk>/mappings/<int:review_id>/assign/", views_mappings.AssignView.as_view()),
    # quality + exports
    path("projects/<int:pk>/quality/", views_exports.QualityView.as_view()),
    path("projects/<int:pk>/quality/run/", views_exports.QualityRunView.as_view()),
    path("projects/<int:pk>/exports/", views_exports.ExportListCreateView.as_view()),
    path("projects/<int:pk>/exports/<int:export_id>/download/", views_exports.ExportDownloadView.as_view()),
]
