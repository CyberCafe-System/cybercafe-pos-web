import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from clientes.models import Cliente
from config.context_processors import obtener_rentas_activas_payload
from equipos.models import Equipo
from usuarios.decorators import cajero_o_admin_required
from usuarios.models import Usuario

from .models import DetalleRenta, ExtensionRenta, Notificacion, Renta
from .ticket import generar_factura_renta_pdf

ESTADOS_BLOQUEANTES = ('ACTIVA', 'TIEMPO_TERMINADO', 'PENDIENTE_REVISION')
EFECTIVO_MAXIMO = getattr(settings, 'EFECTIVO_MAXIMO', Decimal('100.00'))


def verificar_vencimiento_rentas_locales():
    """
    Revisa las rentas en curso y si ya alcanzaron o superaron su hora de vencimiento,
    las transiciona automáticamente a TIEMPO_TERMINADO y notifica a los asistentes.
    """
    ahora = timezone.now()
    rentas_a_vencer = (
        DetalleRenta.objects.filter(estado='ACTIVA', hora_vencimiento__lte=ahora)
        .select_related('equipo', 'renta__cliente')
    )
    if not rentas_a_vencer.exists():
        return

    destinatarios = list(Usuario.objects.filter(activo=True, rol_id__in=[1, 3]))

    for detalle in rentas_a_vencer:
        detalle.estado = 'TIEMPO_TERMINADO'
        detalle.save(update_fields=['estado'])

        eq_nombre = detalle.equipo.nombre if detalle.equipo else f"Equipo #{detalle.equipo_id}"
        cl_nombre = f"{detalle.renta.cliente.nombre} {detalle.renta.cliente.apellido}" if (detalle.renta and detalle.renta.cliente) else "Cliente"

        # Registrar notificaciones para cada asistente y admin activo
        for dest in destinatarios:
            Notificacion.objects.get_or_create(
                usuario_destino=dest,
                tipo='TIEMPO_TERMINADO',
                detalle_renta=detalle,
                defaults={
                    'titulo': f'Tiempo terminado: {eq_nombre}',
                    'mensaje': f'La sesión de {cl_nombre} en {eq_nombre} ha terminado su tiempo contratado.',
                    'creada_en': ahora,
                }
            )


def crear_notificaciones_revision(detalle):
    """Crea notificaciones para asistentes y administradores cuando un equipo entra en revisión."""
    ahora = timezone.now()
    destinatarios = list(Usuario.objects.filter(activo=True, rol_id__in=[1, 3]))
    eq_nombre = detalle.equipo.nombre if detalle.equipo else f"Equipo #{detalle.equipo_id}"
    for dest in destinatarios:
        Notificacion.objects.get_or_create(
            usuario_destino=dest,
            tipo='PENDIENTE_REVISION',
            detalle_renta=detalle,
            defaults={
                'titulo': f'Equipo a revisión: {eq_nombre}',
                'mensaje': f'{eq_nombre} ha sido enviado a revisión técnica. Se requiere realizar la inspección de componentes.',
                'creada_en': ahora,
            }
        )


def _respuesta_factura_renta(renta):
    respuesta = HttpResponse(
        generar_factura_renta_pdf(renta), content_type='application/pdf'
    )
    respuesta['Content-Disposition'] = f'inline; filename="factura_renta_{renta.renta_id}.pdf"'
    return respuesta


@login_required
@cajero_o_admin_required
def api_rentas_activas(request):
    """Endpoint ligero para sincronizar notificaciones globales de rentas activas en cualquier pantalla."""
    verificar_vencimiento_rentas_locales()
    return JsonResponse({'rentas': obtener_rentas_activas_payload()})


