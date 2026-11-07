from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from usuarios.decorators import admin_required
from usuarios.models import registrar_auditoria
from .forms import CategoriaForm
from .models import Categoria


@login_required
@admin_required
def categoria_list(request):
    categorias_qs = Categoria.objects.all().order_by('categoria_id')
    paginator = Paginator(categorias_qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(
        request,
        'categorias/categorias.html',
        {
            'categorias': page_obj,
            'page_obj': page_obj,
        },
    )


@login_required
@admin_required
def categoria_create(request):
    if request.method == 'POST':
        form = CategoriaForm(request.POST)
        if form.is_valid():
            cat = form.save()
            registrar_auditoria(
                usuario=request.user,
                accion='CREAR_CATEGORIA',
                entidad='Categoria',
                entidad_id=cat.categoria_id,
                valor_nuevo={'nombre': cat.nombre, 'activa': cat.activa},
                ip=request.META.get('REMOTE_ADDR'),
            )
            messages.success(request, f'Categoría "{cat.nombre}" registrada correctamente.')
        else:
            for error in form.errors.values():
                messages.error(request, error.as_text().lstrip('* '))
    return redirect('categorias')


@login_required
@admin_required
def categoria_edit(request):
    if request.method == 'POST':
        categoria = get_object_or_404(Categoria, pk=request.POST.get('categoria_id'))
        nombre_prev = categoria.nombre
        form = CategoriaForm(request.POST, instance=categoria)
        if form.is_valid():
            cat = form.save()
            registrar_auditoria(
                usuario=request.user,
                accion='MODIFICAR_CATEGORIA',
                entidad='Categoria',
                entidad_id=cat.categoria_id,
                valor_previo={'nombre': nombre_prev},
                valor_nuevo={'nombre': cat.nombre},
                ip=request.META.get('REMOTE_ADDR'),
            )
            messages.success(request, f'Categoría "{cat.nombre}" actualizada correctamente.')
        else:
            for error in form.errors.values():
                messages.error(request, error.as_text().lstrip('* '))
    return redirect('categorias')


@login_required
@admin_required
def categoria_toggle(request):
    if request.method == 'POST':
        categoria = get_object_or_404(Categoria, pk=request.POST.get('categoria_id'))
        activa_prev = categoria.activa
        categoria.activa = not categoria.activa
        categoria.save(update_fields=['activa'])
        registrar_auditoria(
            usuario=request.user,
            accion='ACTIVAR_CATEGORIA' if categoria.activa else 'DESACTIVAR_CATEGORIA',
            entidad='Categoria',
            entidad_id=categoria.categoria_id,
            valor_previo={'activo': activa_prev},
            valor_nuevo={'activo': categoria.activa, 'nombre': categoria.nombre},
            ip=request.META.get('REMOTE_ADDR'),
        )
        estado_txt = 'activada' if categoria.activa else 'desactivada'
        messages.success(request, f'Categoría "{categoria.nombre}" {estado_txt} correctamente.')
    return redirect('categorias')
