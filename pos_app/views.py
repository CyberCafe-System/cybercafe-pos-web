from decimal import ROUND_HALF_UP, Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from clientes.models import Cliente
from inventario.models import Producto

from .models import DetalleVenta, Venta
from .ticket import generar_factura_pdf

IVA = Decimal('0.13')
CENTAVOS = Decimal('0.01')


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
def pos(request):
    productos = (
        Producto.objects.filter(activo=True)
        .select_related('categoria')
        .order_by('categoria__nombre', 'nombre')
    )
    items, subtotal, iva, total = _resumen_carrito(_obtener_carrito(request))
    contexto = {
        'productos': productos,
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
def quitar_carrito(request):
    if request.method == 'POST':
        carrito = _obtener_carrito(request)
        carrito.pop(str(request.POST.get('producto_id')), None)
        request.session['carrito'] = carrito
    return redirect('pos')


@login_required
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
