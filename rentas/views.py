from decimal import ROUND_HALF_UP, Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from clientes.models import Cliente
from equipos.models import Equipo
from usuarios.decorators import cajero_o_admin_required

from .models import DetalleRenta, Renta


@login_required
def renta_list(request):
    equipos = list(Equipo.objects.prefetch_related('componentes').all().order_by('nombre'))
    clientes = Cliente.objects.all().order_by('nombre', 'apellido')
    detalles_activos = list(
        DetalleRenta.objects
        .select_related('renta__cliente', 'renta__usuario', 'equipo')
        .filter(estado='ACTIVA')
        .order_by('hora_inicio')
    )
    rentas_por_equipo = {d.equipo_id: d for d in detalles_activos}
    for eq in equipos:
        eq.renta_activa = rentas_por_equipo.get(eq.equipo_id)

    return render(request, 'rentas/rentas.html', {
        'equipos': equipos,
        'clientes': clientes,
        'detalles_activos': detalles_activos,
        'now': timezone.now(),
    })


@login_required
@cajero_o_admin_required
def renta_create(request):
    if request.method == 'POST':
        equipo_id = request.POST.get('equipo_id')
        cliente_id = request.POST.get('cliente_id')
        tiempo_str = request.POST.get('tiempo_de_renta', '60')

        try:
            equipo = get_object_or_404(Equipo, pk=equipo_id)
            cliente = get_object_or_404(Cliente, pk=cliente_id)
            tiempo = int(tiempo_str)
            if tiempo <= 0:
                raise ValueError("El tiempo debe ser mayor a 0.")

            tarifa = Decimal(str(equipo.tarifa_por_hora))
            horas = Decimal(tiempo) / Decimal('60')
            subtotal = (tarifa * horas).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            ahora = timezone.now()

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

        except Exception as e:
            messages.error(request, f'Error al crear la renta: {e}')

    return redirect('rentas')


@login_required
@cajero_o_admin_required
def renta_finalizar(request):
    if request.method == 'POST':
        detalle_id = request.POST.get('detalle_renta_id')
        try:
            detalle = get_object_or_404(DetalleRenta, pk=detalle_id)
            detalle.estado = 'FINALIZADA'
            detalle.hora_fin = timezone.now()
            detalle.save(update_fields=['estado', 'hora_fin'])

            renta = detalle.renta
            renta.estado_de_pago = 'PAGADO'
            renta.save(update_fields=['estado_de_pago'])

            messages.success(request, f'Renta de {detalle.equipo.nombre} finalizada y cobrada.')
        except Exception as e:
            messages.error(request, f'Error al finalizar la renta: {e}')

    return redirect('rentas')
