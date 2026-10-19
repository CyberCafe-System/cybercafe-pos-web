from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect


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
