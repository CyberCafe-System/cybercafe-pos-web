import ipaddress

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils import timezone


class Rol(models.Model):
    rol_id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=255)
    descripcion = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'roles'
        verbose_name = 'rol'
        verbose_name_plural = 'roles'

    @property
    def es_asistente(self):
        return self.rol_id == 3 or (self.nombre or '').strip().lower() == 'asistente'

    def __str__(self):
        return self.nombre


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError('El nombre de usuario es obligatorio.')
        for field in ('nombre', 'correo', 'rol'):
            if extra_fields.get(field) is None:
                raise ValueError(f'El campo {field} es obligatorio.')

        username = self.model.normalize_username(username).strip().lower()
        rol = extra_fields.pop('rol')
        user = self.model(username=username, **extra_fields)
        if isinstance(rol, Rol):
            user.rol = rol
        else:
            user.rol_id = rol
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        if extra_fields.get('is_superuser') is False:
            raise ValueError('Un superusuario debe tener is_superuser=True.')

        extra_fields['is_superuser'] = True
        extra_fields['activo'] = True
        return self.create_user(username, password, **extra_fields)


class Usuario(AbstractBaseUser):
    usuario_id = models.AutoField(primary_key=True)
    rol = models.ForeignKey(
        Rol,
        db_column='rol_id',
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name='usuarios',
    )
    nombre = models.CharField(max_length=50)
    username = models.CharField(max_length=50, unique=True)
    correo = models.EmailField(max_length=75)
    password = models.CharField(max_length=255)
    is_superuser = models.BooleanField(default=False)
    last_login = models.DateTimeField(blank=True, null=True)
    activo = models.BooleanField(default=True)

    objects = UsuarioManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['nombre', 'correo', 'rol']

    class Meta:
        managed = False
        db_table = 'usuarios'
        verbose_name = 'usuario'
        verbose_name_plural = 'usuarios'

    def _obtener_nombre_rol(self):
        cached_rol = self._state.fields_cache.get('rol') if hasattr(self, '_state') else None
        if cached_rol is None and self.rol_id:
            try:
                cached_rol = self.rol
            except Exception:
                cached_rol = None
        return (getattr(cached_rol, 'nombre', '') or '').strip().lower()

    def save(self, *args, **kwargs):
        if self.username:
            self.username = self.username.strip().lower()
        es_admin_rol = (self.rol_id == 1) or (self._obtener_nombre_rol() in ('admin', 'administrador'))
        self.is_superuser = bool(es_admin_rol)
        super().save(*args, **kwargs)

    @property
    def is_active(self):
        return self.activo

    @is_active.setter
    def is_active(self, value):  # type: ignore
        self.activo = value

    @property
    def is_staff(self):
        return self.is_active and self.es_admin

    @property
    def es_admin(self):
        if self.rol_id == 1:
            return True
        return self._obtener_nombre_rol() in ('admin', 'administrador')

    @property
    def es_cajero(self):
        if self.rol_id == 2:
            return True
        return self._obtener_nombre_rol() == 'cajero'

    @property
    def es_asistente(self):
        if self.rol_id == 3:
            return True
        return self._obtener_nombre_rol() == 'asistente'

    def get_full_name(self):
        return self.nombre

    def get_short_name(self):
        return self.nombre

    def get_user_permissions(self, obj=None):
        return set()

    def get_group_permissions(self, obj=None):
        return set()

    def get_all_permissions(self, obj=None):
        return set()

    def has_perm(self, perm, obj=None):
        return self.is_active and self.es_admin

    def has_module_perms(self, app_label):
        return self.is_active and self.es_admin

    def __str__(self):
        return self.username


