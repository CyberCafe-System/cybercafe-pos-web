from decimal import ROUND_HALF_UP, Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from clientes.models import Cliente
from equipos.models import Equipo
from usuarios.decorators import cajero_o_admin_required

from .models import DetalleRenta, Renta
from .ticket import generar_factura_renta_pdf

ESTADOS_RENTABLES = ('DISPONIBLE', 'DANIOS_MENORES')
ESTADOS_BLOQUEANTES = ('ACTIVA', 'PENDIENTE_REVISION')


def _equipo_es_rentable(equipo):
    return equipo.estado in ESTADOS_RENTABLES


def _respuesta_factura_renta(renta):
    respuesta = HttpResponse(
        generar_factura_renta_pdf(renta), content_type='application/pdf'
    )
    respuesta['Content-Disposition'] = f'inline; filename="factura_renta_{renta.renta_id}.pdf"'
    return respuesta


@login_required
def renta_list(request):
    equipos = list(Equipo.objects.prefetch_related('componentes').all().order_by('nombre'))
    clientes = Cliente.objects.all().order_by('nombre', 'apellido')
    detalles_relevantes = list(
        DetalleRenta.objects
        .select_related('renta__cliente', 'renta__usuario', 'equipo')
        .filter(estado__in=ESTADOS_BLOQUEANTES)
        .order_by('hora_inicio')
    )

    rentas_por_equipo = {d.equipo_id: d for d in detalles_relevantes if d.estado == 'ACTIVA'}
    revisiones_por_equipo = {d.equipo_id: d for d in detalles_relevantes if d.estado == 'PENDIENTE_REVISION'}

    equipos_rentables = []
    for eq in equipos:
        eq.renta_activa = rentas_por_equipo.get(eq.equipo_id)
        eq.revision_pendiente = revisiones_por_equipo.get(eq.equipo_id)
        eq.es_rentable = (
            eq.renta_activa is None
            and eq.revision_pendiente is None
            and _equipo_es_rentable(eq)
        )
        if eq.es_rentable:
            equipos_rentables.append(eq)

    count_en_uso = sum(1 for eq in equipos if eq.renta_activa)
    count_revision = sum(1 for eq in equipos if eq.revision_pendiente)
    count_mantenimiento = sum(
        1 for eq in equipos
        if not eq.es_rentable and not eq.renta_activa and not eq.revision_pendiente
    )
    count_disponibles = len(equipos_rentables)

    return render(request, 'rentas/rentas.html', {
        'equipos': equipos,
        'equipos_rentables': equipos_rentables,
        'clientes': clientes,
        'detalles_activos': [d for d in detalles_relevantes if d.estado == 'ACTIVA'],
        'count_en_uso': count_en_uso,
        'count_disponibles': count_disponibles,
        'count_mantenimiento': count_mantenimiento,
        'count_revision': count_revision,
        'now': timezone.now(),
    })


