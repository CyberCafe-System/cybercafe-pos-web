import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from componentes.models import Componente
from rentas.models import DetalleRenta
from usuarios.decorators import admin_required
from usuarios.models import registrar_auditoria
from .forms import EquipoForm
from .models import Equipo

logger = logging.getLogger(__name__)
_EQUIPO_ACTIVO_VERIFICADO = False


def asegurar_columna_activo_equipo():
    """Garantiza que la columna activo exista en la tabla equipos en MySQL si aún no se ejecutó V014 en la API."""
    global _EQUIPO_ACTIVO_VERIFICADO
    if _EQUIPO_ACTIVO_VERIFICADO:
        return
    try:
        if connection.vendor == 'mysql':
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'equipos' AND COLUMN_NAME = 'activo'"
                )
                row = cursor.fetchone()
                if not row or row[0] == 0:
                    cursor.execute(
                        "ALTER TABLE `equipos` ADD COLUMN `activo` TINYINT(1) NOT NULL DEFAULT 1 AFTER `estado`;"
                    )
        _EQUIPO_ACTIVO_VERIFICADO = True
    except Exception:
        logger.debug("No se pudo verificar/agregar columna equipos.activo", exc_info=True)


@login_required
@admin_required
def equipo_list(request):
    asegurar_columna_activo_equipo()
    equipos_qs = Equipo.objects.prefetch_related('componentes').all().order_by('equipo_id')
    paginator = Paginator(equipos_qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    # En edición mostramos los componentes libres operativos y también los ya asignados a algún equipo
    # (incluyendo si alguno asignado está desactivado o requiere reemplazo para poder verlo/desvincularlo)
    componentes = Componente.objects.select_related('equipo').filter(
        Q(equipo__isnull=False) | (Q(activo=True) & ~Q(estado='REQUIERE_REEMPLAZO'))
    ).order_by('tipo', 'nombre')
    componentes_libres = [
        c for c in componentes
        if c.equipo_id is None and c.activo and c.estado != 'REQUIERE_REEMPLAZO'
    ]
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
                equipo = form.save(commit=False)
                componentes_ids = request.POST.getlist('componentes')
                # Desvincular los que ya no están seleccionados para este equipo
                equipo.componentes.exclude(pk__in=componentes_ids).update(equipo=None)
                # Vincular los seleccionados
                if componentes_ids:
                    Componente.objects.filter(pk__in=componentes_ids).update(equipo=equipo)

                # Validar que si intenta dejar el equipo en DISPONIBLE no tenga componentes en reemplazo o desactivados
                if equipo.estado == 'DISPONIBLE':
                    comps_reemplazo = equipo.componentes.filter(estado='REQUIERE_REEMPLAZO')
                    comps_inactivos = equipo.componentes.filter(activo=False)
                    if comps_reemplazo.exists() or comps_inactivos.exists():
                        motivos = []
                        if comps_reemplazo.exists():
                            nombres_r = ", ".join([c.nombre for c in comps_reemplazo])
                            motivos.append(f"requieren reemplazo obligatorio ({nombres_r})")
                        if comps_inactivos.exists():
                            nombres_i = ", ".join([c.nombre for c in comps_inactivos])
                            motivos.append(f"se encuentran desactivados ({nombres_i})")

                        equipo.estado = estado_prev if estado_prev != 'DISPONIBLE' else 'EN_MANTENIMIENTO'
                        equipo.save()
                        messages.error(
                            request,
                            f'No se puede colocar el equipo "{equipo.nombre}" como Disponible para renta porque tiene '
                            f'componentes que {" y ".join(motivos)}. Debe activarlos, reemplazarlos o desvincularlos primero.'
                        )
                        return redirect('equipos')

                equipo.save()

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
    Bloquea la habilitación si algún componente asignado tiene REQUIERE_REEMPLAZO o está desactivado.
    """
    if request.method == 'POST':
        equipo = get_object_or_404(Equipo, pk=request.POST.get('equipo_id'))

        # Verificar si hay componentes que requieren reemplazo o están desactivados
        comps_reemplazo = equipo.componentes.filter(estado='REQUIERE_REEMPLAZO')
        comps_inactivos = equipo.componentes.filter(activo=False)
        if comps_reemplazo.exists() or comps_inactivos.exists():
            motivos = []
            if comps_reemplazo.exists():
                nombres_r = ", ".join([c.nombre for c in comps_reemplazo])
                motivos.append(f"requieren reemplazo obligatorio ({nombres_r})")
            if comps_inactivos.exists():
                nombres_i = ", ".join([c.nombre for c in comps_inactivos])
                motivos.append(f"se encuentran desactivados ({nombres_i})")

            messages.error(
                request,
                f'No se puede habilitar el equipo "{equipo.nombre}" porque los siguientes componentes '
                f'{" y ".join(motivos)}. Debe reemplazarlos, activarlos o desvincularlos primero.'
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
def equipo_toggle(request):
    asegurar_columna_activo_equipo()
    if request.method == 'POST':
        equipo = get_object_or_404(Equipo, pk=request.POST.get('equipo_id'))
        if equipo.activo and DetalleRenta.objects.filter(
            equipo=equipo,
            estado__in=('ACTIVA', 'TIEMPO_TERMINADO', 'PENDIENTE_REVISION'),
        ).exists():
            messages.error(
                request,
                f'No se puede desactivar el equipo "{equipo.nombre}" mientras tenga una sesión de renta en curso o pendiente de revisión.'
            )
            return redirect('equipos')

        try:
            estado_prev = equipo.activo
            equipo.activo = not equipo.activo
            equipo.save(update_fields=['activo'])
            accion_audit = 'ACTIVAR_EQUIPO' if equipo.activo else 'DESACTIVAR_EQUIPO'
            estado_txt = 'activado' if equipo.activo else 'desactivado'
            registrar_auditoria(
                usuario=request.user,
                accion=accion_audit,
                entidad='Equipo',
                entidad_id=equipo.equipo_id,
                valor_previo={'activo': estado_prev},
                valor_nuevo={'activo': equipo.activo, 'nombre': equipo.nombre},
                ip=request.META.get('REMOTE_ADDR'),
            )
            messages.success(request, f'Equipo "{equipo.nombre}" {estado_txt} correctamente.')
        except Exception:
            logger.exception('Error al cambiar el estado activo del equipo')
            messages.error(request, 'Ocurrió un error al actualizar el estado del equipo. Intenta nuevamente.')
    return redirect('equipos')
