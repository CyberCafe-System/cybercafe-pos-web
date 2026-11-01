from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from categorias import views as categorias_views
from clientes import views as clientes_views
from componentes import views as componentes_views
from config.views import ProtectedTemplateView
from equipos import views as equipos_views
from inventario import views as inventario_views
from pos_app import views as pos_views
from rentas import views as rentas_views
from revisiones import views as revisiones_views
from usuarios import views as usuarios_views
from usuarios.forms import WebAuthenticationForm

urlpatterns = [
    path('admin/', admin.site.urls),

    # --- RUTAS DE ACCESO ---
    path(
        'login/',
        LoginView.as_view(
            template_name='login.html',
            authentication_form=WebAuthenticationForm,
            redirect_authenticated_user=True,
        ),
        name='login',
    ),
    path('logout/', LogoutView.as_view(), name='logout'),

    # --- PANTALLA PRINCIPAL (Dashboard) ---
    path('', pos_views.inicio, name='inicio'),

    # --- PANTALLAS DE OPERACION PRINCIPALES ---
    path('rentas/', rentas_views.renta_list, name='rentas'),
    path('pos/', pos_views.pos, name='pos'),
    path('clientes/', clientes_views.cliente_list, name='clientes'),
    path('inventario/', inventario_views.producto_list, name='inventario'),
    path('categorias/', categorias_views.categoria_list, name='categorias'),
    path('equipos/', equipos_views.equipo_list, name='equipos'),
    path('componentes/', componentes_views.componente_list, name='componentes'),
    path('usuarios/', usuarios_views.usuario_list, name='usuarios'),
    path('revisiones/', revisiones_views.revisiones_list, name='revisiones'),
    path('revisiones/crear/', revisiones_views.crear_revision, name='crear_revision'),
    path('revisiones/reiniciar/<int:revision_id>/', revisiones_views.reiniciar_revision, name='reiniciar_revision'),
    path('reportes/', pos_views.reportes, name='reportes'),
    path('reportes/exportar_csv/', pos_views.reportes_exportar_csv, name='reportes_exportar_csv'),
    path('reportes/exportar_excel/', pos_views.reportes_exportar_excel, name='reportes_exportar_excel'),

    # --- RENTAS ---
    path('crear_renta/', rentas_views.renta_create, name='crear_renta'),
    path('extender_renta/', rentas_views.renta_extender, name='extender_renta'),
    path('enviar_revision/', rentas_views.renta_enviar_revision, name='enviar_revision'),
    path('finalizar_renta/', rentas_views.renta_finalizar, name='finalizar_renta'),
    path('factura_renta/', rentas_views.renta_factura_pdf, name='factura_renta'),
    path('factura_renta/<int:renta_id>/', rentas_views.renta_factura_pdf, name='factura_renta_id'),

    # POS
    path('agregar_carrito/', pos_views.agregar_carrito, name='agregar_carrito'),
    path('actualizar_cantidad_carrito/', pos_views.actualizar_cantidad_carrito, name='actualizar_cantidad_carrito'),
    path('quitar_carrito/', pos_views.quitar_carrito, name='quitar_carrito'),
    path('limpiar_carrito/', pos_views.limpiar_carrito, name='limpiar_carrito'),
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
    path('crear_equipo/', equipos_views.equipo_create, name='crear_equipo'),
    path('modificar_equipo/', equipos_views.equipo_edit, name='modificar_equipo'),
    path('eliminar_equipo/', equipos_views.equipo_delete, name='eliminar_equipo'),

    # Componentes
    path('crear_componente/', componentes_views.componente_create, name='crear_componente'),
    path('modificar_componente/', componentes_views.componente_edit, name='modificar_componente'),
    path('desactivar_componente/', componentes_views.componente_toggle, name='desactivar_componente'),

    # Usuarios
    path('crear_usuario/', usuarios_views.usuario_create, name='crear_usuario'),
    path('modificar_usuario/', usuarios_views.usuario_edit, name='modificar_usuario'),
    path('desactivar_usuario/', usuarios_views.usuario_toggle, name='desactivar_usuario'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
