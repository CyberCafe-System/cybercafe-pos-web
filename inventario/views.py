import logging
import re
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from categorias.models import Categoria
from usuarios.decorators import admin_required
from usuarios.models import registrar_auditoria

from .forms import ProductoEditForm, ProductoForm
from .models import MovimientoInventario, Producto

logger = logging.getLogger(__name__)


@login_required
@admin_required
def producto_list(request):
    productos_qs = Producto.objects.select_related('categoria').all().order_by('producto_id')
    paginator = Paginator(productos_qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    categorias = Categoria.objects.filter(activa=True).order_by('nombre')
    return render(
        request,
        'inventario/inventario.html',
        {
            'productos': page_obj,
            'page_obj': page_obj,
            'categorias': categorias,
        },
    )


@login_required
@admin_required
def producto_create(request):
    if request.method == 'POST':
        form = ProductoForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                tiene_imagen = bool(form.cleaned_data.get('imagen_upload'))
                with transaction.atomic():
                    producto = form.save()
                    # Registrar movimiento inicial de inventario en kardex si tiene stock inicial
                    if producto.cantidad > 0:
                        MovimientoInventario.objects.create(
                            producto=producto,
                            usuario=request.user,
                            tipo='ENTRADA',
                            delta=producto.cantidad,
                            stock_resultante=producto.cantidad,
                            motivo='Alta inicial de producto en catálogo',
                        )
                    registrar_auditoria(
                        usuario=request.user,
                        accion='CREAR_PRODUCTO',
                        entidad='Producto',
                        entidad_id=producto.producto_id,
                        valor_nuevo={
                            'nombre': producto.nombre,
                            'precio_venta': str(producto.precio_venta),
                            'cantidad': producto.cantidad,
                        },
                        ip=request.META.get('REMOTE_ADDR'),
                    )

                if tiene_imagen:
                    messages.success(request, f'Producto "{producto.nombre}" registrado exitosamente con imagen optimizada.')
                else:
                    messages.success(request, f'Producto "{producto.nombre}" registrado exitosamente.')
            except Exception:
                logger.exception('Error al registrar el producto')
                messages.error(request, 'Ocurrió un error al registrar el producto. Intenta nuevamente.')
        else:
            for error in form.errors.values():
                messages.error(request, error.as_text().lstrip('* '))
    return redirect('inventario')


@login_required
@admin_required
def producto_edit(request):
    if request.method == 'POST':
        producto_id = request.POST.get('producto_id')
        producto = get_object_or_404(Producto, pk=producto_id)
        valor_previo = {
            'nombre': producto.nombre,
            'precio_compra': str(producto.precio_compra),
            'precio_venta': str(producto.precio_venta),
            'categoria_id': producto.categoria_id,
        }

        form = ProductoEditForm(request.POST, request.FILES, instance=producto)
        if form.is_valid():
            try:
                with transaction.atomic():
                    prod_bloqueado = Producto.objects.select_for_update().get(pk=producto_id)

                    producto = form.save(commit=False)
                    producto.cantidad = prod_bloqueado.cantidad
                    producto.version = prod_bloqueado.version + 1
                    producto.save()

                    registrar_auditoria(
                        usuario=request.user,
                        accion='MODIFICAR_PRODUCTO',
                        entidad='Producto',
                        entidad_id=producto.producto_id,
                        valor_previo=valor_previo,
                        valor_nuevo={
                            'nombre': producto.nombre,
                            'precio_compra': str(producto.precio_compra),
                            'precio_venta': str(producto.precio_venta),
                            'categoria_id': producto.categoria_id,
                        },
                        ip=request.META.get('REMOTE_ADDR'),
                    )

                messages.success(request, f'Producto "{producto.nombre}" actualizado correctamente.')
            except Exception:
                logger.exception('Error al actualizar el producto')
                messages.error(request, 'Ocurrió un error al actualizar el producto. Intenta nuevamente.')
        else:
            for error in form.errors.values():
                messages.error(request, error.as_text().lstrip('* '))
    return redirect('inventario')


@login_required
@admin_required
def producto_ajustar_stock(request):
    """
    Ajuste manual atómico de existencias con justificación obligatoria y registro en kardex.
    """
    if request.method == 'POST':
        producto_id = request.POST.get('producto_id')
        motivo = (request.POST.get('motivo') or '').strip()
        tipo_ajuste = (request.POST.get('tipo_ajuste') or 'SUMA').strip().upper()
        raw_delta = (request.POST.get('delta') or '').strip()
        try:
            if tipo_ajuste not in ('SUMA', 'RESTA'):
                raise ValueError("Seleccione un tipo de ajuste válido (Sumar o Restar).")
            if not re.fullmatch(r'\d+', raw_delta):
                raise ValueError("Ingrese una cantidad entera positiva válida (solo números enteros, sin signos ni decimales).")
            cantidad_ajuste = int(raw_delta)
            if cantidad_ajuste <= 0:
                raise ValueError("La cantidad a ajustar debe ser mayor a 0.")
            if not motivo:
                raise ValueError("El motivo del ajuste de stock es obligatorio.")

            delta = cantidad_ajuste if tipo_ajuste == 'SUMA' else -cantidad_ajuste

            with transaction.atomic():
                prod = Producto.objects.select_for_update().get(pk=producto_id)
                nuevo_stock = prod.cantidad + delta
                if nuevo_stock < 0:
                    raise ValueError(f"El ajuste resultaría en stock negativo ({nuevo_stock}). Stock disponible: {prod.cantidad}.")

                stock_previo = prod.cantidad
                prod.cantidad = nuevo_stock
                prod.version += 1
                prod.save(update_fields=['cantidad', 'version'])

                MovimientoInventario.objects.create(
                    producto=prod,
                    usuario=request.user,
                    tipo='AJUSTE',
                    delta=delta,
                    stock_resultante=nuevo_stock,
                    motivo=motivo,
                )
                registrar_auditoria(
                    usuario=request.user,
                    accion='AJUSTAR_STOCK',
                    entidad='Producto',
                    entidad_id=prod.producto_id,
                    valor_previo={'stock': stock_previo},
                    valor_nuevo={'stock': nuevo_stock, 'delta': delta, 'motivo': motivo},
                    ip=request.META.get('REMOTE_ADDR'),
                )

            messages.success(request, f'Stock de "{prod.nombre}" ajustado exitosamente ({delta:+d}). Nuevo stock: {nuevo_stock}.')
        except ValueError as e:
            messages.error(request, str(e))
        except Exception:
            logger.exception('Error al ajustar stock')
            messages.error(request, 'Ocurrió un error inesperado al registrar el ajuste de stock.')

    return redirect('inventario')


@login_required
@admin_required
def producto_toggle(request):
    if request.method == 'POST':
        producto = get_object_or_404(Producto, pk=request.POST.get('producto_id'))
        producto.activo = not producto.activo
        producto.save(update_fields=['activo'])
        estado = 'activado' if producto.activo else 'desactivado'

        registrar_auditoria(
            usuario=request.user,
            accion='TOGGLE_PRODUCTO',
            entidad='Producto',
            entidad_id=producto.producto_id,
            valor_nuevo={'activo': producto.activo},
            ip=request.META.get('REMOTE_ADDR'),
        )
        messages.success(request, f'Producto "{producto.nombre}" {estado} correctamente.')
    return redirect('inventario')
