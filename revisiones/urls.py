from django.urls import path
from . import views

urlpatterns = [
    path('', views.revisiones_list, name='revisiones'),
    path('crear/', views.crear_revision, name='crear_revision'),
    path('reiniciar/<int:revision_id>/', views.reiniciar_revision, name='reiniciar_revision'),
]
