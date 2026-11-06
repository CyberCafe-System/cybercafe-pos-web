import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render

from componentes.models import Componente
from rentas.models import DetalleRenta
from usuarios.decorators import admin_required
from usuarios.models import registrar_auditoria
from .forms import EquipoForm
from .models import Equipo

logger = logging.getLogger(__name__)


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
                
                registrar_auditoria(
                    usuario=request.user,
                    accion='CREAR_EQUIPO',
                    entidad='Equipo',
                    entidad_id=equipo.equipo_id,
                    valor_nuevo={'nombre': equipo.nombre, 'estado': equipo.estado, 'tarifa': str(equipo.tarifa_por_hora)},
                    ip=request.META.get('REMOTE_ADDR'),
                )
                messages.success(request, 'Equipo registrado correctamente.')
            except Exception:
                logger.exception('Error al guardar el equipo')
                messages.error(request, 'Ocurrió un error al guardar el equipo. Intenta nuevamente.')
        else:
            for error in form.errors.values():
                messages.error(request, error.as_text().lstrip('* '))
    return redirect('equipos')


@login_required
@admin_required
def equipo_edit(request):
    if request.method == 'POST':
        equipo = get_object_or_404(Equipo, pk=request.POST.get('equipo_id'))
        estado_prev = equipo.estado
        tarifa_prev = str(equipo.tarifa_por_hora)

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

                registrar_auditoria(
                    usuario=request.user,
                    accion='MODIFICAR_EQUIPO',
                    entidad='Equipo',
                    entidad_id=equipo.equipo_id,
                    valor_previo={'estado': estado_prev, 'tarifa': tarifa_prev},
                    valor_nuevo={'estado': equipo.estado, 'tarifa': str(equipo.tarifa_por_hora)},
                    ip=request.META.get('REMOTE_ADDR'),
                )
                messages.success(request, 'Equipo actualizado correctamente.')
            except Exception:
                logger.exception('Error al actualizar el equipo')
                messages.error(request, 'Ocurrió un error al actualizar el equipo. Intenta nuevamente.')
        else:
            for error in form.errors.values():
                messages.error(request, error.as_text().lstrip('* '))
    return redirect('equipos')


@login_required
@admin_required
def equipo_habilitar(request):
    """
    Permite al Administrador inspeccionar físicamente y habilitar un equipo
    en DEFECTUOSO o DANIOS_MENORES para dejarlo DISPONIBLE.
    Bloquea la habilitación si algún componente activo asignado tiene REQUIERE_REEMPLAZO.
    """
    if request.method == 'POST':
        equipo = get_object_or_404(Equipo, pk=request.POST.get('equipo_id'))

        # Verificar si hay componentes que requieren reemplazo
        comps_reemplazo = equipo.componentes.filter(activo=True, estado='REQUIERE_REEMPLAZO')
        if comps_reemplazo.exists():
            nombres = ", ".join([c.nombre for c in comps_reemplazo])
            messages.error(
                request,
                f'No se puede habilitar el equipo "{equipo.nombre}" porque los siguientes componentes '
                f'requieren reemplazo obligatorio: {nombres}. Debe reemplazarlos o desvincularlos primero.'
            )
            return redirect('equipos')

        # Limpiar componentes en daños menores validados por el admin
        comps_danios = equipo.componentes.filter(activo=True, estado='DANIOS_MENORES')
        if comps_danios.exists():
            comps_danios.update(estado='DISPONIBLE')

        estado_anterior = equipo.estado
        equipo.estado = 'DISPONIBLE'
        equipo.save(update_fields=['estado'])

        registrar_auditoria(
            usuario=request.user,
            accion='HABILITAR_EQUIPO',
            entidad='Equipo',
            entidad_id=equipo.equipo_id,
            valor_previo={'estado': estado_anterior},
            valor_nuevo={'estado': 'DISPONIBLE'},
            ip=request.META.get('REMOTE_ADDR'),
        )
        messages.success(
            request,
            f'El equipo "{equipo.nombre}" ha sido inspeccionado y habilitado exitosamente para renta.'
        )
    return redirect('equipos')


@login_required
@admin_required
def equipo_delete(request):
    if request.method == 'POST':
        equipo = get_object_or_404(Equipo, pk=request.POST.get('equipo_id'))
        if DetalleRenta.objects.filter(equipo=equipo).exists():
            messages.error(
                request,
                f'No se puede eliminar "{equipo.nombre}" porque tiene rentas o historial asociado. '
                'Si está fuera de servicio, cámbialo a estado En Mantenimiento o Defectuoso.'
            )
            return redirect('equipos')
        try:
            nombre = equipo.nombre
            equipo.componentes.update(equipo=None)
            equipo.delete()
            registrar_auditoria(
                usuario=request.user,
                accion='ELIMINAR_EQUIPO',
                entidad='Equipo',
                entidad_id=equipo.equipo_id,
                valor_previo={'nombre': nombre},
                ip=request.META.get('REMOTE_ADDR'),
            )
            messages.success(request, f'Equipo "{nombre}" eliminado correctamente.')
        except (ProtectedError, IntegrityError):
            messages.error(request, 'No se puede eliminar el equipo porque tiene registros vinculados.')
        except Exception:
            logger.exception('Error al eliminar el equipo')
            messages.error(request, 'Ocurrió un error al eliminar el equipo. Intenta nuevamente.')
    return redirect('equipos')
