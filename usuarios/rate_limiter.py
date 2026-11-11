import math
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import LoginIntento, obtener_ip_cliente


@dataclass
class EstadoLogin:
    """Resultado del limitador: todo lo que la vista necesita para responder."""
    intentos: int
    intentos_restantes: int
    bloqueado: bool
    segundos_restantes: int


def formatear_espera(segundos: int) -> str:
    """Convierte segundos a un texto legible: '45 s', '2 min', '1 min 30 s'."""
    segundos = max(0, int(segundos))
    minutos, resto = divmod(segundos, 60)
    if minutos and resto:
        return f"{minutos} min {resto} s"
    if minutos:
        return f"{minutos} min"
    return f"{resto} s"


class LoginRateLimiter:
    """
    Limitador de intentos de inicio de sesión persistente en base de datos.

    Misma lógica que el de la API: al alcanzar el máximo de intentos se bloquea y el tiempo
    de espera crece de forma exponencial en bloqueos consecutivos (hasta un tope). Al vivir
    en la base de datos, es compartido por todos los workers y sobrevive a reinicios.
    """

    def __init__(
        self,
        max_attempts: Optional[int] = None,
        lockout_seconds: Optional[int] = None,
        max_lockout_seconds: Optional[int] = None,
        lockout_multiplier: Optional[float] = None,
        escalation_window: Optional[int] = None,
    ):
        self._max_attempts = max_attempts
        self._lockout_seconds = lockout_seconds
        self._max_lockout_seconds = max_lockout_seconds
        self._lockout_multiplier = lockout_multiplier
        self._escalation_window = escalation_window

    # Los valores se leen de settings en cada uso para respetar la configuración vigente.
    @property
    def max_attempts(self) -> int:
        if self._max_attempts is not None:
            return self._max_attempts
        return int(getattr(settings, 'LOGIN_MAX_ATTEMPTS', 5))

    @property
    def lockout_seconds(self) -> int:
        if self._lockout_seconds is not None:
            return self._lockout_seconds
        return int(getattr(settings, 'LOGIN_LOCKOUT_SECONDS', 60))

    @property
    def max_lockout_seconds(self) -> int:
        if self._max_lockout_seconds is not None:
            return self._max_lockout_seconds
        return int(getattr(settings, 'LOGIN_MAX_LOCKOUT_SECONDS', 900))

    @property
    def lockout_multiplier(self) -> float:
        if self._lockout_multiplier is not None:
            return self._lockout_multiplier
        return float(getattr(settings, 'LOGIN_LOCKOUT_MULTIPLIER', 2.0))

    @property
    def escalation_window(self) -> int:
        if self._escalation_window is not None:
            return self._escalation_window
        return int(getattr(settings, 'LOGIN_ESCALATION_RESET_SECONDS', 1800))

    def get_client_key(self, request, username: str) -> str:
        """Clave única: IP real del cliente + nombre de usuario normalizado."""
        client_ip = obtener_ip_cliente(request) or "127.0.0.1"
        clean_username = (username or "").strip().lower()
        return f"{client_ip}:{clean_username}"[:150]

    def _estado(self, registro: Optional[LoginIntento], ahora) -> EstadoLogin:
        if registro is None:
            return EstadoLogin(0, self.max_attempts, False, 0)
        if registro.bloqueado_hasta and registro.bloqueado_hasta > ahora:
            segundos = max(1, math.ceil((registro.bloqueado_hasta - ahora).total_seconds()))
            return EstadoLogin(registro.intentos, 0, True, segundos)
        return EstadoLogin(
            registro.intentos,
            max(0, self.max_attempts - registro.intentos),
            False,
            0,
        )

    def _normalizar_vencimientos(self, registro: LoginIntento, ahora) -> None:
        """Aplica los reinicios por bloqueo cumplido y por ventana de escalamiento."""
        if registro.bloqueado_hasta and registro.bloqueado_hasta <= ahora:
            registro.intentos = 0
            registro.bloqueado_hasta = None
        if (ahora - registro.ultimo_intento).total_seconds() > self.escalation_window:
            registro.bloqueos = 0

    def estado(self, key: str) -> EstadoLogin:
        """Estado actual de una clave (sin modificar nada)."""
        ahora = timezone.now()
        registro = LoginIntento.objects.filter(clave=key).first()
        if registro is not None and registro.bloqueado_hasta and registro.bloqueado_hasta <= ahora:
            # Un bloqueo ya cumplido equivale a un ciclo nuevo de intentos.
            return EstadoLogin(0, self.max_attempts, False, 0)
        return self._estado(registro, ahora)

    def registrar_fallo(self, key: str) -> EstadoLogin:
        """
        Registra exactamente un intento fallido. Si alcanza el máximo, bloquea con espera
        progresiva. Es atómico entre procesos (select_for_update).
        """
        with transaction.atomic():
            ahora = timezone.now()
            registro, _ = LoginIntento.objects.select_for_update().get_or_create(
                clave=key,
                defaults={'ultimo_intento': ahora},
            )
            self._normalizar_vencimientos(registro, ahora)

            registro.intentos += 1
            registro.ultimo_intento = ahora

            if registro.intentos >= self.max_attempts:
                registro.bloqueos += 1
                exponente = max(0, registro.bloqueos - 1)
                espera = int(
                    min(
                        self.lockout_seconds * (self.lockout_multiplier ** exponente),
                        self.max_lockout_seconds,
                    )
                )
                registro.bloqueado_hasta = ahora + timedelta(seconds=espera)

            registro.save()
            return self._estado(registro, ahora)

    def registrar_exito(self, key: str) -> None:
        """Un inicio de sesión correcto reinicia por completo el estado de la clave."""
        LoginIntento.objects.filter(clave=key).delete()

    def bloqueo_activo_por_ip(self, client_ip: str) -> Optional[EstadoLogin]:
        """Bloqueo vigente más largo asociado a una IP (para mostrarlo al recargar el login)."""
        if not client_ip:
            return None
        ahora = timezone.now()
        registro = (
            LoginIntento.objects.filter(clave__startswith=f"{client_ip}:", bloqueado_hasta__gt=ahora)
            .order_by('-bloqueado_hasta')
            .first()
        )
        if registro is None:
            return None
        return self._estado(registro, ahora)

    def reset_all(self) -> None:
        """Limpia todos los registros (útil para pruebas)."""
        LoginIntento.objects.all().delete()


login_rate_limiter = LoginRateLimiter()
