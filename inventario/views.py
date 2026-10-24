from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from django.core.paginator import Paginator

from categorias.models import Categoria
from usuarios.decorators import admin_required

from .forms import ProductoForm
from .models import Producto


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
                producto = form.save()
                messages.success(request, f'Producto "{producto.nombre}" registrado exitosamente con imagen optimizada.')
            except Exception as e:
                messages.error(request, f'Error al registrar el producto: {e}')
        else:
            for error in form.errors.values():
                messages.error(request, error.as_text().lstrip('* '))
    return redirect('inventario')


@login_required
@admin_required
def producto_edit(request):
    if request.method == 'POST':
        producto = get_object_or_404(Producto, pk=request.POST.get('producto_id'))
        form = ProductoForm(request.POST, request.FILES, instance=producto)
        if form.is_valid():
            try:
                producto = form.save()
                messages.success(request, f'Producto "{producto.nombre}" actualizado correctamente.')
            except Exception as e:
                messages.error(request, f'Error al actualizar el producto: {e}')
        else:
            for error in form.errors.values():
                messages.error(request, error.as_text().lstrip('* '))
    return redirect('inventario')


@login_required
@admin_required
def producto_toggle(request):
    if request.method == 'POST':
        producto = get_object_or_404(Producto, pk=request.POST.get('producto_id'))
        producto.activo = not producto.activo
        producto.save(update_fields=['activo'])
        estado = 'activado' if producto.activo else 'desactivado'
        messages.success(request, f'Producto "{producto.nombre}" {estado} correctamente.')
    return redirect('inventario')


