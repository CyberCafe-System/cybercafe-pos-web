import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from equipos.models import Equipo
from rentas.models import DetalleRenta
from usuarios.decorators import admin_required, asistente_o_admin_required
from usuarios.models import registrar_auditoria
from .models import RevisionComponente, RevisionEquipo

logger = logging.getLogger(__name__)


@login_required
@admin_required
def revisiones_list(request):
    """
    Vista principal Master-Detail del Módulo de Revisiones.
    Carga el historial de revisiones y los equipos actualmente pendientes de inspección.
    """
    # 1. Obtener todas las revisiones realizadas con relaciones precargadas (incluyendo usuario__rol para evitar N+1)
    revisiones = list(
        RevisionEquipo.objects
        .select_related(
            'detalle_renta__equipo',
            'detalle_renta__renta__cliente',
            'detalle_renta__renta__usuario',
            'usuario__rol',
        )
        .prefetch_related('detalle_renta__equipo__componentes')
        .order_by('-fecha_revision')
    )

    # 2. Obtener detalles de renta en espera de inspección física
    detalles_pendientes = list(
        DetalleRenta.objects
        .filter(estado='PENDIENTE_REVISION')
        .select_related(
            'equipo',
            'renta__cliente',
            'renta__usuario',
        )
        .prefetch_related('equipo__componentes')
        .order_by('hora_fin')
    )

    # 3. Métricas y contadores para los botones de filtro y tarjetas resumen
    count_pendientes = len(detalles_pendientes)
    count_aprobadas = sum(1 for r in revisiones if r.inspeccion_pasada)
    count_reprobadas = sum(1 for r in revisiones if not r.inspeccion_pasada)
    count_total = len(revisiones)

    # Total de equipos disponibles y total registrados
    count_equipos_disponibles = Equipo.objects.filter(estado='DISPONIBLE').count()
    count_equipos_total = Equipo.objects.count()

    # Daños reportados en la semana en curso (lunes 00:00 al presente)
    ahora = timezone.localtime(timezone.now())
    inicio_semana = ahora - timezone.timedelta(days=ahora.weekday())
    inicio_semana = inicio_semana.replace(hour=0, minute=0, second=0, microsecond=0)
    count_danios_semana = RevisionEquipo.objects.filter(
        inspeccion_pasada=False,
        fecha_revision__gte=inicio_semana
    ).count()

    # Determinar si cada revisión puede revocarse
    # (solo si el equipo no tiene rentas posteriores ni está actualmente en uso)
    ultimos_detalles_por_equipo = dict(
        DetalleRenta.objects.values('equipo_id').annotate(max_id=models.Max('detalle_renta_id')).values_list('equipo_id', 'max_id')
    )
    equipos_con_renta_activa = set(
        DetalleRenta.objects.filter(estado__in=('ACTIVA', 'TIEMPO_TERMINADO', 'PENDIENTE_REVISION')).values_list('equipo_id', flat=True)
    )

    for r in revisiones:
        eq_id = r.detalle_renta.equipo_id
        es_ultimo = (ultimos_detalles_por_equipo.get(eq_id) == r.detalle_renta_id)
        en_uso = (eq_id in equipos_con_renta_activa)
        r.puede_revocarse = (es_ultimo and not en_uso)

    # 4. Obtener componentes para el apartado de Revisiones de Componentes
    from componentes.models import Componente
    componentes_revisiones = list(
        Componente.objects
        .select_related('equipo')
        .filter(activo=True)
        .order_by('equipo__nombre', 'tipo')
    )

    for c in componentes_revisiones:
        c.ultima_rev_id = None
        c.ultima_fecha = None
        c.ultima_descripcion = None
        if c.observaciones:
            bloques = [b.strip() for b in c.observaciones.split('--------------------------------------------------') if b.strip()]
            primer_bloque = bloques[0] if bloques else c.observaciones

            if '[REVISI' in primer_bloque:
                lineas = primer_bloque.split('\n')
                cabecera = lineas[0].replace('[', '').replace(']', '')
                for part in cabecera.split('|'):
                    p = part.strip()
                    if 'REVISI' in p:
                        c.ultima_rev_id = p.split(':')[-1].strip()
                    elif 'FECHA' in p:
                        c.ultima_fecha = p.split('FECHA:')[-1].strip()
                if len(lineas) > 1:
                    c.ultima_descripcion = lineas[1].replace('Descripción:', '').replace('Daño / Falla:', '').strip()
                else:
                    c.ultima_descripcion = primer_bloque
            elif '---' in primer_bloque:
                # Soporte para registros con formato separado por guiones
                partes = [p.strip() for p in primer_bloque.split('---') if p.strip()]
                if len(partes) >= 1:
                    c.ultima_descripcion = partes[0]
                if len(partes) >= 3:
                    c.ultima_rev_id = f"#{partes[2]}"
                if len(partes) >= 2:
                    c.ultima_fecha = partes[1]
            else:
                c.ultima_descripcion = primer_bloque

    count_componentes_con_novedad = sum(1 for c in componentes_revisiones if c.observaciones or c.estado != 'DISPONIBLE')

    # 5. Equipo pre-seleccionado por parámetro GET (ej. ?equipo_id=X o ?detalle_id=Y)
    equipo_id_param = request.GET.get('equipo_id')
    detalle_id_param = request.GET.get('detalle_id')

    return render(request, 'revisiones/revisiones.html', {
        'revisiones': revisiones,
        'detalles_pendientes': detalles_pendientes,
        'componentes_revisiones': componentes_revisiones,
        'count_pendientes': count_pendientes,
        'count_aprobadas': count_aprobadas,
        'count_reprobadas': count_reprobadas,
        'count_total': count_total,
        'count_equipos_disponibles': count_equipos_disponibles,
        'count_equipos_total': count_equipos_total,
        'count_danios_semana': count_danios_semana,
        'count_componentes_con_novedad': count_componentes_con_novedad,
        'equipo_id_param': equipo_id_param,
        'detalle_id_param': detalle_id_param,
    })