@login_required
@cajero_o_admin_required
def renta_list(request):
    verificar_vencimiento_rentas_locales()

    equipos = list(Equipo.objects.prefetch_related('componentes').all().order_by('nombre'))
    clientes = Cliente.objects.filter(activo=True).order_by('nombre', 'apellido')
    detalles_relevantes = list(
        DetalleRenta.objects
        .select_related('renta__cliente', 'renta__usuario', 'equipo')
        .filter(estado__in=ESTADOS_BLOQUEANTES)
        .order_by('hora_inicio')
    )

    rentas_activas_map = {d.equipo_id: d for d in detalles_relevantes if d.estado == 'ACTIVA'}
    rentas_terminadas_map = {d.equipo_id: d for d in detalles_relevantes if d.estado == 'TIEMPO_TERMINADO'}
    revisiones_map = {d.equipo_id: d for d in detalles_relevantes if d.estado == 'PENDIENTE_REVISION'}

    equipos_rentables = []
    for eq in equipos:
        eq.renta_activa = rentas_activas_map.get(eq.equipo_id)
        eq.tiempo_terminado = rentas_terminadas_map.get(eq.equipo_id)
        eq.revision_pendiente = revisiones_map.get(eq.equipo_id)

        # Regla de rentabilidad estricta
        es_rentable_base, motivo = eq.evaluar_rentabilidad()
        eq.bloqueo_motivo = motivo
        eq.puede_rentarse = (
            eq.renta_activa is None
            and eq.tiempo_terminado is None
            and eq.revision_pendiente is None
            and es_rentable_base
        )
        eq.es_rentable = eq.puede_rentarse
        if eq.puede_rentarse:
            equipos_rentables.append(eq)

    count_en_uso = sum(1 for eq in equipos if eq.renta_activa)
    count_tiempo_terminado = sum(1 for eq in equipos if eq.tiempo_terminado)
    count_revision = sum(1 for eq in equipos if eq.revision_pendiente)
    count_mantenimiento = sum(
        1 for eq in equipos
        if not eq.puede_rentarse and not eq.renta_activa and not eq.tiempo_terminado and not eq.revision_pendiente
    )
    count_disponibles = len(equipos_rentables)

    renta_token = request.session.get('renta_token')
    if not renta_token:
        renta_token = uuid.uuid4().hex
        request.session['renta_token'] = renta_token

    return render(request, 'rentas/rentas.html', {
        'equipos': equipos,
        'equipos_rentables': equipos_rentables,
        'clientes': clientes,
        'detalles_activos': [d for d in detalles_relevantes if d.estado == 'ACTIVA'],
        'detalles_terminados': [d for d in detalles_relevantes if d.estado == 'TIEMPO_TERMINADO'],
        'count_en_uso': count_en_uso,
        'count_tiempo_terminado': count_tiempo_terminado,
        'count_disponibles': count_disponibles,
        'count_mantenimiento': count_mantenimiento,
        'count_revision': count_revision,
        'renta_token': renta_token,
        'efectivo_maximo': EFECTIVO_MAXIMO,
        'now': timezone.now(),
    })


