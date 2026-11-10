import csv
import datetime
import json
import logging
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Case, DecimalField, F, Sum, When
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from clientes.models import Cliente
from equipos.models import Equipo
from inventario.models import MovimientoInventario, Producto
from rentas.models import DetalleRenta, Renta
from usuarios.decorators import admin_required, cajero_o_admin_required
from usuarios.models import Auditoria, Usuario, registrar_auditoria

from .models import DetalleVenta, Venta
from .ticket import generar_factura_pdf

IVA = Decimal('0.13')
CENTAVOS = Decimal('0.01')
EFECTIVO_MAXIMO = getattr(settings, 'EFECTIVO_MAXIMO', Decimal('100.00'))

logger = logging.getLogger(__name__)


def _rango_fecha_local(dia):
    tz = timezone.get_current_timezone()
    inicio = timezone.make_aware(datetime.datetime.combine(dia, datetime.time.min), tz)
    fin = timezone.make_aware(datetime.datetime.combine(dia, datetime.time.max), tz)
    return inicio, fin


def _filtrar_por_fechas(qs, fecha_inicio_str, fecha_fin_str):
    tz = timezone.get_current_timezone()
    if fecha_inicio_str:
        try:
            d_ini = datetime.date.fromisoformat(fecha_inicio_str)
            dt_ini = timezone.make_aware(datetime.datetime.combine(d_ini, datetime.time.min), tz)
            qs = qs.filter(fecha__gte=dt_ini)
        except (ValueError, TypeError):
            pass
    if fecha_fin_str:
        try:
            d_fin = datetime.date.fromisoformat(fecha_fin_str)
            dt_fin = timezone.make_aware(datetime.datetime.combine(d_fin, datetime.time.max), tz)
            qs = qs.filter(fecha__lte=dt_fin)
        except (ValueError, TypeError):
            pass
    return qs


