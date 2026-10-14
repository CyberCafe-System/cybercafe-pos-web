from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from categorias import views as categorias_views
from config.views import ProtectedTemplateView

urlpatterns = [
    path('admin/', admin.site.urls),

    # --- RUTAS DE ACCESO ---
    path(
        'login/',
        LoginView.as_view(template_name='login.html', redirect_authenticated_user=True),
        name='login',
    ),
    path('logout/', LogoutView.as_view(), name='logout'),

    # --- PANTALLA PRINCIPAL (Dashboard) ---
    path('', ProtectedTemplateView.as_view(template_name='inicio.html'), name='inicio'),

    # --- PANTALLAS DE OPERACION PRINCIPALES ---
    path('rentas/', ProtectedTemplateView.as_view(template_name='rentas/rentas.html'), name='rentas'),
    path('pos/', ProtectedTemplateView.as_view(template_name='pos/pos.html'), name='pos'),
    path('clientes/', ProtectedTemplateView.as_view(template_name='clientes/clientes.html'), name='clientes'),
    path('inventario/', ProtectedTemplateView.as_view(template_name='inventario/inventario.html'), name='inventario'),
    path('categorias/', categorias_views.categoria_list, name='categorias'),
    path('equipos/', ProtectedTemplateView.as_view(template_name='equipos/equipos.html'), name='equipos'),
    path('componentes/', ProtectedTemplateView.as_view(
        template_name='componentes/componentes.html'), name='componentes'),
    path('usuarios/', ProtectedTemplateView.as_view(template_name='usuarios/usuarios.html'), name='usuarios'),
    path('reportes/', ProtectedTemplateView.as_view(template_name='reportes.html'),
         name='reportes'),

    # --- RUTAS FALSAS PARA FORMULARIOS (MODALES) ---
    # Rentas
    path('crear_renta/', ProtectedTemplateView.as_view(template_name='rentas/rentas.html'),
         name='crear_renta'),
    path('finalizar_renta/', ProtectedTemplateView.as_view(template_name='rentas/rentas.html'),
         name='finalizar_renta'),

    # POS
    path('agregar_carrito/', ProtectedTemplateView.as_view(template_name='pos/pos.html'),
         name='agregar_carrito'),
    path('procesar_venta/', ProtectedTemplateView.as_view(template_name='pos/pos.html'),
         name='procesar_venta'),

    # Clientes
    path('crear_cliente/', ProtectedTemplateView.as_view(template_name='clientes/clientes.html'),
         name='crear_cliente'),
    path('modificar_cliente/', ProtectedTemplateView.as_view(
        template_name='clientes/clientes.html'), name='modificar_cliente'),
    path('eliminar_cliente/', ProtectedTemplateView.as_view(
        template_name='clientes/clientes.html'), name='eliminar_cliente'),

    # Inventario
    path('crear_producto/', ProtectedTemplateView.as_view(
        template_name='inventario/inventario.html'), name='crear_producto'),
    path('modificar_producto/', ProtectedTemplateView.as_view(
        template_name='inventario/inventario.html'), name='modificar_producto'),
    path('eliminar_producto/', ProtectedTemplateView.as_view(
        template_name='inventario/inventario.html'), name='eliminar_producto'),

    # Categorías
    path('crear_categoria/', categorias_views.categoria_create, name='crear_categoria'),
    path('modificar_categoria/', categorias_views.categoria_edit, name='modificar_categoria'),
    path('desactivar_categoria/', categorias_views.categoria_toggle, name='desactivar_categoria'),

    # Equipos
    path('crear_equipo/', ProtectedTemplateView.as_view(template_name='equipos/equipos.html'),
         name='crear_equipo'),
    path('modificar_equipo/', ProtectedTemplateView.as_view(template_name='equipos/equipos.html'),
         name='modificar_equipo'),
    path('eliminar_equipo/', ProtectedTemplateView.as_view(template_name='equipos/equipos.html'),
         name='eliminar_equipo'),

    # Componentes
    path('crear_componente/', ProtectedTemplateView.as_view(
        template_name='componentes/componentes.html'), name='crear_componente'),
    path('modificar_componente/', ProtectedTemplateView.as_view(
        template_name='componentes/componentes.html'), name='modificar_componente'),
    path('eliminar_componente/', ProtectedTemplateView.as_view(
        template_name='componentes/componentes.html'), name='eliminar_componente'),

    # Usuarios
    path('crear_usuario/', ProtectedTemplateView.as_view(template_name='usuarios/usuarios.html'),
         name='crear_usuario'),
    path('modificar_usuario/', ProtectedTemplateView.as_view(
        template_name='usuarios/usuarios.html'), name='modificar_usuario'),
    path('eliminar_usuario/', ProtectedTemplateView.as_view(
        template_name='usuarios/usuarios.html'), name='eliminar_usuario'),
]
