import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from .decorators import admin_required
from .forms import UsuarioCreateForm, UsuarioEditForm, WebAuthenticationForm
from .models import Auditoria, Rol, Usuario, registrar_auditoria, obtener_ip_cliente
from .rate_limiter import formatear_espera, login_rate_limiter
from .validators import validar_password_intermedia

logger = logging.getLogger(__name__)


def _ids_roles_administrador():
    """IDs de los roles que el modelo considera administradores (mismo criterio que Usuario.es_admin)."""
    ids = {1}
    for rol_id, nombre in Rol.objects.values_list('rol_id', 'nombre'):
        if (nombre or '').strip().lower() in ('admin', 'administrador'):
            ids.add(rol_id)
    return ids


def _bloquear_administradores(ids_roles_admin):
    """
    Bloquea (SELECT ... FOR UPDATE) todas las filas de administradores en orden
    determinista. Actúa como mutex para serializar cualquier cambio de rol o de
    estado que pueda alterar la cantidad de administradores activos y así evitar
    interbloqueos y degradaciones simultáneas.
    """
    return list(
        Usuario.objects.select_for_update()
        .filter(rol_id__in=ids_roles_admin)
        .order_by('usuario_id')
    )


_USERNAMES_NORMALIZADOS = False


def _normalizar_usernames_minusculas():
    """Garantiza que todos los nombres de usuario en la base de datos estén guardados en minúsculas."""
    global _USERNAMES_NORMALIZADOS
    if _USERNAMES_NORMALIZADOS:
        return
    try:
        for u in Usuario.objects.all():
            uname_clean = (u.username or '').strip().lower()
            if u.username != uname_clean and uname_clean:
                Usuario.objects.filter(pk=u.pk).update(username=uname_clean)
        _USERNAMES_NORMALIZADOS = True
    except Exception:
        logger.debug('No se pudo ejecutar la normalización automática de usernames a minúsculas', exc_info=True)


class PosLoginView(LoginView):
    """
    Login web con un único limitador de intentos (persistente en base de datos).
    Toda la información de intentos restantes y tiempo de espera proviene de ese limitador.
    """
    template_name = 'login.html'
    authentication_form = WebAuthenticationForm
    redirect_authenticated_user = True

    @staticmethod
    def _mensaje_bloqueo(segundos):
        return f"Demasiados intentos fallidos. Tiempo estimado de espera: {formatear_espera(segundos)}."

    def _respuesta_bloqueada(self, segundos, form=None):
        """Respuesta 429 con el tiempo real restante (sin evaluar credenciales)."""
        if form is None:
            form = self.get_form_class()(request=self.request)
        context = self.get_context_data(
            form=form,
            lockout_error=self._mensaje_bloqueo(segundos),
            wait_seconds=segundos,
        )
        response = self.render_to_response(context)
        response.status_code = 429
        response['Retry-After'] = str(segundos)
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault('max_intentos', login_rate_limiter.max_attempts)
        # Al recargar la página (GET) se sigue mostrando el bloqueo vigente de esta IP.
        if 'lockout_error' not in context and self.request.method == 'GET':
            estado = login_rate_limiter.bloqueo_activo_por_ip(obtener_ip_cliente(self.request))
            if estado is not None:
                context['lockout_error'] = self._mensaje_bloqueo(estado.segundos_restantes)
                context['wait_seconds'] = estado.segundos_restantes
        return context

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'POST' and not request.user.is_authenticated:
            username = request.POST.get('username', '')
            client_key = login_rate_limiter.get_client_key(request, username)
            estado = login_rate_limiter.estado(client_key)
            if estado.bloqueado:
                return self._respuesta_bloqueada(estado.segundos_restantes)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        username = form.cleaned_data.get('username', '')
        login_rate_limiter.registrar_exito(login_rate_limiter.get_client_key(self.request, username))
        return super().form_valid(form)

    def form_invalid(self, form):
        username = self.request.POST.get('username', '')
        client_key = login_rate_limiter.get_client_key(self.request, username)
        estado = login_rate_limiter.registrar_fallo(client_key)
        if estado.bloqueado:
            return self._respuesta_bloqueada(estado.segundos_restantes, form=form)
        return self.render_to_response(
            self.get_context_data(form=form, intentos_restantes=estado.intentos_restantes)
        )