@login_required
@asistente_o_admin_required
def crear_revision(request):
    """
    Registra la inspección técnica pos-renta.
    Regla estricta: Si se reporta daño o novedad, la descripción es obligatoria.
    Actualiza atómicamente el equipo, la sesión de renta y crea el registro de revisión.
    """
    if request.method == 'POST':
        detalle_id = request.POST.get('detalle_renta_id')
        inspeccion_pasada_raw = request.POST.get('inspeccion_pasada', 'true')
        inspeccion_pasada = (inspeccion_pasada_raw.lower() in ('true', '1', 'on', 'si'))
        estado_si_daniado = request.POST.get('estado_si_daniado', 'DANIOS_MENORES')
        observaciones = (request.POST.get('observaciones') or '').strip()

        # Componentes afectados reportados
        componentes_afectados_raw = request.POST.getlist('componentes_afectados')
        otro_componente = (request.POST.get('otro_componente') or '').strip()

        # Validación de obligatoriedad de descripción cuando se reportan daños
        if not inspeccion_pasada and not observaciones:
            messages.error(
                request,
                'Es obligatorio ingresar una descripción detallada de la anomalía o daño detectado al reprobar un equipo.'
            )
            return redirect('revisiones')

        try:
            with transaction.atomic():
                detalle_prev = get_object_or_404(DetalleRenta, pk=detalle_id)
                # Orden estricto de locks: 1. Equipo -> 2. DetalleRenta
                equipo = get_object_or_404(Equipo.objects.select_for_update(), pk=detalle_prev.equipo_id)
                detalle = get_object_or_404(
                    DetalleRenta.objects.select_for_update().select_related('renta'),
                    pk=detalle_id,
                )

                if detalle.estado not in ('PENDIENTE_REVISION', 'TIEMPO_TERMINADO'):
                    messages.warning(
                        request,
                        f'El equipo {equipo.nombre} ya no se encuentra en estado Pendiente de Revisión '
                        f'(estado actual: {detalle.get_estado_display()}).'
                    )
                    return redirect('revisiones')

                # Validar estado si fue reportado con daños
                estados_validos = ('DANIOS_MENORES', 'DEFECTUOSO', 'EN_MANTENIMIENTO')
                if estado_si_daniado not in estados_validos:
                    estado_si_daniado = 'DANIOS_MENORES'

                # equipo ya se encuentra bloqueado con select_for_update
                if inspeccion_pasada:
                    # Verificar que no existan componentes en DANIOS_MENORES, REQUIERE_REEMPLAZO o desactivados
                    from componentes.models import Componente
                    tiene_comps_bloqueantes = Componente.objects.filter(
                        equipo=equipo,
                    ).filter(
                        models.Q(activo=False) | models.Q(estado__in=('DANIOS_MENORES', 'REQUIERE_REEMPLAZO'))
                    ).exists()
                    if not tiene_comps_bloqueantes:
                        equipo.estado = 'DISPONIBLE'
                else:
                    equipo.estado = estado_si_daniado
                equipo.save(update_fields=['estado'])

                # Marcar el detalle de la sesión como finalizado tras completarse la revisión
                detalle.estado = 'FINALIZADA'
                if not detalle.hora_fin:
                    detalle.hora_fin = timezone.now()
                detalle.save(update_fields=['estado', 'hora_fin'])

                # Procesar lista de componentes afectados si hubo daños
                observaciones_final = observaciones
                if not inspeccion_pasada:
                    lista_afectados = [c.strip() for c in componentes_afectados_raw if c.strip()]
                    if otro_componente:
                        lista_afectados.append(otro_componente)

                    if lista_afectados:
                        prefijo_afectados = f"[Componentes Afectados]: {', '.join(lista_afectados)}"
                        observaciones_final = f"{prefijo_afectados}\n\n[Diagnóstico]: {observaciones}"

                # 1. Registrar primero la auditoría de revisión para obtener su ID
                revision = RevisionEquipo.objects.create(
                    detalle_renta=detalle,
                    usuario=request.user,
                    inspeccion_pasada=inspeccion_pasada,
                    observaciones=observaciones_final or None,
                    fecha_revision=timezone.now(),
                )

                # 2. Si no pasó la inspección, registrar historial acumulativo en cada componente afectado
                if not inspeccion_pasada and lista_afectados:
                    from componentes.models import Componente
                    fecha_str = timezone.localtime(revision.fecha_revision).strftime('%d/%m/%Y %I:%M %p')
                    componentes_equipo_qs = Componente.objects.select_for_update().filter(equipo=equipo)
                    for comp_raw in lista_afectados:
                        c_obj = None
                        if comp_raw.isdigit():
                            c_obj = componentes_equipo_qs.filter(pk=int(comp_raw)).first()
                        if c_obj is None:
                            # Soportar formato "Nombre (S/N: ...)" sin truncar nombres que contengan paréntesis propios
                            nombre_limpio = comp_raw.split(' (S/N:')[0].strip()
                            c_obj = (
                                componentes_equipo_qs.filter(nombre__iexact=comp_raw).first()
                                or componentes_equipo_qs.filter(nombre__iexact=nombre_limpio).first()
                                or componentes_equipo_qs.filter(nombre__iexact=comp_raw.split(' (')[0].strip()).first()
                            )
                        if c_obj:
                            estado_previo_comp = c_obj.estado
                            nuevo_estado = 'DANIOS_MENORES' if estado_si_daniado == 'DANIOS_MENORES' else 'REQUIERE_REEMPLAZO'
                            c_obj.estado = nuevo_estado
                            bloque_revision = (
                                f"[REVISIÓN: #{revision.revision_equipo_id} | FECHA: {fecha_str}]\n"
                                f"Descripción: {observaciones or 'Novedad reportada en inspección técnica'}\n"
                                f"--------------------------------------------------"
                            )
                            if c_obj.observaciones:
                                c_obj.observaciones = f"{bloque_revision}\n{c_obj.observaciones}"
                            else:
                                c_obj.observaciones = bloque_revision
                            c_obj.save(update_fields=['estado', 'observaciones'])
                            RevisionComponente.objects.create(
                                revision_equipo=revision,
                                componente=c_obj,
                                estado_previo=estado_previo_comp,
                                estado_nuevo=nuevo_estado,
                                descripcion=observaciones or 'Novedad reportada en inspección técnica',
                            )

                registrar_auditoria(
                    usuario=request.user,
                    accion='CREAR_REVISION',
                    entidad='RevisionEquipo',
                    entidad_id=revision.revision_equipo_id,
                    valor_nuevo={
                        'nombre': equipo.nombre,
                        'inspeccion_pasada': inspeccion_pasada,
                        'estado': equipo.estado,
                    },
                    ip=request.META.get('REMOTE_ADDR'),
                )

            if inspeccion_pasada:
                messages.success(
                    request,
                    f'Inspección de {equipo.nombre} aprobada exitosamente. El equipo vuelve a estar DISPONIBLE para rentas.'
                )
            else:
                messages.warning(
                    request,
                    f'Inspección de {equipo.nombre} registrada con NOVEDADES ({equipo.get_estado_display()}). '
                    f'El equipo queda fuera de servicio para mantenimiento.'
                )

        except ValueError as e:
            messages.error(request, str(e))
        except Exception:
            logger.exception('Error al registrar la revisión:')
            messages.error(request, 'No se pudo registrar la revisión técnica. Verifica los datos e inténtalo de nuevo.')

    return redirect('revisiones')