@login_required
def inicio(request):
    if getattr(request.user, 'es_asistente', False):
        from django.contrib.auth import logout
        logout(request)
        messages.error(
            request,
            'El rol de Asistente Técnico no tiene acceso al sistema web. '
            'Por favor, utiliza la aplicación móvil oficial.'
        )
        return redirect('login')

    hoy = timezone.localdate()
    inicio_hoy, fin_hoy = _rango_fecha_local(hoy)

    ventas_hoy_qs = Venta.objects.filter(fecha__range=(inicio_hoy, fin_hoy)).exclude(estado='ANULADA')
    rentas_hoy_qs = Renta.objects.filter(fecha__range=(inicio_hoy, fin_hoy))

    # Ingresos totales de hoy calculados mediante agregación SQL (POS sin anuladas + Rentas)
    subtotal_ventas = ventas_hoy_qs.aggregate(
        total=Coalesce(Sum(F('subtotal') + F('iva'), output_field=DecimalField()), Decimal('0.00'))
    )['total'] or Decimal('0.00')
    subtotal_rentas = rentas_hoy_qs.aggregate(
        total=Coalesce(Sum('total'), Decimal('0.00'))
    )['total'] or Decimal('0.00')
    ingresos_hoy = (subtotal_ventas + subtotal_rentas).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # Equipos en uso o con tiempo terminado
    equipos_ocupados = DetalleRenta.objects.filter(
        estado__in=['ACTIVA', 'TIEMPO_TERMINADO']
    ).values('equipo_id').distinct().count()
    total_equipos = Equipo.objects.count()
    equipos_activos_str = f"{equipos_ocupados} / {total_equipos}" if total_equipos else "0 / 0"

    ventas_hoy_count = ventas_hoy_qs.count()

    clientes_ventas = set(ventas_hoy_qs.exclude(cliente_id__isnull=True).values_list('cliente_id', flat=True))
    clientes_rentas = set(rentas_hoy_qs.exclude(cliente_id__isnull=True).values_list('cliente_id', flat=True))
    total_clientes_activos = len(clientes_ventas | clientes_rentas)

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
        detalles_v = list(v.detalles.all())
        items_nombres = [d.producto.nombre for d in detalles_v[:2] if d.producto]
        concepto = ", ".join(items_nombres) if items_nombres else "Venta de mostrador"
        if len(detalles_v) > 2:
            concepto += f" (+{len(detalles_v) - 2} más)"
        cliente_nombre = f"{v.cliente.nombre} {v.cliente.apellido}" if v.cliente else "Cliente General"
        estado_label = 'Anulada' if v.estado == 'ANULADA' else 'Pagado'
        transacciones.append({
            'id': f"TK-{v.venta_id}",
            'cliente': v.cliente,
            'cliente_nombre': cliente_nombre,
            'concepto': concepto,
            'usuario': v.usuario,
            'fecha_hora': v.fecha,
            'total': (v.subtotal + v.iva).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'estado': estado_label,
            'es_anulada': v.estado == 'ANULADA',
            'es_venta': True,
        })

    for r in ultimas_rentas_raw:
        detalles_r = list(r.detalles.all())
        det = detalles_r[0] if detalles_r else None
        equipo_nom = det.equipo.nombre if det and det.equipo else "Equipo"
        minutos = det.tiempo_de_renta if det else 60
        cliente_nombre = f"{r.cliente.nombre} {r.cliente.apellido}" if r.cliente else "Cliente General"
        transacciones.append({
            'id': f"RN-{r.renta_id}",
            'cliente': r.cliente,
            'cliente_nombre': cliente_nombre,
            'concepto': f"Renta {equipo_nom} ({minutos} min)",
            'usuario': r.usuario,
            'fecha_hora': r.fecha,
            'total': r.total,
            'estado': r.estado_de_pago.title(),
            'es_anulada': False,
            'es_venta': False,
        })

    transacciones.sort(key=lambda x: x['fecha_hora'], reverse=True)
    ultimas_transacciones = transacciones[:5]

    inicio_semana = hoy - timezone.timedelta(days=hoy.weekday())
    fin_semana = inicio_semana + timezone.timedelta(days=6)
    inicio_semana_dt, _ = _rango_fecha_local(inicio_semana)
    _, fin_semana_dt = _rango_fecha_local(fin_semana)

    dias_semana_es = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    chart_dias_labels = []
    chart_ventas_data = []
    chart_rentas_data = []

    agregaciones_ventas_semana = {}
    agregaciones_rentas_semana = {}
    for i in range(7):
        dia = inicio_semana + timezone.timedelta(days=i)
        ini_dia, fin_dia = _rango_fecha_local(dia)
        agregaciones_ventas_semana[f'd_{i}'] = Coalesce(
            Sum(
                Case(
                    When(
                        fecha__range=(ini_dia, fin_dia),
                        then=F('subtotal') + F('iva'),
                    ),
                    default=Decimal('0.00'),
                    output_field=DecimalField(),
                )
            ),
            Decimal('0.00'),
        )
        agregaciones_rentas_semana[f'd_{i}'] = Coalesce(
            Sum(
                Case(
                    When(fecha__range=(ini_dia, fin_dia), then=F('total')),
                    default=Decimal('0.00'),
                    output_field=DecimalField(),
                )
            ),
            Decimal('0.00'),
        )

    totales_ventas_semana = (
        Venta.objects.filter(fecha__range=(inicio_semana_dt, fin_semana_dt))
        .exclude(estado='ANULADA')
        .aggregate(**agregaciones_ventas_semana)
    )
    totales_rentas_semana = (
        Renta.objects.filter(fecha__range=(inicio_semana_dt, fin_semana_dt))
        .aggregate(**agregaciones_rentas_semana)
    )

    for i in range(7):
        chart_dias_labels.append(dias_semana_es[i])

        v_sub = totales_ventas_semana.get(f'd_{i}', Decimal('0.00')) or Decimal('0.00')
        r_sub = totales_rentas_semana.get(f'd_{i}', Decimal('0.00')) or Decimal('0.00')

        chart_ventas_data.append(float(v_sub))
        chart_rentas_data.append(float(r_sub))

    top_vendidos_qs = list(
        DetalleVenta.objects.filter(
            venta__fecha__range=(inicio_semana_dt, fin_semana_dt)
        ).exclude(venta__estado='ANULADA')
        .values('producto__nombre')
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
        chart_top_labels = ['Sin ventas esta semana']
        chart_top_data = [1]

    total_semana_ventas = sum(chart_ventas_data)
    total_semana_rentas = sum(chart_rentas_data)
    total_semana = total_semana_ventas + total_semana_rentas

    equipos_libres = max(0, total_equipos - equipos_ocupados)
    porcentaje_ocupacion = int(round((equipos_ocupados / total_equipos * 100))) if total_equipos else 0

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
        'inicio_semana': inicio_semana,
        'fin_semana': fin_semana,
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
    """
    Calcula el resumen del carrito en una sola consulta por lotes.
    Detecta y reporta ítems que ya no existen, están inactivos o tienen su categoría inactiva.
    """
    if not carrito:
        return [], Decimal('0.00'), Decimal('0.00'), Decimal('0.00'), []

    ids_int = []
    for pid in carrito.keys():
        try:
            ids_int.append(int(pid))
        except (ValueError, TypeError):
            pass

    prods_db = {
        p.producto_id: p
        for p in Producto.objects.filter(pk__in=ids_int).select_related('categoria')
    }

    items = []
    subtotal = Decimal('0.00')
    eliminados = []

    for str_pid, cantidad in list(carrito.items()):
        try:
            int_pid = int(str_pid)
        except (ValueError, TypeError):
            continue

        prod = prods_db.get(int_pid)
        if prod is None or not prod.activo or (prod.categoria and not prod.categoria.activa):
            nombre_descartado = prod.nombre if prod else f"ID {str_pid}"
            eliminados.append(nombre_descartado)
            continue

        linea = prod.precio_venta * cantidad
        subtotal += linea
        items.append({'producto': prod, 'cantidad': cantidad, 'subtotal': linea})

    iva = (subtotal * IVA).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    total = subtotal + iva
    return items, subtotal, iva, total, eliminados


def _respuesta_pdf(venta):
    respuesta = HttpResponse(generar_factura_pdf(venta), content_type='application/pdf')
    respuesta['Content-Disposition'] = f'inline; filename="factura_{venta.venta_id}.pdf"'
    return respuesta


@login_required
@cajero_o_admin_required
def pos(request):
    productos = (
        Producto.objects.filter(activo=True, categoria__activa=True)
        .select_related('categoria')
        .order_by('categoria__nombre', 'nombre')
    )

    categorias_dict = {}
    for p in productos:
        cat_nom = p.categoria.nombre.strip().title() if p.categoria else 'General'
        if cat_nom not in categorias_dict:
            categorias_dict[cat_nom] = []
        categorias_dict[cat_nom].append(p)

    categorias_resumen = [
        {'nombre': cat_nom, 'cantidad': len(prods)}
        for cat_nom, prods in categorias_dict.items()
    ]

    carrito = _obtener_carrito(request)
    items, subtotal, iva, total, eliminados = _resumen_carrito(carrito)

    # Notificar y limpiar ítems retirados silenciosamente
    if eliminados:
        for item_nom in eliminados:
            for pid, p in list(carrito.items()):
                # Quitar del carrito de sesión
                pass
        # Filtrar el carrito en sesión para que solo contenga los activos válidos
        ids_validos = {str(item['producto'].producto_id) for item in items}
        carrito_limpio = {k: v for k, v in carrito.items() if str(k) in ids_validos}
        request.session['carrito'] = carrito_limpio
        messages.warning(
            request,
            f'Aviso: Los siguientes productos fueron retirados de tu carrito porque ya no están disponibles: {", ".join(eliminados)}.'
        )

    pos_token = request.session.get('pos_token')
    if not pos_token:
        pos_token = uuid.uuid4().hex
        request.session['pos_token'] = pos_token

    contexto = {
        'productos': productos,
        'categorias_dict': categorias_dict,
        'categorias_resumen': categorias_resumen,
        'items': items,
        'subtotal': subtotal,
        'iva': iva,
        'total': total,
        'clientes': Cliente.objects.filter(activo=True).order_by('nombre', 'apellido'),
        'iva_porcentaje': int(IVA * 100),
        'ultima_venta_id': request.session.get('ultima_venta_id'),
        'pos_token': pos_token,
        'efectivo_maximo': EFECTIVO_MAXIMO,
    }
    return render(request, 'pos/pos.html', contexto)


@login_required
@cajero_o_admin_required
def agregar_carrito(request):
    if request.method == 'POST':
        producto = get_object_or_404(
            Producto.objects.select_related('categoria'),
            pk=request.POST.get('producto_id'),
            activo=True,
            categoria__activa=True,
        )
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
def actualizar_cantidad_carrito(request):
    if request.method == 'POST':
        producto_id = str(request.POST.get('producto_id'))
        accion = request.POST.get('accion')
        producto = get_object_or_404(
            Producto.objects.select_related('categoria'),
            pk=producto_id,
            activo=True,
            categoria__activa=True,
        )
        carrito = _obtener_carrito(request)
        actual = carrito.get(producto_id, 0)

        if accion == 'incrementar':
            if actual + 1 > producto.cantidad:
                messages.error(
                    request,
                    f'Inventario insuficiente de "{producto.nombre}" (disponible: {producto.cantidad}).',
                )
            else:
                carrito[producto_id] = actual + 1
        elif accion == 'decrementar':
            if actual - 1 <= 0:
                carrito.pop(producto_id, None)
            else:
                carrito[producto_id] = actual - 1
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
def limpiar_carrito(request):
    if request.method == 'POST':
        request.session['carrito'] = {}
        messages.info(request, 'El carrito ha sido vaciado.')
    return redirect('pos')


@login_required
@cajero_o_admin_required
def procesar_venta(request):
    if request.method != 'POST':
        return redirect('pos')

    token_enviado = (request.POST.get('pos_token') or '').strip()
    token_sesion = request.session.get('pos_token')

    # Validación de idempotencia contra doble submit
    if not token_enviado or token_enviado != token_sesion:
        # Comprobar si ya fue registrada en BD con esta clave
        if token_enviado:
            venta_previa = Venta.objects.filter(clave_idempotencia=token_enviado).first()
            if venta_previa:
                messages.warning(
                    request,
                    f'Esta solicitud ya fue procesada anteriormente (Factura #{venta_previa.venta_id}).'
                )
                return _respuesta_pdf(venta_previa)
        messages.error(request, 'La solicitud de cobro ya expiró o no es válida. Intente nuevamente.')
        return redirect('pos')

    carrito = _obtener_carrito(request)
    if not carrito:
        messages.error(request, 'El carrito está vacío. Agrega productos antes de procesar el pago.')
        return redirect('pos')

    cliente_id = request.POST.get('cliente_id')
    cliente = get_object_or_404(Cliente, pk=cliente_id, activo=True)

    # Validar pago en efectivo y cambio
    efectivo_raw = (request.POST.get('efectivo_recibido') or '').strip().replace('$', '')
    try:
        efectivo_recibido = Decimal(efectivo_raw).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        messages.error(request, 'Debe ingresar un monto válido de efectivo recibido.')
        return redirect('pos')

    if efectivo_recibido <= Decimal('0.00'):
        messages.error(request, 'El efectivo recibido debe ser mayor a $0.00.')
        return redirect('pos')

    if efectivo_recibido > EFECTIVO_MAXIMO:
        messages.error(
            request,
            f'El monto máximo en efectivo permitido por transacción es de ${EFECTIVO_MAXIMO:.2f}.'
        )
        return redirect('pos')

    try:
        with transaction.atomic():
            # 1. Comprobación de idempotencia concurrente en BD con bloqueo
            venta_existente = Venta.objects.select_for_update().filter(clave_idempotencia=token_enviado).first()
            if venta_existente:
                messages.warning(request, f'La venta #{venta_existente.venta_id} ya fue registrada.')
                return _respuesta_pdf(venta_existente)

            # 2. Bloquear filas de productos en BD con select_for_update() en orden determinista
            ids_productos = sorted([int(pid) for pid in carrito.keys()])
            productos_bloqueados = {
                p.producto_id: p
                for p in Producto.objects.select_for_update().select_related('categoria').filter(producto_id__in=ids_productos)
            }

            # 3. Revalidar stock y estado activo de todos los productos y categoría
            items_procesar = []
            subtotal_recalculado = Decimal('0.00')

            for str_pid, cant in carrito.items():
                int_pid = int(str_pid)
                prod = productos_bloqueados.get(int_pid)

                if not prod:
                    raise ValueError('Uno de los productos seleccionados ya no existe en el catálogo.')

                if not prod.activo or (prod.categoria and not prod.categoria.activa):
                    raise ValueError(f'El producto "{prod.nombre}" ha sido desactivado y no está disponible para la venta.')

                if prod.cantidad < cant:
                    raise ValueError(
                        f'Inventario insuficiente para "{prod.nombre}". '
                        f'Stock actual disponible: {prod.cantidad}, cantidad requerida: {cant}.'
                    )

                item_subtotal = (Decimal(str(prod.precio_venta)) * Decimal(str(cant))).quantize(
                    Decimal('0.01'), rounding=ROUND_HALF_UP
                )
                subtotal_recalculado += item_subtotal
                items_procesar.append({
                    'producto': prod,
                    'cantidad': cant,
                    'precio_unitario': prod.precio_venta,
                    'subtotal': item_subtotal,
                })

            iva_recalculado = (subtotal_recalculado * IVA).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            total_recalculado = subtotal_recalculado + iva_recalculado

            if efectivo_recibido < total_recalculado:
                raise ValueError(
                    f'Efectivo insuficiente. Total a pagar: ${total_recalculado:.2f}, '
                    f'Efectivo recibido: ${efectivo_recibido:.2f}.'
                )

            cambio_calculado = (efectivo_recibido - total_recalculado).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            # 4. Crear la cabecera de la venta
            venta = Venta.objects.create(
                cliente=cliente,
                usuario=request.user,
                fecha=timezone.now(),
                subtotal=subtotal_recalculado,
                iva=iva_recalculado,
                efectivo_recibido=efectivo_recibido,
                cambio=cambio_calculado,
                clave_idempotencia=token_enviado,
                estado='PAGADA',
            )

            # 5. Crear detalles de venta y descontar inventario registrando kardex
            for item in items_procesar:
                prod = item['producto']
                cant = item['cantidad']

                DetalleVenta.objects.create(
                    venta=venta,
                    producto=prod,
                    precio_unitario=item['precio_unitario'],
                    cantidad=cant,
                    subtotal=item['subtotal'],
                )

                prod.cantidad -= cant
                prod.version += 1
                prod.save(update_fields=['cantidad', 'version'])

                MovimientoInventario.objects.create(
                    producto=prod,
                    usuario=request.user,
                    tipo='VENTA',
                    delta=-cant,
                    stock_resultante=prod.cantidad,
                    motivo=f'Venta POS #{venta.venta_id}',
                    referencia_id=venta.venta_id,
                )

            # 6. Al tener éxito, vaciar carrito y rotar token de idempotencia
            request.session['carrito'] = {}
            request.session['ultima_venta_id'] = venta.venta_id
            request.session['pos_token'] = uuid.uuid4().hex

    except ValueError as e:
        messages.error(request, str(e))
        return redirect('pos')
    except Exception:
        logger.exception('Error crítico durante la transacción de procesar_venta:')
        messages.error(request, 'Ocurrió un error inesperado al procesar la venta. Verifique los datos e intente de nuevo.')
        return redirect('pos')

    # Enviar factura por correo si el checklist está activado
    enviar_correo = bool(request.POST.get('enviar_correo'))
    if enviar_correo and cliente.correo:
        from config.servicios_email import enviar_factura_venta_correo
        ok, msg_correo = enviar_factura_venta_correo(venta)
        if ok:
            messages.success(request, f'Venta #{venta.venta_id} registrada. Factura enviada a {cliente.correo}.')
        else:
            messages.warning(request, f'Venta #{venta.venta_id} registrada. (Aviso de correo: {msg_correo})')
    elif enviar_correo and not cliente.correo:
        messages.info(request, f'Venta #{venta.venta_id} registrada. (El cliente no tiene correo electrónico registrado).')
    else:
        messages.success(request, f'Venta #{venta.venta_id} registrada correctamente.')

    return _respuesta_pdf(venta)


@login_required
@admin_required
@require_POST
def anular_venta(request, venta_id):
    """
    Anula una venta del POS exclusivamente por un Administrador y con motivo obligatorio.
    Restaura el stock de los productos vendidos y registra el movimiento en kardex y auditoría.
    """
    motivo = (request.POST.get('motivo') or '').strip()
    if len(motivo) < 10:
        messages.error(request, 'El motivo de anulación es obligatorio y debe contener al menos 10 caracteres explicativos.')
        return redirect('reportes')

    try:
        with transaction.atomic():
            venta = Venta.objects.select_for_update().get(pk=venta_id)
            if venta.estado == 'ANULADA':
                messages.warning(request, f'La venta #{venta_id} ya se encuentra anulada.')
                return redirect('reportes')

            fecha_venta_local = timezone.localtime(venta.fecha).date() if timezone.is_aware(venta.fecha) else venta.fecha.date()
            if fecha_venta_local != timezone.localdate():
                messages.error(
                    request,
                    f'No se puede anular la venta #{venta_id} porque pertenece a una fecha anterior ({fecha_venta_local.strftime("%d/%m/%Y")}). Solo se permiten anulaciones del mismo día.'
                )
                return redirect('reportes')

            venta.estado = 'ANULADA'
            venta.anulada_por = request.user
            venta.anulada_en = timezone.now()
            venta.motivo_anulacion = motivo
            venta.save(update_fields=['estado', 'anulada_por', 'anulada_en', 'motivo_anulacion'])

            # Restaurar stock de cada detalle bloqueando productos en orden determinista por producto_id (anti-deadlock)
            detalles_raw = list(venta.detalles.select_related('producto'))
            detalles_con_prod = [d for d in detalles_raw if getattr(d, 'producto_id', None)]
            detalles_con_prod.sort(key=lambda d: d.producto_id)
            ids_prod = sorted({d.producto_id for d in detalles_con_prod})

            productos_lock_qs = Producto.objects.select_for_update().filter(producto_id__in=ids_prod).order_by('producto_id')
            productos_lock = {p.producto_id: p for p in productos_lock_qs}

            for detalle in detalles_con_prod:
                prod = productos_lock.get(detalle.producto_id) or Producto.objects.select_for_update().get(pk=detalle.producto_id)
                prod.cantidad += detalle.cantidad
                prod.version += 1
                prod.save(update_fields=['cantidad', 'version'])

                MovimientoInventario.objects.create(
                    producto=prod,
                    usuario=request.user,
                    tipo='ANULACION',
                    delta=detalle.cantidad,
                    stock_resultante=prod.cantidad,
                    motivo=f'Anulación Factura #{venta.venta_id}: {motivo}',
                    referencia_id=venta.venta_id,
                )

            registrar_auditoria(
                usuario=request.user,
                accion='ANULAR_VENTA',
                entidad='Venta',
                entidad_id=venta.venta_id,
                valor_previo={'estado': 'PAGADA'},
                valor_nuevo={'estado': 'ANULADA', 'motivo': motivo, 'anulada_por': request.user.username},
                ip=request.META.get('REMOTE_ADDR'),
            )

        messages.success(request, f'Venta #{venta_id} anulada correctamente. Se ha restituido el inventario.')
    except Exception:
        logger.exception(f'Error al anular venta #{venta_id}:')
        messages.error(request, 'Ocurrió un error inesperado al anular la venta.')

    return redirect('reportes')


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

    if not getattr(request.user, 'es_admin', False):
        fecha_venta_local = (
            timezone.localtime(venta.fecha).date()
            if timezone.is_aware(venta.fecha)
            else venta.fecha.date()
        )
        if venta.usuario_id != getattr(request.user, 'usuario_id', None) or fecha_venta_local != timezone.localdate():
            messages.error(
                request,
                'Solo tienes permiso para visualizar las facturas de las ventas realizadas por ti durante el día de hoy.',
            )
            return redirect('reportes')

    return _respuesta_pdf(venta)


def _sanitizar_celda_planilla(valor):
    """Previene inyección de fórmulas (CSV/Excel Macro Injection) al abrir reportes en hojas de cálculo."""
    texto = str(valor if valor is not None else '')
    if texto.startswith(('=', '+', '-', '@', '\t', '\r')):
        return f"'{texto}"
    return texto


def _construir_transacciones_reporte(request):
    """
    Construye de forma centralizada la lista de transacciones y totales para la vista
    de reportes y para las exportaciones a CSV y Excel.
    Si el usuario es Cajero (no Administrador), fuerza la consulta únicamente a sus
    propias operaciones realizadas durante el día actual.
    """
    es_admin = getattr(request.user, 'es_admin', False)
    tipo_filtro = request.GET.get('tipo', 'todos')
    if tipo_filtro not in ('todos', 'ventas', 'rentas'):
        tipo_filtro = 'todos'

    if es_admin:
        fecha_inicio_str = request.GET.get('fecha_inicio')
        fecha_fin_str = request.GET.get('fecha_fin')
        usuario_id_str = request.GET.get('usuario')
    else:
        hoy_str = timezone.localdate().isoformat()
        fecha_inicio_str = hoy_str
        fecha_fin_str = hoy_str
        uid_actual = getattr(request.user, 'usuario_id', None)
        usuario_id_str = str(uid_actual) if uid_actual is not None else ''

    ventas_qs = Venta.objects.select_related('cliente', 'usuario', 'anulada_por').prefetch_related('detalles__producto').order_by('-fecha')
    rentas_qs = Renta.objects.select_related('cliente', 'usuario').prefetch_related('detalles__equipo').order_by('-fecha')

    ventas_qs = _filtrar_por_fechas(ventas_qs, fecha_inicio_str, fecha_fin_str)
    rentas_qs = _filtrar_por_fechas(rentas_qs, fecha_inicio_str, fecha_fin_str)

    if not es_admin:
        uid_actual = getattr(request.user, 'usuario_id', None)
        ventas_qs = ventas_qs.filter(usuario_id=uid_actual)
        rentas_qs = rentas_qs.filter(usuario_id=uid_actual)
    elif usuario_id_str and usuario_id_str.isdigit():
        uid = int(usuario_id_str)
        ventas_qs = ventas_qs.filter(usuario_id=uid)
        rentas_qs = rentas_qs.filter(usuario_id=uid)

    transacciones = []
    total_ventas = Decimal('0.00')
    total_rentas = Decimal('0.00')

    if tipo_filtro in ['todos', 'ventas']:
        agregado_v = ventas_qs.exclude(estado='ANULADA').aggregate(
            total=Coalesce(Sum(F('subtotal') + F('iva'), output_field=DecimalField()), Decimal('0.00'))
        )['total'] or Decimal('0.00')
        total_ventas = agregado_v.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        for v in ventas_qs:
            items_nombres = []
            for d in v.detalles.all():
                prod_nombre = d.producto.nombre if d.producto else "Producto"
                items_nombres.append(f"{d.cantidad}x {prod_nombre}")
            articulos = ", ".join(items_nombres) if items_nombres else "Venta de mostrador"
            monto_v = (v.subtotal + v.iva).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            es_anulada = (v.estado == 'ANULADA')

            fecha_local = timezone.localtime(v.fecha) if timezone.is_aware(v.fecha) else v.fecha
            es_mismo_dia = (fecha_local.date() == timezone.localdate())

            transacciones.append({
                'ticket': f"V-{v.venta_id}",
                'fecha': v.fecha,
                'fecha_str': fecha_local.strftime('%d/%m/%Y %I:%M %p'),
                'usuario': v.usuario.username if v.usuario else "Sistema",
                'cliente': f"{v.cliente.nombre} {v.cliente.apellido}" if v.cliente else "Cliente General",
                'concepto': articulos,
                'total': monto_v,
                'tipo': 'Venta POS',
                'estado': 'Anulada' if es_anulada else 'Pagada',
                'es_anulada': es_anulada,
                'es_mismo_dia': es_mismo_dia,
                'es_venta': True,
                'venta_id': v.venta_id,
                'renta_id': None,
                'motivo_anulacion': v.motivo_anulacion,
                'anulada_por': v.anulada_por.username if v.anulada_por else None,
            })

    if tipo_filtro in ['todos', 'rentas']:
        agregado_r = rentas_qs.aggregate(
            total=Coalesce(Sum('total'), Decimal('0.00'))
        )['total'] or Decimal('0.00')
        total_rentas = agregado_r.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        for r in rentas_qs:
            detalles = list(r.detalles.all())
            if detalles:
                equipos_info = []
                for det in detalles:
                    equipo_nom = det.equipo.nombre if (det and det.equipo) else "Equipo"
                    minutos = (det.tiempo_de_renta or 0) + (det.tiempo_agregado or 0)
                    equipos_info.append(f"Renta {equipo_nom} ({minutos} min)")
                concepto = ", ".join(equipos_info)
            else:
                concepto = "Renta de Equipo"
            monto_r = r.total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            transacciones.append({
                'ticket': f"R-{r.renta_id}",
                'fecha': r.fecha,
                'fecha_str': timezone.localtime(r.fecha).strftime('%d/%m/%Y %I:%M %p'),
                'usuario': r.usuario.username if r.usuario else "Sistema",
                'cliente': f"{r.cliente.nombre} {r.cliente.apellido}" if r.cliente else "Cliente General",
                'concepto': concepto,
                'total': monto_r,
                'tipo': 'Renta de Equipo',
                'estado': r.estado_de_pago.title(),
                'es_anulada': False,
                'es_venta': False,
                'venta_id': None,
                'renta_id': r.renta_id,
            })

    transacciones.sort(key=lambda x: x['fecha'], reverse=True)
    return {
        'transacciones': transacciones,
        'total_ventas': total_ventas,
        'total_rentas': total_rentas,
        'fecha_inicio_str': fecha_inicio_str,
        'fecha_fin_str': fecha_fin_str,
        'tipo_filtro': tipo_filtro,
        'usuario_id_str': usuario_id_str,
    }


@login_required
@cajero_o_admin_required
def reportes(request):
    datos = _construir_transacciones_reporte(request)
    transacciones = datos['transacciones']
    total_ventas = datos['total_ventas']
    total_rentas = datos['total_rentas']
    fecha_inicio_str = datos['fecha_inicio_str']
    fecha_fin_str = datos['fecha_fin_str']
    tipo_filtro = datos['tipo_filtro']
    usuario_id_str = datos['usuario_id_str']

    total_global = total_ventas + total_rentas
    num_transacciones = len([t for t in transacciones if not t.get('es_anulada')])
    ticket_promedio = (total_global / Decimal(num_transacciones)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if num_transacciones else Decimal('0.00')

    pct_ventas = int((total_ventas / total_global * 100)) if total_global > 0 else 0
    pct_rentas = 100 - pct_ventas if total_global > 0 else 0

    paginator = Paginator(transacciones, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    if getattr(request.user, 'es_admin', False):
        usuarios = Usuario.objects.filter(activo=True).order_by('username')
    else:
        usuarios = Usuario.objects.filter(pk=getattr(request.user, 'usuario_id', None))

    return render(request, 'reportes.html', {
        'transacciones': page_obj,
        'page_obj': page_obj,
        'total_recaudado_global': total_global,
        'total_ventas': total_ventas,
        'total_rentas': total_rentas,
        'num_transacciones': num_transacciones,
        'ticket_promedio': ticket_promedio,
        'pct_ventas': pct_ventas,
        'pct_rentas': pct_rentas,
        'fecha_inicio': fecha_inicio_str or '',
        'fecha_fin': fecha_fin_str or '',
        'tipo_filtro': tipo_filtro,
        'usuario_id_seleccionado': int(usuario_id_str) if (usuario_id_str and usuario_id_str.isdigit()) else '',
        'usuarios': usuarios,
        'ahora': timezone.now(),
    })


@login_required
@admin_required
def reportes_exportar_csv(request):
    datos = _construir_transacciones_reporte(request)
    transacciones = datos['transacciones']

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="reporte_ingresos_{timezone.localdate()}.csv"'
    response.write('\ufeff')

    writer = csv.writer(response)
    writer.writerow(['Ticket', 'Tipo de Ingreso', 'Estado', 'Fecha y Hora', 'Cajero / Atendido Por', 'Cliente', 'Detalle / Concepto', 'Total'])
    for f in transacciones:
        writer.writerow([
            _sanitizar_celda_planilla(f['ticket']),
            _sanitizar_celda_planilla(f['tipo']),
            _sanitizar_celda_planilla(f.get('estado', 'Pagada')),
            _sanitizar_celda_planilla(f['fecha_str']),
            _sanitizar_celda_planilla(f['usuario']),
            _sanitizar_celda_planilla(f['cliente']),
            _sanitizar_celda_planilla(f['concepto']),
            f"${f['total']}",
        ])

    return response


@login_required
@admin_required
def reportes_exportar_excel(request):
    datos = _construir_transacciones_reporte(request)
    transacciones = datos['transacciones']

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Reporte de Ingresos"

    headers = ['N° Ticket', 'Tipo de Ingreso', 'Estado', 'Fecha y Hora', 'Cajero / Atendido Por', 'Cliente', 'Detalle / Concepto', 'Total ($)']
    ws.append(headers)

    header_font = Font(name='Calibri', size=11, bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='2C1E16', end_color='2C1E16', fill_type='solid')
    header_alignment = Alignment(horizontal='center', vertical='center')

    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment

    for row_idx, f in enumerate(transacciones, start=2):
        ws.cell(row=row_idx, column=1, value=_sanitizar_celda_planilla(f['ticket']))
        ws.cell(row=row_idx, column=2, value=_sanitizar_celda_planilla(f['tipo']))
        ws.cell(row=row_idx, column=3, value=_sanitizar_celda_planilla(f.get('estado', 'Pagada')))
        ws.cell(row=row_idx, column=4, value=_sanitizar_celda_planilla(f['fecha_str']))
        ws.cell(row=row_idx, column=5, value=_sanitizar_celda_planilla(f['usuario']))
        ws.cell(row=row_idx, column=6, value=_sanitizar_celda_planilla(f['cliente']))
        ws.cell(row=row_idx, column=7, value=_sanitizar_celda_planilla(f['concepto']))
        total_cell = ws.cell(row=row_idx, column=8, value=float(f['total']))
        total_cell.number_format = '$#,##0.00'

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="reporte_ingresos_{timezone.localdate()}.xlsx"'
    wb.save(response)
    return response