@login_required
@admin_required
def usuario_list(request):
    _normalizar_usernames_minusculas()
    q = (request.GET.get('q') or '').strip()
    estado = (request.GET.get('estado') or 'todos').strip().lower()
    rol_id = (request.GET.get('rol') or '').strip()

    usuarios_qs = Usuario.objects.select_related('rol').all().order_by('usuario_id')

    if q:
        usuarios_qs = usuarios_qs.filter(
            Q(username__icontains=q)
            | Q(nombre__icontains=q)
            | Q(correo__icontains=q)
        )

    if estado == 'activos':
        usuarios_qs = usuarios_qs.filter(activo=True)
    elif estado == 'inactivos':
        usuarios_qs = usuarios_qs.filter(activo=False)

    if rol_id.isdigit():
        usuarios_qs = usuarios_qs.filter(rol_id=int(rol_id))

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
            'q': q,
            'estado': estado,
            'rol_id': rol_id,
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
    if request.method != 'POST':
        return redirect('usuarios')

    try:
        with transaction.atomic():
            # Mutex: serializa cambios de rol/estado entre administradores.
            ids_roles_admin = _ids_roles_administrador()
            admins_bloqueados = _bloquear_administradores(ids_roles_admin)

            usuario = get_object_or_404(
                Usuario.objects.select_for_update().select_related('rol'),
                pk=request.POST.get('usuario_id'),
            )

            # Un administrador no puede cambiar su propio rol (evita auto-degradarse).
            rol_solicitado = request.POST.get('rol')
            if (
                usuario.usuario_id == request.user.usuario_id
                and rol_solicitado
                and str(rol_solicitado) != str(usuario.rol_id)
            ):
                messages.error(
                    request,
                    'No puedes cambiar tu propio rol. Solicita a otro administrador que realice el cambio.',
                )
                return redirect('usuarios')

            valor_previo = {
                'username': usuario.username,
                'nombre': usuario.nombre,
                'correo': usuario.correo,
                'rol_id': usuario.rol_id,
            }
            era_admin_activo = usuario.activo and usuario.rol_id in ids_roles_admin

            form = UsuarioEditForm(request.POST, instance=usuario)
            if form.is_valid():
                usuario_guardado = form.save(commit=False)
                nuevo_es_admin = usuario_guardado.rol_id in ids_roles_admin

                # Garantizar al menos un administrador activo en el sistema.
                if era_admin_activo and not nuevo_es_admin:
                    otros_admins_activos = [
                        u for u in admins_bloqueados
                        if u.usuario_id != usuario.usuario_id and u.activo
                    ]
                    if not otros_admins_activos:
                        messages.error(
                            request,
                            'No puedes quitar el rol de Administrador al único Administrador activo del sistema.',
                        )
                        return redirect('usuarios')

                nueva_password = request.POST.get('nueva_password', '').strip()
                if nueva_password:
                    validar_password_intermedia(nueva_password, user=usuario_guardado)
                    usuario_guardado.set_password(nueva_password)
                usuario_guardado.save()

                registrar_auditoria(
                    usuario=request.user,
                    accion='MODIFICAR_USUARIO',
                    entidad='Usuario',
                    entidad_id=usuario_guardado.usuario_id,
                    valor_previo=valor_previo,
                    valor_nuevo={
                        'username': usuario_guardado.username,
                        'nombre': usuario_guardado.nombre,
                        'correo': usuario_guardado.correo,
                        'rol_id': usuario_guardado.rol_id,
                    },
                    ip=request.META.get('REMOTE_ADDR'),
                )
                messages.success(request, 'Usuario actualizado correctamente.')
            else:
                for field, error_list in form.errors.items():
                    for err in error_list:
                        messages.error(request, err)
    except ValidationError as e:
        for msg in e.messages:
            messages.error(request, f'Contraseña inválida: {msg}')
    except Http404:
        raise
    except Exception:
        logger.exception('Error al actualizar el usuario')
        messages.error(request, 'Ocurrió un error al actualizar el usuario. Intenta nuevamente.')
    return redirect('usuarios')


@login_required
@admin_required
def usuario_toggle(request):
    if request.method != 'POST':
        return redirect('usuarios')

    try:
        with transaction.atomic():
            # Mutex: serializa cambios de rol/estado entre administradores.
            ids_roles_admin = _ids_roles_administrador()
            admins_bloqueados = _bloquear_administradores(ids_roles_admin)

            usuario = get_object_or_404(
                Usuario.objects.select_for_update().select_related('rol'),
                pk=request.POST.get('usuario_id'),
            )

            # Prevenir auto-deshabilitación
            if usuario.usuario_id == request.user.usuario_id:
                messages.error(request, 'No puedes desactivar tu propia cuenta mientras estás en sesión.')
                return redirect('usuarios')

            # Garantizar al menos un administrador activo en el sistema.
            if usuario.activo and usuario.rol_id in ids_roles_admin:
                otros_admins_activos = [
                    u for u in admins_bloqueados
                    if u.usuario_id != usuario.usuario_id and u.activo
                ]
                if not otros_admins_activos:
                    messages.error(request, 'No puedes desactivar al único Administrador activo del sistema.')
                    return redirect('usuarios')

            estado_prev = usuario.activo
            usuario.activo = not usuario.activo
            usuario.save(update_fields=['activo'])
            estado = 'activado' if usuario.activo else 'desactivado'

            registrar_auditoria(
                usuario=request.user,
                accion='ACTIVAR_USUARIO' if usuario.activo else 'DESACTIVAR_USUARIO',
                entidad='Usuario',
                entidad_id=usuario.usuario_id,
                valor_previo={'activo': estado_prev},
                valor_nuevo={'activo': usuario.activo, 'username': usuario.username},
                ip=request.META.get('REMOTE_ADDR'),
            )
        messages.success(request, f'Usuario {usuario.username} {estado} correctamente.')
    except Http404:
        raise
    except Exception:
        logger.exception('Error al cambiar estado del usuario')
        messages.error(request, 'Ocurrió un error al actualizar el estado del usuario.')
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
