from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from usuarios.decorators import admin_required
from .forms import CategoriaForm
from .models import Categoria


@login_required
@admin_required
def categoria_list(request):
    categorias = Categoria.objects.all().order_by('categoria_id')
    return render(request, 'categorias/categorias.html', {'categorias': categorias})


@login_required
@admin_required
def categoria_create(request):
    if request.method == 'POST':
        form = CategoriaForm(request.POST)
        if form.is_valid():
            form.save()
    return redirect('categorias')


@login_required
@admin_required
def categoria_edit(request):
    if request.method == 'POST':
        categoria = get_object_or_404(Categoria, pk=request.POST.get('categoria_id'))
        form = CategoriaForm(request.POST, instance=categoria)
        if form.is_valid():
            form.save()
    return redirect('categorias')


@login_required
@admin_required
def categoria_toggle(request):
    if request.method == 'POST':
        categoria = get_object_or_404(Categoria, pk=request.POST.get('categoria_id'))
        categoria.activa = not categoria.activa
        categoria.save(update_fields=['activa'])
    return redirect('categorias')

