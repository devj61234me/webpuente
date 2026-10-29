from django.contrib import admin

from . import models

for model in (models.MigrationProject, models.AnalysisRun, models.AuditLog, models.ExportJob):
    admin.site.register(model)