class Auditoria(models.Model):
    auditoria_id = models.AutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario,
        db_column='usuario_id',
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name='auditorias',
        verbose_name='Usuario Responsable',
    )
    fecha = models.DateTimeField(auto_now_add=True, verbose_name='Fecha y Hora')
    accion = models.CharField(max_length=50, verbose_name='Acción')
    entidad = models.CharField(max_length=50, verbose_name='Entidad Afectada')
    entidad_id = models.IntegerField(verbose_name='ID de Entidad')
    valor_previo = models.JSONField(null=True, blank=True, verbose_name='Valor Previo')
    valor_nuevo = models.JSONField(null=True, blank=True, verbose_name='Valor Nuevo')
    origen = models.CharField(max_length=10, default='WEB', verbose_name='Origen')
    ip = models.CharField(max_length=45, null=True, blank=True, verbose_name='Dirección IP')

    class Meta:
        managed = False
        db_table = 'auditoria'
        verbose_name = 'registro de auditoría'
        verbose_name_plural = 'registros de auditoría'
        ordering = ['-fecha']

    def __str__(self):
        fecha_txt = self.fecha.strftime('%d/%m/%Y %H:%M') if self.fecha else ''
        usuario_txt = self.usuario.username if self.usuario else 'Sistema'
        return f"[{fecha_txt}] {usuario_txt}: {self.accion} {self.entidad} #{self.entidad_id}"

    @property
    def datos_previos(self) -> dict:
        val = self.valor_previo
        if not val:
            return {}
        if isinstance(val, dict):
            return val
        if isinstance(val, str):
            try:
                import json
                parsed = json.loads(val)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    @property
    def datos_nuevos(self) -> dict:
        val = self.valor_nuevo
        if not val:
            return {}
        if isinstance(val, dict):
            return val
        if isinstance(val, str):
            try:
                import json
                parsed = json.loads(val)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    @property
    def motivo_operacion(self) -> str | None:
        return self.datos_nuevos.get('motivo') or self.datos_previos.get('motivo')

    @property
    def nombre_referencia(self) -> str | None:
        """Retorna el nombre o identificador humano del recurso si existe en los payloads."""
        return (
            self.datos_nuevos.get('nombre')
            or self.datos_previos.get('nombre')
            or self.datos_nuevos.get('username')
            or self.datos_previos.get('username')
        )

    ETIQ_ACCIONES = {
        'CREAR_USUARIO': 'Crear usuario',
        'MODIFICAR_USUARIO': 'Modificar usuario',
        'ACTIVAR_USUARIO': 'Activar usuario',
        'DESACTIVAR_USUARIO': 'Desactivar usuario',
        'TOGGLE_USUARIO': 'Cambiar estado de usuario',
        'CREAR_EQUIPO': 'Crear equipo',
        'MODIFICAR_EQUIPO': 'Modificar equipo',
        'HABILITAR_EQUIPO': 'Habilitar equipo',
        'ELIMINAR_EQUIPO': 'Eliminar equipo',
        'ACTIVAR_EQUIPO': 'Activar equipo',
        'DESACTIVAR_EQUIPO': 'Desactivar equipo',
        'CREAR_PRODUCTO': 'Crear producto',
        'MODIFICAR_PRODUCTO': 'Modificar producto',
        'AJUSTAR_STOCK': 'Ajustar stock',
        'ACTIVAR_PRODUCTO': 'Activar producto',
        'DESACTIVAR_PRODUCTO': 'Desactivar producto',
        'TOGGLE_PRODUCTO': 'Cambiar estado de producto',
        'CREAR_CATEGORIA': 'Crear categoría',
        'MODIFICAR_CATEGORIA': 'Modificar categoría',
        'ACTIVAR_CATEGORIA': 'Activar categoría',
        'DESACTIVAR_CATEGORIA': 'Desactivar categoría',
        'CREAR_CLIENTE': 'Crear cliente',
        'MODIFICAR_CLIENTE': 'Modificar cliente',
        'ACTIVAR_CLIENTE': 'Activar cliente',
        'DESACTIVAR_CLIENTE': 'Desactivar cliente',
        'CREAR_COMPONENTE': 'Crear componente',
        'MODIFICAR_COMPONENTE': 'Modificar componente',
        'ACTIVAR_COMPONENTE': 'Activar componente',
        'DESACTIVAR_COMPONENTE': 'Desactivar componente',
        'CREAR_RENTA': 'Iniciar renta',
        'EXTENDER_RENTA': 'Extender renta',
        'CREAR_REVISION': 'Registrar revisión',
        'MODIFICAR_REVISION': 'Modificar revisión',
        'ANULAR_VENTA': 'Anular venta',
        'REINICIAR_REVISION': 'Revocar revisión',
    }

    ETIQ_CAMPOS = {
        'rol_id': 'Rol',
        'correo': 'Correo electrónico',
        'username': 'Usuario',
        'nombre': 'Nombre',
        'estado': 'Estado',
        'tarifa': 'Tarifa por hora',
        'tarifa_por_hora': 'Tarifa por hora',
        'precio_venta': 'Precio de venta',
        'precio_compra': 'Precio de compra',
        'cantidad': 'Cantidad',
        'stock': 'Stock',
        'delta': 'Ajuste de unidades',
        'activo': 'Estado',
        'anulada_por': 'Anulada por',
    }

    ETIQ_ESTADOS = {
        'DISPONIBLE': 'Disponible',
        'DANIOS_MENORES': 'Daños menores',
        'DEFECTUOSO': 'Defectuoso',
        'EN_MANTENIMIENTO': 'En mantenimiento',
        'REQUIERE_REEMPLAZO': 'Requiere reemplazo',
        'PAGADA': 'Pagada',
        'COMPLETADA': 'Completada',
        'ANULADA': 'Anulada',
    }

    @property
    def accion_legible(self) -> str:
        raw = (self.accion or '').strip().upper()
        if raw in self.ETIQ_ACCIONES:
            return self.ETIQ_ACCIONES[raw]
        return raw.replace('_', ' ').capitalize()

    @classmethod
    def _formatear_valor_campo(cls, clave: str, valor):
        if valor is None:
            return '—'
        if isinstance(valor, bool):
            return 'Activo' if valor else 'Inactivo'
        if clave in ('precio_venta', 'precio_compra', 'tarifa', 'tarifa_por_hora', 'total', 'subtotal', 'iva', 'costo'):
            try:
                return f"${float(valor):.2f}"
            except Exception:
                return str(valor)
        if clave == 'rol_id':
            roles = {1: 'Administrador', 2: 'Cajero', 3: 'Asistente'}
            return roles.get(int(valor) if str(valor).isdigit() else valor, f"Rol #{valor}")
        if 'password' in clave.lower():
            return '••••••••'
        val_str = str(valor)
        if val_str.upper() in cls.ETIQ_ESTADOS:
            return cls.ETIQ_ESTADOS[val_str.upper()]
        return val_str

    @property
    def comparativa_cambios(self) -> list[dict]:
        """
        Retorna la lista de atributos modificados o creados con nombres legibles:
        [{'campo': 'Nombre', 'anterior': 'X', 'nuevo': 'Y', 'cambio': True}]
        """
        prev = self.datos_previos
        nuev = self.datos_nuevos
        if not prev and not nuev:
            return []

        todas_claves = list(dict.fromkeys(list(prev.keys()) + list(nuev.keys())))
        cambios = []
        for clave in todas_claves:
            if clave == 'motivo':
                continue
            v_ant = prev.get(clave)
            v_nue = nuev.get(clave)
            formato_ant = self._formatear_valor_campo(clave, v_ant)
            formato_nue = self._formatear_valor_campo(clave, v_nue)

            campo_nombre = self.ETIQ_CAMPOS.get(clave, clave.replace('_', ' ').capitalize())
            es_diferente = (v_ant != v_nue)

            cambios.append({
                'clave': clave,
                'campo': campo_nombre,
                'anterior': formato_ant,
                'nuevo': formato_nue,
                'es_cambio': es_diferente and (clave in prev) and (clave in nuev),
                'es_alta': (clave not in prev and clave in nuev),
                'es_baja': (clave in prev and clave not in nuev),
            })
        return cambios

    @property
    def resumen_visual(self) -> list[dict]:
        """Genera chips/pills visuales limpios para mostrar en la celda de la tabla."""
        badges = []
        nuev = self.datos_nuevos
        prev = self.datos_previos

        # 1. Delta de Kardex
        if 'delta' in nuev:
            try:
                d = int(nuev['delta'])
                signo = '+' if d > 0 else ''
                color = 'success' if d > 0 else 'danger'
                icono = 'bi-box-arrow-in-down' if d > 0 else 'bi-box-arrow-up'
                badges.append({'icono': icono, 'texto': f"{signo}{d} unid.", 'color': color})
            except Exception:
                badges.append({'icono': 'bi-arrow-left-right', 'texto': f"Delta: {nuev['delta']}", 'color': 'secondary'})

        # 2. Stock resultante
        if 'stock' in nuev:
            badges.append({'icono': 'bi-boxes', 'texto': f"Stock: {nuev['stock']}", 'color': 'primary'})

        # 3. Diferencias directas clave
        for campo in ('rol_id', 'estado', 'cantidad', 'tarifa', 'precio_venta'):
            if campo in prev and campo in nuev and prev[campo] != nuev[campo]:
                v_a = self._formatear_valor_campo(campo, prev[campo])
                v_n = self._formatear_valor_campo(campo, nuev[campo])
                c_nom = campo.replace('_id', '').replace('_', ' ').capitalize()
                badges.append({
                    'icono': 'bi-arrow-right-short',
                    'texto': f"{c_nom}: {v_a} → {v_n}",
                    'color': 'warning text-dark',
                })

        # 4. Si fue creación pura
        if not prev and nuev:
            if 'precio_venta' in nuev:
                badges.append({'icono': 'bi-tag', 'texto': f"${nuev['precio_venta']}", 'color': 'success'})
            if 'cantidad' in nuev and 'delta' not in nuev:
                badges.append({'icono': 'bi-box-seam', 'texto': f"Stock: {nuev['cantidad']}", 'color': 'secondary'})
            if 'tarifa' in nuev:
                badges.append({'icono': 'bi-cash', 'texto': f"${nuev['tarifa']}/hr", 'color': 'success'})
            if 'rol_id' in nuev:
                r_nom = self._formatear_valor_campo('rol_id', nuev['rol_id'])
                badges.append({'icono': 'bi-person-badge', 'texto': r_nom, 'color': 'info text-dark'})

        # 5. Activo
        if 'activo' in nuev:
            act = nuev['activo']
            badges.append({
                'icono': 'bi-check-circle' if act else 'bi-x-circle',
                'texto': 'Habilitado' if act else 'Inhabilitado',
                'color': 'success' if act else 'secondary',
            })

        return badges