@login_required
@admin_required
def reiniciar_revision(request, revision_id):
    """
    Opción exclusiva para el Administrador:
    Revoca una revisión errónea, elimina su registro y devuelve el equipo a estado PENDIENTE_REVISION
    para que el técnico realice la inspección física nuevamente desde la app móvil.
    Seguridad: Valida que el equipo no haya sido rentado nuevamente de forma posterior ni esté en uso.
    """
    if request.method == 'POST':
        try:
            with transaction.atomic():
                revision = get_object_or_404(
                    RevisionEquipo.objects.select_for_update().select_related(
                        'detalle_renta__equipo',
                        'detalle_renta__renta',
                    ),
                    pk=revision_id,
                )
                equipo = get_object_or_404(Equipo.objects.select_for_update(), pk=revision.detalle_renta.equipo_id)
                detalle = get_object_or_404(DetalleRenta.objects.select_for_update(), pk=revision.detalle_renta_id)

                # 1. Validación: Verificar que el equipo NO haya sido rentado de nuevo posteriormente
                renta_posterior = DetalleRenta.objects.filter(
                    equipo=equipo,
                    detalle_renta_id__gt=detalle.detalle_renta_id
                ).exists()

                renta_activa = DetalleRenta.objects.filter(
                    equipo=equipo,
                    estado__in=('ACTIVA', 'TIEMPO_TERMINADO', 'PENDIENTE_REVISION')
                ).exclude(detalle_renta_id=detalle.detalle_renta_id).exists()

                if renta_posterior or renta_activa:
                    messages.error(
                        request,
                        f'No es posible revocar la revisión #{revision_id}: El equipo {equipo.nombre} ya ha sido rentado posteriormente o se encuentra en uso actualmente.'
                    )
                    return redirect('revisiones')

                # 2. Restaurar el detalle de la sesión a PENDIENTE_REVISION
                detalle.estado = 'PENDIENTE_REVISION'
                detalle.save(update_fields=['estado'])

                # 3. Restaurar estado_previo y limpiar reporte inyectado en periféricos por esta revisión
                from componentes.models import Componente
                mapa_estados_previos = {
                    rc.componente_id: rc.estado_previo
                    for rc in RevisionComponente.objects.filter(revision_equipo=revision)
                }
                prefijo_rev = f"[REVISIÓN: #{revision.revision_equipo_id}"
                componentes_equipo = Componente.objects.select_for_update().filter(equipo=equipo)
                for comp in componentes_equipo:
                    modificado = False
                    if comp.observaciones and prefijo_rev in comp.observaciones:
                        bloques = [b.strip() for b in comp.observaciones.split('--------------------------------------------------') if b.strip()]
                        bloques_filtrados = [b for b in bloques if prefijo_rev not in b]
                        if bloques_filtrados:
                            comp.observaciones = "\n--------------------------------------------------\n".join(bloques_filtrados) + "\n--------------------------------------------------"
                            comp.estado = mapa_estados_previos.get(comp.componente_id, comp.estado)
                        else:
                            comp.observaciones = None
                            comp.estado = mapa_estados_previos.get(comp.componente_id, 'DISPONIBLE')
                        modificado = True
                    elif comp.componente_id in mapa_estados_previos:
                        comp.estado = mapa_estados_previos[comp.componente_id]
                        modificado = True

                    if modificado:
                        comp.save(update_fields=['observaciones', 'estado'])

                RevisionComponente.objects.filter(revision_equipo=revision).delete()

                # 4. Registrar auditoría y eliminar el registro de revisión
                registrar_auditoria(
                    usuario=request.user,
                    accion='REINICIAR_REVISION',
                    entidad='RevisionEquipo',
                    entidad_id=revision_id,
                    valor_previo={
                        'nombre': equipo.nombre,
                        'inspeccion_pasada': revision.inspeccion_pasada,
                        'observaciones': revision.observaciones,
                    },
                    valor_nuevo={'estado': 'PENDIENTE_REVISION'},
                    ip=request.META.get('REMOTE_ADDR'),
                )
                revision.delete()

            messages.success(
                request,
                f'La revisión #{revision_id} fue revocada correctamente. '
                f'El equipo {equipo.nombre} ha vuelto a la lista de pendientes para que se realice la inspección nuevamente desde la app móvil.'
            )
        except ValueError as e:
            messages.error(request, str(e))
        except Exception:
            logger.exception('Error al revocar la revisión:')
            messages.error(request, 'No se pudo revocar la revisión técnica. Inténtalo de nuevo.')

    return redirect('revisiones')


