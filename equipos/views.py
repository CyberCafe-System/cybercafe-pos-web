from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render

from usuarios.decorators import admin_required
from .forms import EquipoForm
from .models import Equipo


@login_required
@admin_required
def equipo_list(request):
    equipos = Equipo.objects.prefetch_related('componentes').all().order_by('equipo_id')
    return render(request, 'equipos/equipos.html', {'equipos': equipos})


@login_required
@admin_required
def equipo_create(request):
    if request.method == 'POST':
        form = EquipoForm(request.POST)
        if form.is_valid():
            try:
                form.save()
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
                form.save()
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

