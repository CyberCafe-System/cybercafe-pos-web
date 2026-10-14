from django.contrib import admin
from django.urls import path
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),

    # --- RUTAS DE ACCESO ---
    path('login/', TemplateView.as_view(template_name='login.html'), name='login'),
    path('logout/', TemplateView.as_view(template_name='login.html'), name='logout'),

    # --- PANTALLA PRINCIPAL (Dashboard) ---
    path('', TemplateView.as_view(template_name='inicio.html'), name='inicio'),

    # --- PANTALLAS DE OPERACION PRINCIPALES ---
    path('rentas/', TemplateView.as_view(template_name='rentas/rentas.html'), name='rentas'),
    path('pos/', TemplateView.as_view(template_name='pos/pos.html'), name='pos'),
    path('clientes/', TemplateView.as_view(template_name='clientes/clientes.html'), name='clientes'),
    path('inventario/', TemplateView.as_view(template_name='inventario/inventario.html'), name='inventario'),
    path('categorias/', TemplateView.as_view(template_name='categorias/categorias.html'), name='categorias'),
    path('equipos/', TemplateView.as_view(template_name='equipos/equipos.html'), name='equipos'),
    path('componentes/', TemplateView.as_view(
        template_name='componentes/componentes.html'), name='componentes'),
    path('usuarios/', TemplateView.as_view(template_name='usuarios/usuarios.html'), name='usuarios'),
    path('reportes/', TemplateView.as_view(template_name='reportes.html'),
         name='reportes'),

    # --- RUTAS FALSAS PARA FORMULARIOS (MODALES) ---
    # Rentas
    path('crear_renta/', TemplateView.as_view(template_name='rentas/rentas.html'),
         name='crear_renta'),
    path('finalizar_renta/', TemplateView.as_view(template_name='rentas/rentas.html'),
         name='finalizar_renta'),

    # POS
    path('agregar_carrito/', TemplateView.as_view(template_name='pos/pos.html'),
         name='agregar_carrito'),
    path('procesar_venta/', TemplateView.as_view(template_name='pos/pos.html'),
         name='procesar_venta'),

    # Clientes
    path('crear_cliente/', TemplateView.as_view(template_name='clientes/clientes.html'),
         name='crear_cliente'),
    path('modificar_cliente/', TemplateView.as_view(
        template_name='clientes/clientes.html'), name='modificar_cliente'),
    path('eliminar_cliente/', TemplateView.as_view(
        template_name='clientes/clientes.html'), name='eliminar_cliente'),

    # Inventario
    path('crear_producto/', TemplateView.as_view(
        template_name='inventario/inventario.html'), name='crear_producto'),
    path('modificar_producto/', TemplateView.as_view(
        template_name='inventario/inventario.html'), name='modificar_producto'),
    path('eliminar_producto/', TemplateView.as_view(
        template_name='inventario/inventario.html'), name='eliminar_producto'),

    # Categorías
    path('crear_categoria/', TemplateView.as_view(
        template_name='categorias/categorias.html'), name='crear_categoria'),
    path('modificar_categoria/', TemplateView.as_view(
        template_name='categorias/categorias.html'), name='modificar_categoria'),
    path('eliminar_categoria/', TemplateView.as_view(
        template_name='categorias/categorias.html'), name='eliminar_categoria'),

    # Equipos
    path('crear_equipo/', TemplateView.as_view(template_name='equipos/equipos.html'),
         name='crear_equipo'),
    path('modificar_equipo/', TemplateView.as_view(template_name='equipos/equipos.html'),
         name='modificar_equipo'),
    path('eliminar_equipo/', TemplateView.as_view(template_name='equipos/equipos.html'),
         name='eliminar_equipo'),

    # Componentes
    path('crear_componente/', TemplateView.as_view(
        template_name='componentes/componentes.html'), name='crear_componente'),
    path('modificar_componente/', TemplateView.as_view(
        template_name='componentes/componentes.html'), name='modificar_componente'),
    path('eliminar_componente/', TemplateView.as_view(
        template_name='componentes/componentes.html'), name='eliminar_componente'),

    # Usuarios
    path('crear_usuario/', TemplateView.as_view(template_name='usuarios/usuarios.html'),
         name='crear_usuario'),
    path('modificar_usuario/', TemplateView.as_view(
        template_name='usuarios/usuarios.html'), name='modificar_usuario'),
    path('eliminar_usuario/', TemplateView.as_view(
        template_name='usuarios/usuarios.html'), name='eliminar_usuario'),
]
