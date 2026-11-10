from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect

from .models import obtener_ip_cliente


class RealClientIPMiddleware:
    """
    Middleware que normaliza request.META['REMOTE_ADDR'] con la IP real del dispositivo
    cliente cuando el servidor corre en una VPS detrás de un proxy inverso (Nginx,
    Cloudflare, Caddy, Apache, Docker).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ip_real = obtener_ip_cliente(request)
        if ip_real:
            request.META['REMOTE_ADDR'] = ip_real
            request.client_ip = ip_real
        return self.get_response(request)


class BloqueoAsistenteWebMiddleware:
    """
    Middleware que asegura que ningún usuario con rol Asistente pueda navegar en la web.
    Si un asistente posee una sesión activa en la web, la sesión se cierra automáticamente
    y se le redirige al login con un mensaje explicativo.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and getattr(request.user, 'es_asistente', False):
            logout(request)
            messages.warning(
                request,
                'El rol Asistente solo tiene acceso mediante la aplicación móvil.',
            )
            return redirect('login')
        return self.get_response(request)