@login_required
@cajero_o_admin_required
def renta_extender(request):
    if request.method == 'POST':
        detalle_id = request.POST.get('detalle_renta_id')
        token_ext = (request.POST.get('ext_token') or uuid.uuid4().hex).strip()

        try:
            minutos_extra = int(request.POST.get('minutos_extra', 0))
            if minutos_extra < 1 or minutos_extra > 480:
                raise ValueError("El tiempo adicional debe ser de entre 1 y 480 minutos.")

            # Idempotencia por token persistido
            ext_existente = ExtensionRenta.objects.filter(clave_idempotencia=token_ext).first()
            if ext_existente:
                messages.warning(request, 'Esta extensión ya fue procesada anteriormente.')
                return _respuesta_factura_renta(ext_existente.detalle_renta.renta)

            ahora = timezone.now()

            with transaction.atomic():
                detalle_prev = get_object_or_404(
                    DetalleRenta, pk=detalle_id, estado__in=['ACTIVA', 'TIEMPO_TERMINADO']
                )
                # Orden estricto de locks: 1. Equipo -> 2. DetalleRenta
                equipo = get_object_or_404(Equipo.objects.select_for_update(), pk=detalle_prev.equipo_id)
                detalle = get_object_or_404(
                    DetalleRenta.objects.select_for_update().select_related('renta'),
                    pk=detalle_id,
                    estado__in=['ACTIVA', 'TIEMPO_TERMINADO'],
                )

                tarifa = Decimal(str(equipo.tarifa_por_hora))
                horas_extra = Decimal(minutos_extra) / Decimal('60')
                costo_extra = (tarifa * horas_extra).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

                # Validar efectivo recibido
                efectivo_raw = (request.POST.get('efectivo_recibido') or '').strip().replace('$', '')
                try:
                    efectivo_recibido = Decimal(efectivo_raw).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                except (InvalidOperation, TypeError, ValueError):
                    raise ValueError("Debe ingresar un monto válido de efectivo recibido para la extensión.")

                if efectivo_recibido < costo_extra:
                    raise ValueError(f"Efectivo insuficiente. Costo adicional: ${costo_extra:.2f}, Efectivo recibido: ${efectivo_recibido:.2f}.")

                if efectivo_recibido > EFECTIVO_MAXIMO:
                    raise ValueError(f"El monto máximo en efectivo permitido por operación es de ${EFECTIVO_MAXIMO:.2f}.")

                cambio_extra = (efectivo_recibido - costo_extra).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

                # Regla de negocio: si estaba vencida (TIEMPO_TERMINADO), no se cobra tiempo muerto
                # Se cuenta desde ahora y vuelve al estado ACTIVA
                if detalle.estado == 'TIEMPO_TERMINADO':
                    detalle.hora_vencimiento = ahora + timezone.timedelta(minutes=minutos_extra)
                    detalle.estado = 'ACTIVA'
                else:
                    # Renta activa aún: se suma a su vencimiento proyectado
                    if detalle.hora_vencimiento and detalle.hora_vencimiento > ahora:
                        detalle.hora_vencimiento += timezone.timedelta(minutes=minutos_extra)
                    else:
                        detalle.hora_vencimiento = ahora + timezone.timedelta(minutes=minutos_extra)

                detalle.tiempo_agregado = (detalle.tiempo_agregado or 0) + minutos_extra
                detalle.subtotal = (detalle.subtotal + costo_extra).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                detalle.save(update_fields=['tiempo_agregado', 'subtotal', 'hora_vencimiento', 'estado'])

                renta = detalle.renta
                renta.total = (renta.total + costo_extra).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                renta.efectivo_recibido = ((renta.efectivo_recibido or Decimal('0.00')) + efectivo_recibido).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                renta.cambio = cambio_extra
                renta.save(update_fields=['total', 'efectivo_recibido', 'cambio'])

                # Registrar la extensión en tabla histórica
                ExtensionRenta.objects.create(
                    detalle_renta=detalle,
                    usuario=request.user,
                    minutos=minutos_extra,
                    costo=costo_extra,
                    efectivo_recibido=efectivo_recibido,
                    cambio=cambio_extra,
                    clave_idempotencia=token_ext,
                    fecha=ahora,
                )

            messages.success(
                request,
                f'Se agregaron +{minutos_extra} min a {equipo.nombre}. '
                f'Cobro: ${costo_extra:.2f} (Efectivo: ${efectivo_recibido:.2f}, Cambio: ${cambio_extra:.2f}).'
            )
            request.session['ultima_renta_id'] = renta.renta_id
            return _respuesta_factura_renta(renta)
        except ValueError as e:
            messages.error(request, str(e))
        except Exception:
            messages.error(request, 'No se pudo extender la renta. Inténtalo de nuevo.')

    return redirect('rentas')


