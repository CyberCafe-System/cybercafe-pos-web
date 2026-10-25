import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from equipos.models import Equipo
from usuarios.decorators import admin_required

from .forms import ComponenteForm
from .models import Componente

logger = logging.getLogger(__name__)


@login_required
@admin_required
def componente_list(request):
    componentes_qs = (
        Componente.objects.select_related('equipo')
        .all()
        .order_by('equipo__nombre', 'nombre')
    )
    paginator = Paginator(componentes_qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    equipos = Equipo.objects.all().order_by('nombre')
    return render(request, 'componentes/componentes.html', {
        'componentes': page_obj,
        'page_obj': page_obj,
        'equipos': equipos,
    })


@login_required
@admin_required
def componente_create(request):
    if request.method == 'POST':
        form = ComponenteForm(request.POST)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, 'Componente registrado correctamente.')
            except Exception:
                logger.exception('Error al guardar el componente')
                messages.error(request, 'Ocurrió un error al guardar el componente. Intenta nuevamente.')
        else:
            for error in form.errors.values():
                messages.error(request, error.as_text().lstrip('* '))
    return redirect('componentes')


@login_required
@admin_required
def componente_edit(request):
    if request.method == 'POST':
        componente = get_object_or_404(Componente, pk=request.POST.get('componente_id'))
        form = ComponenteForm(request.POST, instance=componente)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, 'Componente actualizado correctamente.')
            except Exception:
                logger.exception('Error al actualizar el componente')
                messages.error(request, 'Ocurrió un error al actualizar el componente. Intenta nuevamente.')
        else:
            for error in form.errors.values():
                messages.error(request, error.as_text().lstrip('* '))
    return redirect('componentes')


@login_required
@admin_required
def componente_toggle(request):
    if request.method == 'POST':
        componente = get_object_or_404(Componente, pk=request.POST.get('componente_id'))
        componente.activo = not componente.activo
        componente.save(update_fields=['activo'])
    return redirect('componentes')

