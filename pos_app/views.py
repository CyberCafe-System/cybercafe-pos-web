from decimal import ROUND_HALF_UP, Decimal
from itertools import groupby

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from clientes.models import Cliente
from equipos.models import Equipo
from inventario.models import Producto
from rentas.models import DetalleRenta, Renta
from usuarios.decorators import cajero_o_admin_required

from .models import DetalleVenta, Venta
from .ticket import generar_factura_pdf

IVA = Decimal('0.13')
CENTAVOS = Decimal('0.01')


@login_required
def inicio(request):
    hoy = timezone.localdate()

    ventas_hoy_qs = Venta.objects.filter(fecha__date=hoy)
    rentas_hoy_qs = Renta.objects.filter(fecha__date=hoy)

    # Ingresos totales de hoy (POS + Rentas)
    subtotal_ventas = sum((v.subtotal + v.iva) for v in ventas_hoy_qs) or Decimal('0.00')
    subtotal_rentas = sum(r.total for r in rentas_hoy_qs) or Decimal('0.00')
    ingresos_hoy = (subtotal_ventas + subtotal_rentas).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # Equipos en uso
    equipos_ocupados = DetalleRenta.objects.filter(estado='ACTIVA').count()
    total_equipos = Equipo.objects.count()
    equipos_activos_str = f"{equipos_ocupados} / {total_equipos}" if total_equipos else "0 / 0"

    # Total de ventas POS hoy
    ventas_hoy_count = ventas_hoy_qs.count()

    # Clientes activos únicos hoy (set union para deduplicación estricta)
    clientes_ventas = set(ventas_hoy_qs.exclude(cliente_id__isnull=True).values_list('cliente_id', flat=True))
    clientes_rentas = set(rentas_hoy_qs.exclude(cliente_id__isnull=True).values_list('cliente_id', flat=True))
    total_clientes_activos = len(clientes_ventas | clientes_rentas)

    # Últimas transacciones (Ventas y Rentas)
    ultimas_ventas_raw = list(
        Venta.objects.select_related('cliente', 'usuario')
        .prefetch_related('detalles__producto')
        .order_by('-fecha')[:6]
    )
    ultimas_rentas_raw = list(
        Renta.objects.select_related('cliente', 'usuario')
        .prefetch_related('detalles__equipo')
        .order_by('-fecha')[:6]
    )

    transacciones = []
    for v in ultimas_ventas_raw:
        items_nombres = [d.producto.nombre for d in v.detalles.all()[:2]]
        concepto = ", ".join(items_nombres) if items_nombres else "Venta de mostrador"
        if v.detalles.count() > 2:
            concepto += f" (+{v.detalles.count() - 2} más)"
        transacciones.append({
            'id': f"TK-{v.venta_id}",
            'cliente': v.cliente,
            'concepto': concepto,
            'usuario': v.usuario,
            'fecha_hora': v.fecha,
            'total': (v.subtotal + v.iva).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'estado': 'Pagado',
            'es_venta': True,
        })

    for r in ultimas_rentas_raw:
        det = r.detalles.first()
        equipo_nom = det.equipo.nombre if det and det.equipo else "Equipo"
        minutos = det.tiempo_de_renta if det else 60
        transacciones.append({
            'id': f"RN-{r.renta_id}",
            'cliente': r.cliente,
            'concepto': f"Renta {equipo_nom} ({minutos} min)",
            'usuario': r.usuario,
            'fecha_hora': r.fecha,
            'total': r.total,
            'estado': r.estado_de_pago.title(),
            'es_venta': False,
        })

    # Ordenar por fecha descendente y tomar las 8 más recientes
    transacciones.sort(key=lambda x: x['fecha_hora'], reverse=True)
    ultimas_transacciones = transacciones[:8]

    # Gráfica 1: Últimos 7 días con desglose real de Ventas vs Rentas
    dias_semana_es = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
    chart_dias_labels = []
    chart_ventas_data = []
    chart_rentas_data = []

    for i in range(6, -1, -1):
        dia = hoy - timezone.timedelta(days=i)
        etiqueta = "Hoy" if i == 0 else f"{dias_semana_es[dia.weekday()]} {dia.day}"
        chart_dias_labels.append(etiqueta)

        v_sub = sum((v.subtotal + v.iva) for v in Venta.objects.filter(fecha__date=dia)) or Decimal('0.00')
        r_sub = sum(r.total for r in Renta.objects.filter(fecha__date=dia)) or Decimal('0.00')

        chart_ventas_data.append(float(v_sub))
        chart_rentas_data.append(float(r_sub))

    # Gráfica 2: Top 5 Productos Más Vendidos
    top_vendidos_qs = list(
        DetalleVenta.objects.values('producto__nombre')
        .annotate(total_unidades=Sum('cantidad'))
        .order_by('-total_unidades')[:5]
    )
    chart_top_labels = []
    chart_top_data = []
    for item in top_vendidos_qs:
        if item['producto__nombre']:
            chart_top_labels.append(item['producto__nombre'])
            chart_top_data.append(int(item['total_unidades']))

    tiene_datos_top = bool(chart_top_labels)
    if not tiene_datos_top:
        chart_top_labels = ['Sin ventas aún']
        chart_top_data = [1]

    # Resumen semanal acumulado
    total_semana_ventas = sum(chart_ventas_data)
    total_semana_rentas = sum(chart_rentas_data)
    total_semana = total_semana_ventas + total_semana_rentas

    # Ocupación de equipos
    equipos_libres = max(0, total_equipos - equipos_ocupados)
    porcentaje_ocupacion = round((equipos_ocupados / total_equipos * 100), 1) if total_equipos else 0

    import json

    return render(request, 'inicio.html', {
        'ingresos_hoy': ingresos_hoy,
        'equipos_activos': equipos_activos_str,
        'equipos_ocupados': equipos_ocupados,
        'equipos_libres': equipos_libres,
        'total_equipos': total_equipos,
        'porcentaje_ocupacion': porcentaje_ocupacion,
        'ventas_hoy': ventas_hoy_count,
        'total_clientes': total_clientes_activos,
        'ultimas_ventas': ultimas_transacciones,
        'chart_dias_labels': json.dumps(chart_dias_labels),
        'chart_ventas_data': json.dumps(chart_ventas_data),
        'chart_rentas_data': json.dumps(chart_rentas_data),
        'chart_top_labels': json.dumps(chart_top_labels),
        'chart_top_data': json.dumps(chart_top_data),
        'tiene_datos_top': tiene_datos_top,
        'total_semana': total_semana,
        'total_semana_ventas': total_semana_ventas,
        'total_semana_rentas': total_semana_rentas,
    })