class LoginIntento(models.Model):
    """
    Estado persistente del limitador de intentos de inicio de sesión web.
    Se guarda en base de datos para que todos los workers compartan el mismo contador
    y el estado sobreviva a reinicios del servicio.
    """
    clave = models.CharField(max_length=150, unique=True)
    intentos = models.PositiveIntegerField(default=0)
    bloqueos = models.PositiveIntegerField(default=0)
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)
    ultimo_intento = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'web_login_intentos'
        verbose_name = 'intento de inicio de sesión'
        verbose_name_plural = 'intentos de inicio de sesión'

    def __str__(self):
        return f"{self.clave} ({self.intentos} intentos)"


_CABECERAS_IP_PROXY = (
    'HTTP_CF_CONNECTING_IP',
    'HTTP_TRUE_CLIENT_IP',
    'HTTP_X_REAL_IP',
    'HTTP_X_FORWARDED_FOR',
    'HTTP_X_CLIENT_IP',
    'HTTP_CLIENT_IP',
    'HTTP_X_FORWARDED',
    'HTTP_FORWARDED_FOR',
    'HTTP_FORWARDED',
    'REMOTE_ADDR',
)


def _limpiar_ip_individual(valor: str) -> str | None:
    """Limpia y valida un candidato a dirección IPv4 o IPv6."""
    if not valor:
        return None
    candidato = valor.strip().strip('"').strip("'")
    if not candidato or candidato.lower() == 'unknown':
        return None
    if candidato.lower().startswith('for='):
        candidato = candidato[4:].strip().strip('"').strip("'")
    # Formato [IPv6]:puerto
    if candidato.startswith('[') and ']' in candidato:
        candidato = candidato[1:candidato.index(']')]
    # Formato IPv4:puerto
    elif candidato.count(':') == 1 and '.' in candidato:
        candidato = candidato.split(':', 1)[0]
    try:
        ip_obj = ipaddress.ip_address(candidato)
        if getattr(ip_obj, 'ipv4_mapped', None):
            ip_obj = ip_obj.ipv4_mapped
        return str(ip_obj)[:45]
    except ValueError:
        return None


