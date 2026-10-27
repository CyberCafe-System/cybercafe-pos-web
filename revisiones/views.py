from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from rentas.models import DetalleRenta
from usuarios.decorators import admin_required, asistente_o_admin_required
from .models import RevisionEquipo


@login_required
@admin_required
def revisiones_list(request):
    """
    Vista principal Master-Detail del Módulo de Revisiones.
    Carga el historial de revisiones y los equipos actualmente pendientes de inspección.
    """
    # 1. Obtener todas las revisiones realizadas con relaciones precargadas
    revisiones = list(
        RevisionEquipo.objects
        .select_related(
            'detalle_renta__equipo',
            'detalle_renta__renta__cliente',
            'detalle_renta__renta__usuario',
            'usuario',
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

    # 3. Métricas y contadores para los botones de filtro
    count_pendientes = len(detalles_pendientes)
    count_aprobadas = sum(1 for r in revisiones if r.inspeccion_pasada)
    count_reprobadas = sum(1 for r in revisiones if not r.inspeccion_pasada)
    count_total = len(revisiones)

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
        'count_componentes_con_novedad': count_componentes_con_novedad,
        'equipo_id_param': equipo_id_param,
        'detalle_id_param': detalle_id_param,
    })


@login_required
@asistente_o_admin_required
def crear_revision(request):
    """
    Registra la inspección física in situ pos-renta.
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
                detalle = get_object_or_404(
                    DetalleRenta.objects.select_for_update().select_related('equipo', 'renta'),
                    pk=detalle_id,
                )

                if detalle.estado != 'PENDIENTE_REVISION':
                    messages.warning(
                        request,
                        f'El equipo {detalle.equipo.nombre} ya no se encuentra en estado Pendiente de Revisión '
                        f'(estado actual: {detalle.get_estado_display()}).'
                    )
                    return redirect('revisiones')

                # Validar estado si fue reportado con daños
                estados_validos = ('DANIOS_MENORES', 'DEFECTUOSO', 'EN_MANTENIMIENTO')
                if estado_si_daniado not in estados_validos:
                    estado_si_daniado = 'DANIOS_MENORES'

                equipo = detalle.equipo
                if inspeccion_pasada:
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
                    for comp_nombre in lista_afectados:
                        c_obj = Componente.objects.filter(equipo=equipo, nombre__iexact=comp_nombre.split(' (')[0]).first()
                        if c_obj:
                            nuevo_estado = 'DANIOS_MENORES' if estado_si_daniado == 'DANIOS_MENORES' else 'REQUIERE_REEMPLAZO'
                            c_obj.estado = nuevo_estado
                            estado_label = c_obj.get_estado_display()
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

        except Exception as e:
            messages.error(request, f'No se pudo registrar la revisión: {str(e)}')

    return redirect('revisiones')


@login_required
@admin_required
def reiniciar_revision(request, revision_id):
    """
    Opción exclusiva para el Administrador:
    Anula una revisión errónea, elimina su registro y devuelve el equipo a estado PENDIENTE_REVISION.
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
                detalle = revision.detalle_renta
                equipo = detalle.equipo

                # Restaurar el detalle a PENDIENTE_REVISION
                detalle.estado = 'PENDIENTE_REVISION'
                detalle.save(update_fields=['estado'])

                # Eliminar el registro de auditoría erróneo
                revision.delete()

            messages.success(
                request,
                f'La revisión #{revision_id} fue anulada correctamente. '
                f'El equipo {equipo.nombre} ha vuelto a la bandeja de Pendientes de Revisión para ser evaluado nuevamente.'
            )
        except Exception as e:
            messages.error(request, f'Error al anular la revisión: {str(e)}')

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
                revision.observaciones = observaciones or None
                revision.inspeccion_pasada = inspeccion_pasada
                revision.save(update_fields=['observaciones', 'inspeccion_pasada'])

                # Si cambia el resultado de la inspección, actualizamos el estado del equipo
                equipo = revision.detalle_renta.equipo
                if inspeccion_pasada:
                    equipo.estado = 'DISPONIBLE'
                else:
                    estado_daniado = request.POST.get('estado_si_daniado', 'DANIOS_MENORES')
                    equipo.estado = estado_daniado
                equipo.save(update_fields=['estado'])

            messages.success(request, f'Revisión #{revision_id} actualizada correctamente por el Administrador.')
        except Exception as e:
            messages.error(request, f'No se pudo actualizar la revisión: {str(e)}')

    return redirect('revisiones')
