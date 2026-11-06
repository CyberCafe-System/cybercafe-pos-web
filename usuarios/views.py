import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from .decorators import admin_required
from .forms import UsuarioCreateForm, UsuarioEditForm
from .models import Auditoria, Rol, Usuario, registrar_auditoria
from .validators import validar_password_intermedia

logger = logging.getLogger(__name__)


@login_required
@admin_required
def usuario_list(request):
    usuarios_qs = Usuario.objects.select_related('rol').all().order_by('usuario_id')
    paginator = Paginator(usuarios_qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    current_uid = getattr(request.user, 'usuario_id', None)
    for u in page_obj:
        u.es_usuario_actual = (u.usuario_id == current_uid)
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
                nuevo_u = form.save()
                registrar_auditoria(
                    usuario=request.user,
                    accion='CREAR_USUARIO',
                    entidad='Usuario',
                    entidad_id=nuevo_u.usuario_id,
                    valor_nuevo={'username': nuevo_u.username, 'nombre': nuevo_u.nombre, 'rol_id': nuevo_u.rol_id},
                    ip=request.META.get('REMOTE_ADDR'),
                )
                messages.success(request, 'Usuario creado correctamente.')
            except Exception:
                logger.exception('Error al crear el usuario')
                messages.error(request, 'Ocurrió un error al crear el usuario. Intenta nuevamente.')
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
        valor_previo = {'nombre': usuario.nombre, 'correo': usuario.correo, 'rol_id': usuario.rol_id}
        form = UsuarioEditForm(request.POST, instance=usuario)
        if form.is_valid():
            try:
                usuario_guardado = form.save(commit=False)
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

                registrar_auditoria(
                    usuario=request.user,
                    accion='MODIFICAR_USUARIO',
                    entidad='Usuario',
                    entidad_id=usuario_guardado.usuario_id,
                    valor_previo=valor_previo,
                    valor_nuevo={'nombre': usuario_guardado.nombre, 'correo': usuario_guardado.correo, 'rol_id': usuario_guardado.rol_id},
                    ip=request.META.get('REMOTE_ADDR'),
                )
                messages.success(request, 'Usuario actualizado correctamente.')
            except Exception:
                logger.exception('Error al actualizar el usuario')
                messages.error(request, 'Ocurrió un error al actualizar el usuario. Intenta nuevamente.')
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

        # Garantizar al menos un administrador activo en el sistema
        if usuario.es_admin and usuario.activo:
            otros_admins = Usuario.objects.filter(activo=True, rol_id=1).exclude(pk=usuario.pk).count()
            if otros_admins == 0:
                messages.error(request, 'No puedes desactivar al único Administrador activo del sistema.')
                return redirect('usuarios')

        usuario.activo = not usuario.activo
        usuario.save(update_fields=['activo'])
        estado = 'activado' if usuario.activo else 'desactivado'

        registrar_auditoria(
            usuario=request.user,
            accion='TOGGLE_USUARIO',
            entidad='Usuario',
            entidad_id=usuario.usuario_id,
            valor_nuevo={'activo': usuario.activo},
            ip=request.META.get('REMOTE_ADDR'),
        )
        messages.success(request, f'Usuario {usuario.username} {estado} correctamente.')
    return redirect('usuarios')


@login_required
@admin_required
def auditoria_list(request):
    """
    Vista de registro de auditoría append-only accesible únicamente para Administradores.
    """
    auditorias_qs = Auditoria.objects.select_related('usuario').all().order_by('-fecha')

    entidad = request.GET.get('entidad', '').strip()
    if entidad:
        auditorias_qs = auditorias_qs.filter(entidad__iexact=entidad)

    usuario_id = request.GET.get('usuario', '').strip()
    if usuario_id and usuario_id.isdigit():
        auditorias_qs = auditorias_qs.filter(usuario_id=int(usuario_id))

    paginator = Paginator(auditorias_qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    usuarios = Usuario.objects.all().order_by('username')

    return render(request, 'usuarios/auditoria.html', {
        'auditorias': page_obj,
        'page_obj': page_obj,
        'usuarios': usuarios,
        'entidad_sel': entidad,
        'usuario_sel': int(usuario_id) if (usuario_id and usuario_id.isdigit()) else '',
    })
