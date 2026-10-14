from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import UsuarioCreateForm, UsuarioEditForm
from .models import Rol, Usuario


@login_required
def usuario_list(request):
    usuarios = Usuario.objects.select_related('rol').all().order_by('usuario_id')
    roles = Rol.objects.all().order_by('nombre')
    return render(request, 'usuarios/usuarios.html', {'usuarios': usuarios, 'roles': roles})


@login_required
def usuario_create(request):
    if request.method == 'POST':
        form = UsuarioCreateForm(request.POST)
        if form.is_valid():
            form.save()
        else:
            for error in form.errors.values():
                messages.error(request, error.as_text().lstrip('* '))
    return redirect('usuarios')


@login_required
def usuario_edit(request):
    if request.method == 'POST':
        usuario = get_object_or_404(Usuario, pk=request.POST.get('usuario_id'))
        form = UsuarioEditForm(request.POST, instance=usuario)
        if form.is_valid():
            form.save()
        else:
            for error in form.errors.values():
                messages.error(request, error.as_text().lstrip('* '))
    return redirect('usuarios')


@login_required
def usuario_toggle(request):
    if request.method == 'POST':
        usuario = get_object_or_404(Usuario, pk=request.POST.get('usuario_id'))
        usuario.activo = not usuario.activo
        usuario.save(update_fields=['activo'])
    return redirect('usuarios')
