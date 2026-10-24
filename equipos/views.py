from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render

from componentes.models import Componente
from usuarios.decorators import admin_required
from .forms import EquipoForm
from .models import Equipo


@login_required
@admin_required
def equipo_list(request):
    equipos_qs = Equipo.objects.prefetch_related('componentes').all().order_by('equipo_id')
    paginator = Paginator(equipos_qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    componentes = Componente.objects.select_related('equipo').filter(
        activo=True
    ).exclude(
        estado='REQUIERE_REEMPLAZO'
    ).order_by('tipo', 'nombre')
    componentes_libres = [c for c in componentes if c.equipo_id is None]
    return render(request, 'equipos/equipos.html', {
        'equipos': page_obj,
        'page_obj': page_obj,
        'componentes': componentes,
        'componentes_libres': componentes_libres,
    })


@login_required
@admin_required
def equipo_create(request):
    if request.method == 'POST':
        form = EquipoForm(request.POST)
        if form.is_valid():
            try:
                equipo = form.save()
                componentes_ids = request.POST.getlist('componentes')
                if componentes_ids:
                    Componente.objects.filter(pk__in=componentes_ids).update(equipo=equipo)
                messages.success(request, 'Equipo registrado correctamente.')
            except Exception as e:
                messages.error(request, f'Error al guardar el equipo: {e}')
        else:
            for error in form.errors.values():
                messages.error(request, error.as_text().lstrip('* '))
    return redirect('equipos')


@login_required
@admin_required
def equipo_edit(request):
    if request.method == 'POST':
        equipo = get_object_or_404(Equipo, pk=request.POST.get('equipo_id'))
        form = EquipoForm(request.POST, instance=equipo)
        if form.is_valid():
            try:
                equipo = form.save()
                componentes_ids = request.POST.getlist('componentes')
                # Desvincular los que ya no están seleccionados para este equipo
                equipo.componentes.exclude(pk__in=componentes_ids).update(equipo=None)
                # Vincular los seleccionados
                if componentes_ids:
                    Componente.objects.filter(pk__in=componentes_ids).update(equipo=equipo)
                messages.success(request, 'Equipo actualizado correctamente.')
            except Exception as e:
                messages.error(request, f'Error al actualizar el equipo: {e}')
        else:
            for error in form.errors.values():
                messages.error(request, error.as_text().lstrip('* '))
    return redirect('equipos')


@login_required
@admin_required
def equipo_delete(request):
    if request.method == 'POST':
        equipo = get_object_or_404(Equipo, pk=request.POST.get('equipo_id'))
        try:
            # Desvincular componentes asignados
            equipo.componentes.update(equipo=None)
            equipo.delete()
            messages.success(request, f'Equipo {equipo.nombre} eliminado correctamente.')
        except IntegrityError:
            messages.error(request, 'No se puede eliminar el equipo porque tiene rentas o registros asociados.')
        except Exception as e:
            messages.error(request, f'Error al eliminar el equipo: {e}')
    return redirect('equipos')