def _obtener_carrito(request):
    carrito = request.session.get('carrito')
    if not isinstance(carrito, dict):
        return {}
    return carrito


def _resumen_carrito(carrito):
    items = []
    subtotal = Decimal('0.00')
    for producto_id, cantidad in carrito.items():
        producto = (
            Producto.objects.filter(pk=producto_id, activo=True)
            .select_related('categoria')
            .first()
        )
        if producto is None:
            continue
        linea = producto.precio_venta * cantidad
        subtotal += linea
        items.append({'producto': producto, 'cantidad': cantidad, 'subtotal': linea})
    iva = (subtotal * IVA).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    return items, subtotal, iva, subtotal + iva


def _respuesta_pdf(venta):
    respuesta = HttpResponse(generar_factura_pdf(venta), content_type='application/pdf')
    respuesta['Content-Disposition'] = f'inline; filename="factura_{venta.venta_id}.pdf"'
    return respuesta


@login_required
@cajero_o_admin_required
def pos(request):
    productos = (
        Producto.objects.filter(activo=True)
        .select_related('categoria')
        .order_by('categoria__nombre', 'nombre')
    )

    # Organizar por categorías
    categorias_dict = {}
    for p in productos:
        cat_nom = p.categoria.nombre if p.categoria else 'General'
        if cat_nom not in categorias_dict:
            categorias_dict[cat_nom] = []
        categorias_dict[cat_nom].append(p)

    categorias_resumen = [
        {'nombre': cat_nom, 'cantidad': len(prods)}
        for cat_nom, prods in categorias_dict.items()
    ]

    items, subtotal, iva, total = _resumen_carrito(_obtener_carrito(request))
    contexto = {
        'productos': productos,
        'categorias_dict': categorias_dict,
        'categorias_resumen': categorias_resumen,
        'items': items,
        'subtotal': subtotal,
        'iva': iva,
        'total': total,
        'clientes': Cliente.objects.order_by('nombre', 'apellido'),
        'iva_porcentaje': int(IVA * 100),
        'ultima_venta_id': request.session.get('ultima_venta_id'),
    }
    return render(request, 'pos/pos.html', contexto)


@login_required
@cajero_o_admin_required
def agregar_carrito(request):
    if request.method == 'POST':
        producto = get_object_or_404(Producto, pk=request.POST.get('producto_id'), activo=True)
        try:
            cantidad = int(request.POST.get('cantidad') or 1)
        except (TypeError, ValueError):
            cantidad = 1
        if cantidad < 1:
            cantidad = 1

        carrito = _obtener_carrito(request)
        clave = str(producto.producto_id)
        actual = carrito.get(clave, 0)
        if actual + cantidad > producto.cantidad:
            messages.error(
                request,
                f'Inventario insuficiente de "{producto.nombre}" '
                f'(disponible: {producto.cantidad}).',
            )
        else:
            carrito[clave] = actual + cantidad
            request.session['carrito'] = carrito
    return redirect('pos')


