from functools import wraps
from django.contrib import messages
from django.shortcuts import redirect


def admin_required(view_func):
    """
    Permite el acceso únicamente a usuarios con rol de Administrador.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not getattr(request.user, 'es_admin', False):
            messages.error(request, 'No tienes permisos de Administrador para acceder a este módulo.')
            return redirect('inicio')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def cajero_o_admin_required(view_func):
    """
    Permite el acceso a Cajeros y Administradores.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        es_admin = getattr(request.user, 'es_admin', False)
        es_cajero = getattr(request.user, 'es_cajero', False)
        if not (es_admin or es_cajero):
            messages.error(request, 'No tienes permisos de Cajero o Administrador para acceder a este módulo.')
            return redirect('inicio')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def asistente_o_admin_required(view_func):
    """
    Permite el acceso a Asistentes y Administradores (por ejemplo, para el Módulo de Revisiones).
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        es_admin = getattr(request.user, 'es_admin', False)
        es_asistente = getattr(request.user, 'es_asistente', False)
        if not (es_admin or es_asistente):
            messages.error(request, 'No tienes permisos de Asistente o Administrador para acceder a este módulo.')
            return redirect('inicio')
        return view_func(request, *args, **kwargs)
    return _wrapped_view
