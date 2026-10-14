from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class ProtectedTemplateView(LoginRequiredMixin, TemplateView):
    """Vista de plantilla que exige una sesión autenticada."""