@login_required
@cajero_o_admin_required
def quitar_carrito(request):
    if request.method == 'POST':
        carrito = _obtener_carrito(request)
        carrito.pop(str(request.POST.get('producto_id')), None)
        request.session['carrito'] = carrito
    return redirect('pos')


@login_required
@cajero_o_admin_required
def procesar_venta(request):
    if request.method != 'POST':
        return redirect('pos')

    items, subtotal, iva, _total = _resumen_carrito(_obtener_carrito(request))
    if not items:
        messages.error(request, 'El carrito está vacío. Agrega productos antes de procesar el pago.')
        return redirect('pos')

    cliente = get_object_or_404(Cliente, pk=request.POST.get('cliente_id'))

    venta = Venta.objects.create(
        cliente=cliente,
        usuario=request.user,
        fecha=timezone.now(),
        subtotal=subtotal,
        iva=iva,
    )

    for item in items:
        producto = item['producto']
        DetalleVenta.objects.create(
            venta=venta,
            producto=producto,
            precio_unitario=producto.precio_venta,
            cantidad=item['cantidad'],
            subtotal=item['subtotal'],
        )
        producto.cantidad = max(producto.cantidad - item['cantidad'], 0)
        producto.save(update_fields=['cantidad'])

    request.session['carrito'] = {}
    request.session['ultima_venta_id'] = venta.venta_id
    messages.success(request, f'Venta #{venta.venta_id} registrada correctamente.')

    return _respuesta_pdf(venta)


@login_required
@cajero_o_admin_required
def ticket_pdf(request, venta_id=None):
    venta = None
    if venta_id is not None:
        venta = Venta.objects.filter(pk=venta_id).first()
    else:
        ultima = request.session.get('ultima_venta_id')
        if ultima:
            venta = Venta.objects.filter(pk=ultima).first()

    if venta is None:
        messages.error(request, 'No hay ninguna venta registrada para generar el ticket.')
        return redirect('pos')

    return _respuesta_pdf(venta)


@login_required
@cajero_o_admin_required
def reportes(request):
    fecha_inicio_str = request.GET.get('fecha_inicio')
    fecha_fin_str = request.GET.get('fecha_fin')

    ventas_qs = Venta.objects.select_related('cliente', 'usuario').prefetch_related('detalles__producto').order_by('-fecha')
    rentas_qs = Renta.objects.select_related('cliente', 'usuario').prefetch_related('detalles__equipo').order_by('-fecha')

    if fecha_inicio_str:
        ventas_qs = ventas_qs.filter(fecha__date__gte=fecha_inicio_str)
        rentas_qs = rentas_qs.filter(fecha__date__gte=fecha_inicio_str)
    if fecha_fin_str:
        ventas_qs = ventas_qs.filter(fecha__date__lte=fecha_fin_str)
        rentas_qs = rentas_qs.filter(fecha__date__lte=fecha_fin_str)

    transacciones = []
    for v in ventas_qs[:100]:
        items_nombres = [f"{d.cantidad}x {d.producto.nombre}" for d in v.detalles.all()]
        articulos = ", ".join(items_nombres) if items_nombres else "Venta de mostrador"
        transacciones.append({
            'ticket': f"V-{v.venta_id}",
            'fecha': v.fecha,
            'usuario': v.usuario.username if v.usuario else "Sistema",
            'cliente': f"{v.cliente.nombre} {v.cliente.apellido}" if v.cliente else "Cliente General",
            'concepto': articulos,
            'total': (v.subtotal + v.iva).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'tipo': 'Venta POS',
            'es_venta': True,
            'venta_id': v.venta_id,
        })

    for r in rentas_qs[:100]:
        det = r.detalles.first()
        equipo_nom = det.equipo.nombre if det and det.equipo else "Equipo"
        minutos = det.tiempo_de_renta if det else 60
        transacciones.append({
            'ticket': f"R-{r.renta_id}",
            'fecha': r.fecha,
            'usuario': r.usuario.username if r.usuario else "Sistema",
            'cliente': f"{r.cliente.nombre} {r.cliente.apellido}" if r.cliente else "Cliente General",
            'concepto': f"Renta {equipo_nom} ({minutos} min)",
            'total': r.total,
            'tipo': 'Renta de Equipo',
            'es_venta': False,
            'venta_id': None,
        })

    transacciones.sort(key=lambda x: x['fecha'], reverse=True)
    total_recaudado = sum((t['total'] for t in transacciones), Decimal('0.00'))

    return render(request, 'reportes.html', {
        'transacciones': transacciones,
        'total_recaudado': total_recaudado,
        'fecha_inicio': fecha_inicio_str or '',
        'fecha_fin': fecha_fin_str or '',
    })

