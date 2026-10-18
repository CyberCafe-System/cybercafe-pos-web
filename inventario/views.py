from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from categorias.models import Categoria
from usuarios.decorators import asistente_o_admin_required

from .forms import ProductoForm
from .models import Producto


@login_required
@asistente_o_admin_required
def producto_list(request):
    productos = Producto.objects.select_related('categoria').all().order_by('producto_id')
    categorias = Categoria.objects.filter(activa=True).order_by('nombre')
    return render(
        request,
        'inventario/inventario.html',
        {'productos': productos, 'categorias': categorias},
    )


@login_required
@asistente_o_admin_required
def producto_create(request):
    if request.method == 'POST':
        form = ProductoForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
    return redirect('inventario')


@login_required
@asistente_o_admin_required
def producto_edit(request):
    if request.method == 'POST':
        producto = get_object_or_404(Producto, pk=request.POST.get('producto_id'))
        form = ProductoForm(request.POST, request.FILES, instance=producto)
        if form.is_valid():
            form.save()
    return redirect('inventario')


@login_required
@asistente_o_admin_required
def producto_toggle(request):
    if request.method == 'POST':
        producto = get_object_or_404(Producto, pk=request.POST.get('producto_id'))
        producto.activo = not producto.activo
        producto.save(update_fields=['activo'])
    return redirect('inventario')