def obtener_ip_cliente(request_o_meta) -> str | None:
    """
    Obtiene la IP real del dispositivo cliente, funcionando tanto en entorno local
    como en un VPS detrás de Nginx, Cloudflare, Caddy, Apache o Docker.
    Prioriza IPs públicas válidas, luego IPs de red privada (LAN) y por último loopback.
    """
    if request_o_meta is None:
        return None

    if isinstance(request_o_meta, str):
        limpia = _limpiar_ip_individual(request_o_meta)
        return limpia or request_o_meta.strip()[:45] or None

    meta = getattr(request_o_meta, 'META', None)
    if meta is None and isinstance(request_o_meta, dict):
        meta = request_o_meta
    if not isinstance(meta, dict):
        return None

    candidatas_publicas = []
    candidatas_privadas = []
    candidatas_loopback = []

    for header in _CABECERAS_IP_PROXY:
        raw_val = meta.get(header)
        if not raw_val or not isinstance(raw_val, str):
            continue
        # X-Forwarded-For o Forwarded pueden traer múltiples IPs separadas por coma o punto y coma
        partes = [p for bloque in raw_val.split(';') for p in bloque.split(',')]
        for parte in partes:
            ip_limpia = _limpiar_ip_individual(parte)
            if not ip_limpia:
                continue
            try:
                ip_obj = ipaddress.ip_address(ip_limpia)
                if ip_obj.is_loopback or ip_obj.is_unspecified:
                    candidatas_loopback.append(ip_limpia)
                elif ip_obj.is_private or ip_obj.is_link_local:
                    candidatas_privadas.append(ip_limpia)
                else:
                    candidatas_publicas.append(ip_limpia)
            except ValueError:
                continue

    if candidatas_publicas:
        return candidatas_publicas[0]
    if candidatas_privadas:
        return candidatas_privadas[0]
    if candidatas_loopback:
        return candidatas_loopback[0]
    return None


def registrar_auditoria(usuario, accion: str, entidad: str, entidad_id: int, valor_previo=None, valor_nuevo=None, origen='WEB', ip=None):
    """
    Registra un evento append-only en la tabla de auditoría.
    Registra en log de advertencia si ocurre un fallo para no bloquear operaciones principales.
    """
    try:
        usuario_instancia = usuario if isinstance(usuario, Usuario) else None
        ip_normalizada = obtener_ip_cliente(ip) if ip is not None else None
        Auditoria.objects.create(
            usuario=usuario_instancia,
            accion=accion,
            entidad=entidad,
            entidad_id=entidad_id,
            valor_previo=valor_previo,
            valor_nuevo=valor_nuevo,
            origen=origen,
            ip=ip_normalizada,
        )
    except Exception as exc:
        if exc.__class__.__name__ == 'DatabaseOperationForbidden':
            return
        import logging
        logging.getLogger(__name__).warning(
            "No se pudo registrar evento de auditoría (%s en %s#%s)",
            accion, entidad, entidad_id, exc_info=True,
        )
