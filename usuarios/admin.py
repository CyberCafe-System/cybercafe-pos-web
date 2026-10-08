from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import UsuarioChangeForm, UsuarioCreationForm
from .models import Rol, Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    form = UsuarioChangeForm
    add_form = UsuarioCreationForm
    model = Usuario
    list_display = ('username', 'nombre', 'correo', 'rol', 'activo', 'is_superuser')
    list_filter = ('activo', 'is_superuser', 'rol')
    search_fields = ('username', 'nombre', 'correo')
    ordering = ('username',)
    filter_horizontal = ()
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Información personal', {'fields': ('nombre', 'correo', 'rol')}),
        ('Permisos', {'fields': ('activo', 'is_superuser')}),
        ('Actividad', {'fields': ('last_login',)}),
    )
    add_fieldsets = (
        (
            None,
            {
                'classes': ('wide',),
                'fields': (
                    'username',
                    'nombre',
                    'correo',
                    'rol',
                    'activo',
                    'is_superuser',
                    'password1',
                    'password2',
                ),
            },
        ),
    )


@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'descripcion')
    search_fields = ('nombre',)