@login_required
@cajero_o_admin_required
def renta_extender(request):
    if request.method == 'POST':
        detalle_id = request.POST.get('detalle_renta_id')
        try:
            minutos_extra = int(request.POST.get('minutos_extra', 0))
            if minutos_extra <= 0:
                raise ValueError("El tiempo adicional debe ser mayor a 0.")

            with transaction.atomic():
                detalle = get_object_or_404(
                    DetalleRenta.objects.select_for_update().select_related('equipo', 'renta'),
                    pk=detalle_id,
                    estado='ACTIVA',
                )
                equipo = detalle.equipo
                tarifa = Decimal(str(equipo.tarifa_por_hora))
                horas_extra = Decimal(minutos_extra) / Decimal('60')
                costo_extra = (tarifa * horas_extra).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

                detalle.tiempo_agregado = (detalle.tiempo_agregado or 0) + minutos_extra
                detalle.subtotal += costo_extra
                detalle.save(update_fields=['tiempo_agregado', 'subtotal'])

                renta = detalle.renta
                renta.total += costo_extra
                renta.save(update_fields=['total'])

            messages.success(request, f'Se agregaron +{minutos_extra} min a {equipo.nombre}. Nuevo total: ${detalle.subtotal}')
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

        try:
            tiempo = int(tiempo_str)
            if tiempo <= 0:
                raise ValueError("El tiempo debe ser mayor a 0.")

            cliente = get_object_or_404(Cliente, pk=cliente_id)
            ahora = timezone.now()

            with transaction.atomic():
                equipo = get_object_or_404(
                    Equipo.objects.select_for_update(), pk=equipo_id
                )

                if not _equipo_es_rentable(equipo):
                    raise ValueError(
                        f"El equipo {equipo.nombre} no está disponible para renta "
                        f"(estado: {equipo.get_estado_display()})."
                    )

                if DetalleRenta.objects.filter(
                    equipo=equipo, estado__in=ESTADOS_BLOQUEANTES
                ).exists():
                    raise ValueError(
                        f"El equipo {equipo.nombre} ya tiene una sesión activa "
                        f"o pendiente de revisión."
                    )

                tarifa = Decimal(str(equipo.tarifa_por_hora))
                horas = Decimal(tiempo) / Decimal('60')
                subtotal = (tarifa * horas).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

                renta = Renta.objects.create(
                    usuario=request.user,
                    cliente=cliente,
                    fecha=ahora,
                    total=subtotal,
                    estado_de_pago='PENDIENTE',
                )

                DetalleRenta.objects.create(
                    renta=renta,
                    equipo=equipo,
                    hora_inicio=ahora,
                    tiempo_de_renta=tiempo,
                    tiempo_agregado=0,
                    hora_fin=None,
                    subtotal=subtotal,
                    estado='ACTIVA',
                )

            messages.success(request, f'Renta iniciada para {equipo.nombre} — {tiempo} min. Total: ${subtotal}')

        except ValueError as e:
            messages.error(request, str(e))
        except Exception:
            messages.error(request, 'No se pudo crear la renta. Verifica los datos e inténtalo de nuevo.')

    return redirect('rentas')


@login_required
@cajero_o_admin_required
def renta_finalizar(request):
    if request.method == 'POST':
        detalle_id = request.POST.get('detalle_renta_id')
        try:
            with transaction.atomic():
                detalle = get_object_or_404(
                    DetalleRenta.objects.select_for_update().select_related('equipo', 'renta'),
                    pk=detalle_id,
                )

                if detalle.estado != 'ACTIVA':
                    raise ValueError(
                        f"La renta de {detalle.equipo.nombre} no está activa "
                        f"(estado actual: {detalle.get_estado_display()})."
                    )

                detalle.estado = 'PENDIENTE_REVISION'
                detalle.hora_fin = timezone.now()
                detalle.save(update_fields=['estado', 'hora_fin'])

                renta = detalle.renta
                renta.estado_de_pago = 'PAGADO'
                renta.save(update_fields=['estado_de_pago'])

            # Enviar comprobante por correo si el checklist está activado
            enviar_correo = bool(request.POST.get('enviar_correo'))
            cliente_correo = renta.cliente.correo if renta.cliente else None
            if enviar_correo and cliente_correo:
                from config.servicios_email import enviar_factura_renta_correo
                ok, msg_correo = enviar_factura_renta_correo(renta)
                if ok:
                    messages.success(
                        request,
                        f'Renta de {detalle.equipo.nombre} cobrada. Factura enviada por correo a {cliente_correo}.'
                    )
                else:
                    messages.warning(
                        request,
                        f'Renta de {detalle.equipo.nombre} cobrada. (Aviso de correo: {msg_correo})'
                    )
            elif enviar_correo and not cliente_correo:
                messages.info(
                    request,
                    f'Renta de {detalle.equipo.nombre} cobrada. (El cliente no tiene correo electrónico registrado).'
                )
            else:
                messages.success(
                    request,
                    f'Renta de {detalle.equipo.nombre} cobrada. El equipo queda '
                    f'pendiente de revisión antes de volver a estar disponible.'
                )

            request.session['ultima_renta_id'] = renta.renta_id
            return _respuesta_factura_renta(renta)
        except ValueError as e:
            messages.error(request, str(e))
        except Exception:
            messages.error(request, 'No se pudo finalizar la renta. Inténtalo de nuevo.')

    return redirect('rentas')


@login_required
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
