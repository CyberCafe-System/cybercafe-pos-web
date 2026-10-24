from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from .decorators import admin_required
from .forms import UsuarioCreateForm, UsuarioEditForm
from .models import Rol, Usuario
from .validators import validar_password_intermedia


@login_required
@admin_required
def usuario_list(request):
    usuarios_qs = Usuario.objects.select_related('rol').all().order_by('usuario_id')
    paginator = Paginator(usuarios_qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    roles = Rol.objects.all().order_by('nombre')
    return render(
        request,
        'usuarios/usuarios.html',
        {
            'usuarios': page_obj,
            'page_obj': page_obj,
            'roles': roles,
        },
    )


@login_required
@admin_required
def usuario_create(request):
    if request.method == 'POST':
        form = UsuarioCreateForm(request.POST)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, 'Usuario creado correctamente.')
            except Exception as e:
                messages.error(request, f'Error al crear el usuario: {e}')
        else:
            for field, error_list in form.errors.items():
                for err in error_list:
                    messages.error(request, err)
    return redirect('usuarios')


@login_required
@admin_required
def usuario_edit(request):
    if request.method == 'POST':
        usuario = get_object_or_404(Usuario, pk=request.POST.get('usuario_id'))
        form = UsuarioEditForm(request.POST, instance=usuario)
        if form.is_valid():
            try:
                usuario_guardado = form.save(commit=False)
                # Cambiar contraseña si se proporcionó una nueva
                nueva_password = request.POST.get('nueva_password', '').strip()
                if nueva_password:
                    try:
                        validar_password_intermedia(nueva_password, user=usuario_guardado)
                        usuario_guardado.set_password(nueva_password)
                    except ValidationError as e:
                        for msg in e.messages:
                            messages.error(request, f'Contraseña inválida: {msg}')
                        return redirect('usuarios')
                usuario_guardado.save()
                messages.success(request, 'Usuario actualizado correctamente.')
            except Exception as e:
                messages.error(request, f'Error al actualizar el usuario: {e}')
        else:
            for field, error_list in form.errors.items():
                for err in error_list:
                    messages.error(request, err)
    return redirect('usuarios')


@login_required
@admin_required
def usuario_toggle(request):
    if request.method == 'POST':
        usuario = get_object_or_404(Usuario, pk=request.POST.get('usuario_id'))
        # Prevenir auto-deshabilitación
        if usuario.usuario_id == request.user.usuario_id:
            messages.error(request, 'No puedes desactivar tu propia cuenta mientras estás en sesión.')
            return redirect('usuarios')
        usuario.activo = not usuario.activo
        usuario.save(update_fields=['activo'])
        estado = 'activado' if usuario.activo else 'desactivado'
        messages.success(request, f'Usuario {usuario.username} {estado} correctamente.')
    return redirect('usuarios')
