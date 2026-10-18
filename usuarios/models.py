from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models


class Rol(models.Model):
    rol_id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=255)
    descripcion = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'roles'
        verbose_name = 'rol'
        verbose_name_plural = 'roles'

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

        username = self.model.normalize_username(username)
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
    nombre = models.CharField(max_length=255)
    username = models.CharField(max_length=100, unique=True)
    correo = models.EmailField(max_length=255)
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

    def save(self, *args, **kwargs):
        # Sincronizar is_superuser con el rol
        es_admin_rol = (self.rol_id == 1)
        if not es_admin_rol and hasattr(self, '_state'):
            cached_rol = self._state.fields_cache.get('rol')
            if cached_rol and getattr(cached_rol, 'nombre', '').lower() == 'admin':
                es_admin_rol = True
        self.is_superuser = bool(es_admin_rol)
        super().save(*args, **kwargs)

    @property
    def is_active(self):
        return self.activo

    @is_active.setter
    def is_active(self, value): #type: ignore
        self.activo = value

    @property
    def is_staff(self):
        return self.is_active and self.es_admin

    @property
    def es_admin(self):
        if self.rol_id == 1:
            return True
        cached_rol = self._state.fields_cache.get('rol') if hasattr(self, '_state') else None
        return bool(cached_rol and getattr(cached_rol, 'nombre', '').lower() == 'admin')

    @property
    def es_cajero(self):
        if self.rol_id == 2:
            return True
        cached_rol = self._state.fields_cache.get('rol') if hasattr(self, '_state') else None
        return bool(cached_rol and getattr(cached_rol, 'nombre', '').lower() == 'cajero')

    @property
    def es_asistente(self):
        if self.rol_id == 3:
            return True
        cached_rol = self._state.fields_cache.get('rol') if hasattr(self, '_state') else None
        return bool(cached_rol and getattr(cached_rol, 'nombre', '').lower() == 'asistente')

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
