import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import connection, transaction
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
                componentes_raw = request.POST.getlist('componentes')
                componentes_ids = sorted({int(cid) for cid in componentes_raw if str(cid).isdigit()})

                with transaction.atomic():
                    if componentes_ids:
                        comps_bloqueados = list(
                            Componente.objects.select_for_update()
                            .filter(pk__in=componentes_ids)
                        )
                        if len(comps_bloqueados) != len(componentes_ids):
                            raise ValueError("Uno o más periféricos seleccionados no existen.")
                        ocupados = [c.nombre for c in comps_bloqueados if c.equipo_id is not None]
                        if ocupados:
                            raise ValueError(
                                f'Los siguientes periféricos ya están asignados a otro equipo: {", ".join(ocupados)}.'
                            )
                        no_aptos = [
                            c.nombre for c in comps_bloqueados
                            if not c.activo or c.estado == 'REQUIERE_REEMPLAZO'
                        ]
                        if no_aptos and form.cleaned_data.get('estado') == 'DISPONIBLE':
                            raise ValueError(
                                f'No se puede registrar el equipo como Disponible con periféricos inactivos o que requieren reemplazo ({", ".join(no_aptos)}).'
                            )

                    equipo = form.save()
                    if componentes_ids:
                        Componente.objects.filter(pk__in=componentes_ids, equipo__isnull=True).update(equipo=equipo)

                    registrar_auditoria(
                        usuario=request.user,
                        accion='CREAR_EQUIPO',
                        entidad='Equipo',
                        entidad_id=equipo.equipo_id,
                        valor_nuevo={'nombre': equipo.nombre, 'estado': equipo.estado, 'tarifa': str(equipo.tarifa_por_hora)},
                        ip=request.META.get('REMOTE_ADDR'),
                    )
                messages.success(request, 'Equipo registrado correctamente.')
            except ValueError as e:
                messages.error(request, str(e))
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
                componentes_raw = request.POST.getlist('componentes')
                componentes_ids = sorted({int(cid) for cid in componentes_raw if str(cid).isdigit()})

                with transaction.atomic():
                    equipo_lock = get_object_or_404(Equipo.objects.select_for_update(), pk=equipo.equipo_id)
                    equipo = form.save(commit=False)

                    # Bloquear periféricos actuales y los solicitados en orden determinista
                    comps_actuales_y_nuevos = list(
                        Componente.objects.select_for_update()
                        .filter(Q(equipo_id=equipo_lock.equipo_id) | Q(pk__in=componentes_ids))
                        .order_by('componente_id')
                    )
                    mapa_comps = {c.componente_id: c for c in comps_actuales_y_nuevos}

                    ajenos = [
                        mapa_comps[cid].nombre
                        for cid in componentes_ids
                        if cid in mapa_comps and mapa_comps[cid].equipo_id not in (None, equipo_lock.equipo_id)
                    ]
                    if ajenos:
                        raise ValueError(
                            f'No se pueden asignar periféricos que ya pertenecen a otro equipo: {", ".join(ajenos)}.'
                        )

                    comps_seleccionados = [mapa_comps[cid] for cid in componentes_ids if cid in mapa_comps]

                    # Validar que si intenta dejar el equipo en DISPONIBLE no tenga componentes en reemplazo o desactivados
                    if equipo.estado == 'DISPONIBLE':
                        comps_reemplazo = [c for c in comps_seleccionados if c.estado == 'REQUIERE_REEMPLAZO']
                        comps_inactivos = [c for c in comps_seleccionados if not c.activo]
                        if comps_reemplazo or comps_inactivos:
                            motivos = []
                            if comps_reemplazo:
                                nombres_r = ", ".join([c.nombre for c in comps_reemplazo])
                                motivos.append(f"requieren reemplazo obligatorio ({nombres_r})")
                            if comps_inactivos:
                                nombres_i = ", ".join([c.nombre for c in comps_inactivos])
                                motivos.append(f"se encuentran desactivados ({nombres_i})")

                            raise ValueError(
                                f'No se puede colocar el equipo "{equipo.nombre}" como Disponible para renta porque tiene '
                                f'componentes que {" y ".join(motivos)}. Debe activarlos, reemplazarlos o desvincularlos primero.'
                            )

                    # Desvincular los que ya no están seleccionados para este equipo
                    equipo.componentes.exclude(pk__in=componentes_ids).update(equipo=None)
                    # Vincular únicamente los libres o propios seleccionados
                    if componentes_ids:
                        Componente.objects.filter(
                            Q(equipo__isnull=True) | Q(equipo_id=equipo_lock.equipo_id),
                            pk__in=componentes_ids,
                        ).update(equipo=equipo)

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
            except ValueError as e:
                messages.error(request, str(e))
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
        try:
            with transaction.atomic():
                equipo = get_object_or_404(Equipo.objects.select_for_update(), pk=request.POST.get('equipo_id'))
                comps_equipo = list(Componente.objects.select_for_update().filter(equipo=equipo))

                comps_reemplazo = [c for c in comps_equipo if c.estado == 'REQUIERE_REEMPLAZO']
                comps_inactivos = [c for c in comps_equipo if not c.activo]
                if comps_reemplazo or comps_inactivos:
                    motivos = []
                    if comps_reemplazo:
                        nombres_r = ", ".join([c.nombre for c in comps_reemplazo])
                        motivos.append(f"requieren reemplazo obligatorio ({nombres_r})")
                    if comps_inactivos:
                        nombres_i = ", ".join([c.nombre for c in comps_inactivos])
                        motivos.append(f"se encuentran desactivados ({nombres_i})")

                    messages.error(
                        request,
                        f'No se puede habilitar el equipo "{equipo.nombre}" porque los siguientes componentes '
                        f'{" y ".join(motivos)}. Debe reemplazarlos, activarlos o desvincularlos primero.'
                    )
                    return redirect('equipos')

                # Limpiar componentes en daños menores validados por el admin
                Componente.objects.filter(equipo=equipo, activo=True, estado='DANIOS_MENORES').update(estado='DISPONIBLE')

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
        except Exception:
            logger.exception('Error al habilitar el equipo')
            messages.error(request, 'Ocurrió un error al habilitar el equipo. Intenta nuevamente.')
    return redirect('equipos')


@login_required
@admin_required
def equipo_toggle(request):
    asegurar_columna_activo_equipo()
    if request.method == 'POST':
        try:
            with transaction.atomic():
                equipo = get_object_or_404(Equipo.objects.select_for_update(), pk=request.POST.get('equipo_id'))
                if equipo.activo and DetalleRenta.objects.filter(
                    equipo=equipo,
                    estado__in=('ACTIVA', 'TIEMPO_TERMINADO', 'PENDIENTE_REVISION'),
                ).exists():
                    messages.error(
                        request,
                        f'No se puede desactivar el equipo "{equipo.nombre}" mientras tenga una sesión de renta en curso o pendiente de revisión.'
                    )
                    return redirect('equipos')

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
