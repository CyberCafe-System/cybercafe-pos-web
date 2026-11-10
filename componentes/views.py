import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from equipos.models import Equipo
from rentas.models import DetalleRenta
from usuarios.decorators import admin_required
from usuarios.models import registrar_auditoria

from .forms import ComponenteForm
from .models import Componente

logger = logging.getLogger(__name__)
ESTADOS_RENTA_BLOQUEANTES = ('ACTIVA', 'TIEMPO_TERMINADO', 'PENDIENTE_REVISION')


def _equipo_tiene_renta_o_revision(equipo_id) -> bool:
    if not equipo_id:
        return False
    return DetalleRenta.objects.filter(
        equipo_id=equipo_id,
        estado__in=ESTADOS_RENTA_BLOQUEANTES,
    ).exists()


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
    equipos = list(Equipo.objects.all().order_by('nombre'))
    equipos_bloqueados_ids = set(
        DetalleRenta.objects.filter(estado__in=ESTADOS_RENTA_BLOQUEANTES).values_list('equipo_id', flat=True)
    )
    for comp in page_obj:
        comp.equipo_bloqueado = (comp.equipo_id in equipos_bloqueados_ids) if comp.equipo_id else False
    for eq in equipos:
        eq.bloqueado_operacion = (eq.equipo_id in equipos_bloqueados_ids)
    return render(request, 'componentes/componentes.html', {
        'componentes': page_obj,
        'page_obj': page_obj,
        'equipos': equipos,
        'equipos_bloqueados_ids': list(equipos_bloqueados_ids),
    })


@login_required
@admin_required
def componente_create(request):
    if request.method == 'POST':
        form = ComponenteForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    equipo_destino = form.cleaned_data.get('equipo')
                    if equipo_destino:
                        eq_lock = get_object_or_404(Equipo.objects.select_for_update(), pk=equipo_destino.equipo_id)
                        if _equipo_tiene_renta_o_revision(eq_lock.equipo_id):
                            raise ValueError(
                                f'No se puede asignar el componente al equipo "{eq_lock.nombre}" mientras tenga '
                                'una renta activa o se encuentre pendiente de revisión.'
                            )
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
            except ValueError as e:
                messages.error(request, str(e))
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
                    comp_lock = get_object_or_404(
                        Componente.objects.select_for_update().select_related('equipo'),
                        pk=componente.componente_id,
                    )
                    equipo_prev_id = comp_lock.equipo_id
                    estado_prev = comp_lock.estado
                    equipo_prev_nombre = comp_lock.equipo.nombre if comp_lock.equipo else f'#{equipo_prev_id}'

                    equipo_nuevo_obj = form.cleaned_data.get('equipo')
                    equipo_nuevo_id = equipo_nuevo_obj.equipo_id if equipo_nuevo_obj else None
                    estado_nuevo = form.cleaned_data.get('estado')

                    ids_eq = sorted({eid for eid in (equipo_prev_id, equipo_nuevo_id) if eid is not None})
                    equipos_lock = {
                        e.equipo_id: e
                        for e in Equipo.objects.select_for_update().filter(equipo_id__in=ids_eq).order_by('equipo_id')
                    }

                    # 1. Validar que el equipo actual no esté en renta activa ni pendiente de revisión
                    # si se intenta quitar el componente, cambiarlo de equipo o cambiar su estado.
                    if equipo_prev_id is not None and _equipo_tiene_renta_o_revision(equipo_prev_id):
                        eq_nom = equipos_lock[equipo_prev_id].nombre if equipo_prev_id in equipos_lock else equipo_prev_nombre
                        if equipo_nuevo_id != equipo_prev_id:
                            raise ValueError(
                                f'No se puede quitar ni cambiar de equipo el componente "{comp_lock.nombre}" '
                                f'porque el equipo "{eq_nom}" tiene una renta activa o se encuentra pendiente de revisión.'
                            )
                        if estado_nuevo != estado_prev:
                            raise ValueError(
                                f'No se puede cambiar el estado del componente "{comp_lock.nombre}" '
                                f'mientras el equipo "{eq_nom}" tenga una renta activa o esté pendiente de revisión.'
                            )

                    # 2. Validar que el equipo destino tampoco esté en renta activa ni pendiente de revisión
                    if equipo_nuevo_id is not None and equipo_nuevo_id != equipo_prev_id:
                        if _equipo_tiene_renta_o_revision(equipo_nuevo_id):
                            eq_dest_nom = (
                                equipos_lock[equipo_nuevo_id].nombre
                                if equipo_nuevo_id in equipos_lock
                                else getattr(equipo_nuevo_obj, 'nombre', f'#{equipo_nuevo_id}')
                            )
                            raise ValueError(
                                f'No se puede asignar el componente "{comp_lock.nombre}" al equipo "{eq_dest_nom}" '
                                'porque dicho equipo tiene una renta activa o se encuentra pendiente de revisión.'
                            )

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
            except ValueError as e:
                messages.error(request, str(e))
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
        try:
            with transaction.atomic():
                componente = get_object_or_404(
                    Componente.objects.select_for_update().select_related('equipo'),
                    pk=request.POST.get('componente_id'),
                )
                if componente.equipo_id is not None and _equipo_tiene_renta_o_revision(componente.equipo_id):
                    eq_nom = componente.equipo.nombre if componente.equipo else f'#{componente.equipo_id}'
                    messages.error(
                        request,
                        f'No se puede cambiar el estado del componente "{componente.nombre}" '
                        f'mientras el equipo "{eq_nom}" tenga una renta activa o esté pendiente de revisión.',
                    )
                    return redirect('componentes')

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
        except Exception:
            logger.exception('Error al cambiar estado del componente')
            messages.error(request, 'Ocurrió un error al actualizar el estado del componente.')
    return redirect('componentes')