@login_required
@admin_required
def editar_revision(request, revision_id):
    """
    Opción exclusiva para el Administrador:
    Permite editar las observaciones, diagnóstico y resultado de una revisión existente.
    """
    if request.method == 'POST':
        revision = get_object_or_404(RevisionEquipo, pk=revision_id)
        observaciones = (request.POST.get('observaciones') or '').strip()
        inspeccion_pasada_raw = request.POST.get('inspeccion_pasada', 'true')
        inspeccion_pasada = (inspeccion_pasada_raw.lower() in ('true', '1', 'on', 'si'))

        try:
            with transaction.atomic():
                pasada_prev = getattr(revision, 'inspeccion_pasada', None)
                obs_prev = getattr(revision, 'observaciones', None)

                revision.observaciones = observaciones or None
                revision.inspeccion_pasada = inspeccion_pasada
                revision.save(update_fields=['observaciones', 'inspeccion_pasada'])

                # Si cambia el resultado de la inspección, actualizamos el estado del equipo y sus componentes
                equipo = get_object_or_404(Equipo.objects.select_for_update(), pk=revision.detalle_renta.equipo_id)
                estado_eq_prev = getattr(equipo, 'estado', None)

                if inspeccion_pasada:
                    # Si originalmente había reprobado componentes en esta revisión, restaurarlos a su estado_previo
                    if pasada_prev is False:
                        from componentes.models import Componente
                        rcs = list(RevisionComponente.objects.filter(revision_equipo=revision))
                        if rcs:
                            mapa_prev = {rc.componente_id: rc.estado_previo for rc in rcs}
                            prefijo_rev = f"[REVISIÓN: #{revision.revision_equipo_id}"
                            for comp in Componente.objects.select_for_update().filter(pk__in=mapa_prev.keys()):
                                if comp.observaciones and prefijo_rev in comp.observaciones:
                                    bloques = [b.strip() for b in comp.observaciones.split('--------------------------------------------------') if b.strip()]
                                    bloques_filtrados = [b for b in bloques if prefijo_rev not in b]
                                    comp.observaciones = (
                                        "\n--------------------------------------------------\n".join(bloques_filtrados) + "\n--------------------------------------------------"
                                        if bloques_filtrados else None
                                    )
                                comp.estado = mapa_prev.get(comp.componente_id) or 'DISPONIBLE'
                                comp.save(update_fields=['observaciones', 'estado'])
                            RevisionComponente.objects.filter(revision_equipo=revision).delete()

                        tiene_bloqueo = Componente.objects.filter(equipo=equipo).filter(
                            models.Q(activo=False) | models.Q(estado='REQUIERE_REEMPLAZO')
                        ).exists()
                        if tiene_bloqueo:
                            raise ValueError(
                                f'No se puede marcar el equipo "{equipo.nombre}" como Disponible porque tiene '
                                'periféricos inactivos o que requieren reemplazo.'
                            )
                    equipo.estado = 'DISPONIBLE'
                else:
                    estado_daniado = request.POST.get('estado_si_daniado', 'DANIOS_MENORES')
                    if estado_daniado not in ('DANIOS_MENORES', 'DEFECTUOSO', 'EN_MANTENIMIENTO'):
                        estado_daniado = 'DANIOS_MENORES'
                    equipo.estado = estado_daniado
                equipo.save(update_fields=['estado'])

                registrar_auditoria(
                    usuario=request.user,
                    accion='MODIFICAR_REVISION',
                    entidad='RevisionEquipo',
                    entidad_id=revision_id,
                    valor_previo={'inspeccion_pasada': pasada_prev, 'estado': estado_eq_prev, 'observaciones': obs_prev},
                    valor_nuevo={'inspeccion_pasada': inspeccion_pasada, 'estado': equipo.estado, 'observaciones': revision.observaciones},
                    ip=request.META.get('REMOTE_ADDR'),
                )

            messages.success(request, f'Revisión #{revision_id} actualizada correctamente por el Administrador.')
        except ValueError as e:
            messages.error(request, str(e))
        except Exception:
            logger.exception('Error al actualizar la revisión:')
            messages.error(request, 'No se pudo actualizar la revisión técnica. Inténtalo de nuevo.')

    return redirect('revisiones')