@login_required
@cajero_o_admin_required
def renta_create(request):
    if request.method == 'POST':
        equipo_id = request.POST.get('equipo_id')
        cliente_id = request.POST.get('cliente_id')
        tiempo_str = request.POST.get('tiempo_de_renta', '60')
        token_enviado = (request.POST.get('renta_token') or '').strip()

        # Idempotencia
        if token_enviado:
            renta_existente = Renta.objects.filter(clave_idempotencia=token_enviado).first()
            if renta_existente:
                messages.warning(request, f'La renta #{renta_existente.renta_id} ya fue registrada.')
                return _respuesta_factura_renta(renta_existente)

        try:
            if not cliente_id:
                raise ValueError("Debe seleccionar un cliente para iniciar la renta.")

            tiempo = int(tiempo_str)
            if tiempo < 15 or tiempo > 480:
                raise ValueError("El tiempo de renta debe ser de al menos 15 minutos y un máximo de 480 minutos (8 horas).")

            cliente = get_object_or_404(Cliente, pk=cliente_id, activo=True)
            ahora = timezone.now()

            with transaction.atomic():
                equipo = get_object_or_404(
                    Equipo.objects.select_for_update(), pk=equipo_id
                )

                es_rentable, motivo = equipo.evaluar_rentabilidad()
                if not es_rentable:
                    raise ValueError(f"El equipo {equipo.nombre} no está disponible: {motivo}")

                if DetalleRenta.objects.filter(
                    equipo=equipo, estado__in=ESTADOS_BLOQUEANTES
                ).exists():
                    raise ValueError(
                        f"El equipo {equipo.nombre} ya tiene una sesión en curso o pendiente de revisión."
                    )

                tarifa = Decimal(str(equipo.tarifa_por_hora))
                horas = Decimal(tiempo) / Decimal('60')
                subtotal = (tarifa * horas).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

                # Validar efectivo recibido
                efectivo_raw = (request.POST.get('efectivo_recibido') or '').strip().replace('$', '')
                try:
                    efectivo_recibido = Decimal(efectivo_raw).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                except (InvalidOperation, TypeError, ValueError):
                    raise ValueError("Debe ingresar un monto válido de efectivo recibido.")

                if efectivo_recibido < subtotal:
                    raise ValueError(f"Efectivo insuficiente. Total a pagar: ${subtotal:.2f}, Recibido: ${efectivo_recibido:.2f}.")

                if efectivo_recibido > EFECTIVO_MAXIMO:
                    raise ValueError(f"El monto máximo en efectivo permitido por transacción es de ${EFECTIVO_MAXIMO:.2f}.")

                cambio = (efectivo_recibido - subtotal).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                hora_vencimiento = ahora + timezone.timedelta(minutes=tiempo)

                renta = Renta.objects.create(
                    usuario=request.user,
                    cliente=cliente,
                    fecha=ahora,
                    total=subtotal,
                    efectivo_recibido=efectivo_recibido,
                    cambio=cambio,
                    clave_idempotencia=token_enviado or uuid.uuid4().hex,
                    estado_de_pago='PAGADO',
                )

                DetalleRenta.objects.create(
                    renta=renta,
                    equipo=equipo,
                    hora_inicio=ahora,
                    hora_vencimiento=hora_vencimiento,
                    tiempo_de_renta=tiempo,
                    tiempo_agregado=0,
                    hora_fin=None,
                    subtotal=subtotal,
                    estado='ACTIVA',
                )

                request.session['renta_token'] = uuid.uuid4().hex

            # Envío de factura por correo si se solicitó
            enviar_correo = bool(request.POST.get('enviar_correo'))
            cliente_correo = renta.cliente.correo if renta.cliente else None
            if enviar_correo and cliente_correo:
                from config.servicios_email import enviar_factura_renta_correo
                ok, msg_correo = enviar_factura_renta_correo(renta)
                if ok:
                    messages.success(
                        request,
                        f'Renta de {equipo.nombre} cobrada e iniciada ({tiempo} min). Factura enviada a {cliente_correo}.'
                    )
                else:
                    messages.warning(
                        request,
                        f'Renta de {equipo.nombre} iniciada ({tiempo} min). (Aviso correo: {msg_correo})'
                    )
            else:
                messages.success(
                    request,
                    f'Renta de {equipo.nombre} cobrada e iniciada exitosamente ({tiempo} min — Total: ${subtotal:.2f}, Cambio: ${cambio:.2f}).'
                )

            request.session['ultima_renta_id'] = renta.renta_id
            return _respuesta_factura_renta(renta)

        except ValueError as e:
            messages.error(request, str(e))
        except Exception:
            messages.error(request, 'No se pudo crear la renta. Verifica los datos e inténtalo de nuevo.')

    return redirect('rentas')


