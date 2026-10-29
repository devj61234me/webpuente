from django.shortcuts import get_object_or_404

from .models import MigrationProject


def get_project(request, pk):
    """Every endpoint loads its project through here: a project of another user is simply 'not found'."""
    return get_object_or_404(MigrationProject, pk=pk, owner=request.user)
