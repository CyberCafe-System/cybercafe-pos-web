import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from equipos.models import Equipo
from usuarios.decorators import admin_required
from usuarios.models import registrar_auditoria

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
                with transaction.atomic():
                    comp = form.save()
                    if comp.equipo and comp.equipo.estado == 'DISPONIBLE' and (not comp.activo or comp.estado == 'REQUIERE_REEMPLAZO'):
                        comp.equipo.estado = 'DEFECTUOSO' if comp.estado == 'REQUIERE_REEMPLAZO' else 'EN_MANTENIMIENTO'
                        comp.equipo.save(update_fields=['estado'])
                        messages.warning(
                            request,
                            f'El equipo "{comp.equipo.nombre}" fue cambiado a "{comp.equipo.get_estado_display()}" '
                            f'porque el componente "{comp.nombre}" requiere reemplazo o está desactivado.'
                        )
                    registrar_auditoria(
                        usuario=request.user,
                        accion='CREAR_COMPONENTE',
                        entidad='Componente',
                        entidad_id=comp.componente_id,
                        valor_nuevo={'nombre': comp.nombre, 'tipo': comp.tipo, 'estado': comp.estado},
                        ip=request.META.get('REMOTE_ADDR'),
                    )
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
        valor_prev = {'nombre': componente.nombre, 'estado': componente.estado, 'equipo_id': componente.equipo_id}
        form = ComponenteForm(request.POST, instance=componente)
        if form.is_valid():
            try:
                with transaction.atomic():
                    comp = form.save()
                    if comp.equipo and comp.equipo.estado == 'DISPONIBLE' and (not comp.activo or comp.estado == 'REQUIERE_REEMPLAZO'):
                        comp.equipo.estado = 'DEFECTUOSO' if comp.estado == 'REQUIERE_REEMPLAZO' else 'EN_MANTENIMIENTO'
                        comp.equipo.save(update_fields=['estado'])
                        messages.warning(
                            request,
                            f'El equipo "{comp.equipo.nombre}" fue cambiado a "{comp.equipo.get_estado_display()}" '
                            f'porque el componente "{comp.nombre}" requiere reemplazo o está desactivado.'
                        )
                    registrar_auditoria(
                        usuario=request.user,
                        accion='MODIFICAR_COMPONENTE',
                        entidad='Componente',
                        entidad_id=comp.componente_id,
                        valor_previo=valor_prev,
                        valor_nuevo={'nombre': comp.nombre, 'estado': comp.estado, 'equipo_id': comp.equipo_id},
                        ip=request.META.get('REMOTE_ADDR'),
                    )
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
        with transaction.atomic():
            componente = get_object_or_404(
                Componente.objects.select_for_update().select_related('equipo'),
                pk=request.POST.get('componente_id'),
            )
            activo_prev = componente.activo
            componente.activo = not componente.activo
            componente.save(update_fields=['activo'])
            estado_txt = 'activado' if componente.activo else 'desactivado'
            if not componente.activo and componente.equipo and componente.equipo.estado == 'DISPONIBLE':
                componente.equipo.estado = 'EN_MANTENIMIENTO'
                componente.equipo.save(update_fields=['estado'])
                messages.warning(
                    request,
                    f'El equipo "{componente.equipo.nombre}" dejó de estar Disponible y pasó a En Mantenimiento '
                    f'porque tiene el componente "{componente.nombre}" desactivado.'
                )
            registrar_auditoria(
                usuario=request.user,
                accion='ACTIVAR_COMPONENTE' if componente.activo else 'DESACTIVAR_COMPONENTE',
                entidad='Componente',
                entidad_id=componente.componente_id,
                valor_previo={'activo': activo_prev},
                valor_nuevo={'activo': componente.activo, 'nombre': componente.nombre},
                ip=request.META.get('REMOTE_ADDR'),
            )
        messages.success(request, f'Componente "{componente.nombre}" {estado_txt} correctamente.')
    return redirect('componentes')