@login_required
@cajero_o_admin_required
def renta_enviar_revision(request):
    """
    Finaliza el tiempo de uso del equipo y lo envía directamente a revisión técnica.
    La renta ya fue cobrada previamente por adelantado.
    """
    if request.method == 'POST':
        detalle_id = request.POST.get('detalle_renta_id')
        try:
            with transaction.atomic():
                detalle = get_object_or_404(
                    DetalleRenta.objects.select_for_update().select_related('equipo', 'renta'),
                    pk=detalle_id,
                )
                if detalle.estado not in ('ACTIVA', 'TIEMPO_TERMINADO'):
                    raise ValueError(
                        f"La sesión de {detalle.equipo.nombre} no está activa ni en tiempo terminado "
                        f"(estado actual: {detalle.get_estado_display()})."
                    )
                detalle.estado = 'PENDIENTE_REVISION'
                detalle.hora_fin = timezone.now()
                detalle.save(update_fields=['estado', 'hora_fin'])
                crear_notificaciones_revision(detalle)

            messages.info(
                request,
                f'Sesión de {detalle.equipo.nombre} finalizada. El puesto ha pasado a Revisión Técnica.'
            )
        except ValueError as e:
            messages.error(request, str(e))
        except Exception:
            messages.error(request, 'No se pudo enviar el equipo a revisión. Inténtalo de nuevo.')

    return redirect('rentas')


@login_required
@cajero_o_admin_required
def renta_finalizar(request):
    """
    Cobra y confirma el cierre de la renta, enviando a PENDIENTE_REVISION si no se envió antes.
    No permite reasignación de cliente para evitar discrepancias contables.
    """
    if request.method == 'POST':
        detalle_id = request.POST.get('detalle_renta_id')
        try:
            with transaction.atomic():
                detalle_prev = get_object_or_404(DetalleRenta, pk=detalle_id)
                equipo = get_object_or_404(Equipo.objects.select_for_update(), pk=detalle_prev.equipo_id)
                detalle = get_object_or_404(
                    DetalleRenta.objects.select_for_update().select_related('renta'),
                    pk=detalle_id,
                )

                if detalle.estado == 'FINALIZADA' and detalle.renta.estado_de_pago == 'PAGADO':
                    messages.info(request, f'La renta #{detalle.renta.renta_id} ya fue finalizada anteriormente.')
                    request.session['ultima_renta_id'] = detalle.renta.renta_id
                    return _respuesta_factura_renta(detalle.renta)

                if detalle.estado in ('ACTIVA', 'TIEMPO_TERMINADO'):
                    detalle.estado = 'PENDIENTE_REVISION'
                    detalle.hora_fin = timezone.now()
                    detalle.save(update_fields=['estado', 'hora_fin'])
                    crear_notificaciones_revision(detalle)

                renta = detalle.renta
                renta.estado_de_pago = 'PAGADO'
                renta.save(update_fields=['estado_de_pago'])

            messages.success(request, f'Renta de {equipo.nombre} finalizada y registrada correctamente.')
            request.session['ultima_renta_id'] = renta.renta_id
            return _respuesta_factura_renta(renta)
        except ValueError as e:
            messages.error(request, str(e))
        except Exception:
            messages.error(request, 'No se pudo cobrar/finalizar la renta. Inténtalo de nuevo.')

    return redirect('rentas')


@login_required
@cajero_o_admin_required
def renta_factura_pdf(request, renta_id=None):
    renta = None
    if renta_id is not None:
        renta = Renta.objects.filter(pk=renta_id).first()
    else:
        ultima = request.session.get('ultima_renta_id')
        if ultima:
            renta = Renta.objects.filter(pk=ultima).first()

    if renta is None:
        messages.error(request, 'No hay ninguna renta registrada para generar la factura.')
        return redirect('rentas')

    return _respuesta_factura_renta(renta)
