from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from categorias import views as categorias_views
from clientes import views as clientes_views
from config.views import ProtectedTemplateView
from inventario import views as inventario_views
from pos_app import views as pos_views
from usuarios import views as usuarios_views

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
    path('pos/', pos_views.pos, name='pos'),
    path('clientes/', clientes_views.cliente_list, name='clientes'),
    path('inventario/', inventario_views.producto_list, name='inventario'),
    path('categorias/', categorias_views.categoria_list, name='categorias'),
    path('equipos/', ProtectedTemplateView.as_view(template_name='equipos/equipos.html'), name='equipos'),
    path('componentes/', ProtectedTemplateView.as_view(
        template_name='componentes/componentes.html'), name='componentes'),
    path('usuarios/', usuarios_views.usuario_list, name='usuarios'),
    path('reportes/', ProtectedTemplateView.as_view(template_name='reportes.html'),
         name='reportes'),

    # --- RUTAS FALSAS PARA FORMULARIOS (MODALES) ---
    # Rentas
    path('crear_renta/', ProtectedTemplateView.as_view(template_name='rentas/rentas.html'),
         name='crear_renta'),
    path('finalizar_renta/', ProtectedTemplateView.as_view(template_name='rentas/rentas.html'),
         name='finalizar_renta'),

    # POS
    path('agregar_carrito/', pos_views.agregar_carrito, name='agregar_carrito'),
    path('quitar_carrito/', pos_views.quitar_carrito, name='quitar_carrito'),
    path('procesar_venta/', pos_views.procesar_venta, name='procesar_venta'),
    path('ticket_pdf/', pos_views.ticket_pdf, name='ticket_pdf'),
    path('ticket_pdf/<int:venta_id>/', pos_views.ticket_pdf, name='ticket_pdf_venta'),

    # Clientes
    path('crear_cliente/', clientes_views.cliente_create, name='crear_cliente'),
    path('modificar_cliente/', clientes_views.cliente_edit, name='modificar_cliente'),

    # Inventario
    path('crear_producto/', inventario_views.producto_create, name='crear_producto'),
    path('modificar_producto/', inventario_views.producto_edit, name='modificar_producto'),
    path('desactivar_producto/', inventario_views.producto_toggle, name='desactivar_producto'),

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
    path('crear_usuario/', usuarios_views.usuario_create, name='crear_usuario'),
    path('modificar_usuario/', usuarios_views.usuario_edit, name='modificar_usuario'),
    path('desactivar_usuario/', usuarios_views.usuario_toggle, name='desactivar_usuario'),
]
