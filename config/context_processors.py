import json

from django.utils import timezone
from rentas.models import DetalleRenta


def obtener_rentas_activas_payload():
    """
    Devuelve la lista serializable de sesiones de renta actualmente en curso (ACTIVA o TIEMPO_TERMINADO)
    para el monitor global de notificaciones en todas las pantallas.
    """
    try:
        detalles = (
            DetalleRenta.objects.filter(estado__in=['ACTIVA', 'TIEMPO_TERMINADO'])
            .select_related('equipo', 'renta__cliente')
            .order_by('hora_inicio')
        )
        resultado = []
        for d in detalles:
            tiempo_total = (d.tiempo_de_renta or 0) + (d.tiempo_agregado or 0)
            eq_nombre = d.equipo.nombre if d.equipo else 'Equipo'
            if d.renta and d.renta.cliente:
                cl_nombre = f"{d.renta.cliente.nombre} {d.renta.cliente.apellido}".strip()
            else:
                cl_nombre = 'Cliente General'
            resultado.append({
                'detalle_id': d.detalle_renta_id,
                'equipo_id': d.equipo_id,
                'equipo_nombre': eq_nombre,
                'cliente_nombre': cl_nombre,
                'inicio_iso': d.hora_inicio.isoformat() if d.hora_inicio else '',
                'vencimiento_iso': d.hora_vencimiento.isoformat() if d.hora_vencimiento else '',
                'tiempo_total': tiempo_total,
                'estado': d.estado,
                'notif_key': f"{d.detalle_renta_id}_{tiempo_total}_{d.estado}",
            })
        return resultado
    except Exception:
        return []


def contexto_global_sistema(request):
    """
    Context processor global que inyecta:
    1. Estado de navegación activo e indicador de módulo actual.
    2. Datos en vivo de rentas activas y vencidas para notificaciones globales.
    """
    match = getattr(request, 'resolver_match', None)
    url_name = getattr(match, 'url_name', '') or ''

    nav_inicio = (url_name == 'inicio')
    nav_rentas = url_name in (
        'rentas', 'crear_renta', 'extender_renta', 'finalizar_renta',
        'enviar_revision', 'factura_renta', 'factura_renta_id',
    )
    nav_pos = url_name in ('pos', 'procesar_venta', 'ticket_pdf', 'ticket_pdf_venta', 'anular_venta')
    nav_inventario = url_name in ('inventario', 'crear_producto', 'modificar_producto', 'desactivar_producto', 'ajustar_stock')
    nav_categorias = url_name in ('categorias', 'crear_categoria', 'modificar_categoria', 'desactivar_categoria')
    nav_revisiones = ('revision' in url_name)
    nav_equipos = url_name in ('equipos', 'crear_equipo', 'modificar_equipo', 'eliminar_equipo', 'habilitar_equipo')
    nav_componentes = url_name in ('componentes', 'crear_componente', 'modificar_componente', 'desactivar_componente')
    nav_clientes = url_name in ('clientes', 'crear_cliente', 'modificar_cliente', 'desactivar_cliente')
    nav_usuarios = url_name in ('usuarios', 'crear_usuario', 'modificar_usuario', 'desactivar_usuario', 'auditoria')
    nav_reportes = url_name in ('reportes', 'reportes_exportar_csv', 'reportes_exportar_excel')

    modulo_titulo = 'Panel Principal'
    modulo_icono = 'bi-speedometer2'
    if nav_rentas:
        modulo_titulo = 'Control de Rentas'
        modulo_icono = 'bi-pc-display'
    elif nav_revisiones:
        modulo_titulo = 'Revisiones de Equipos'
        modulo_icono = 'bi-clipboard-check'
    elif nav_pos:
        modulo_titulo = 'Punto de Venta'
        modulo_icono = 'bi-cart4'
    elif nav_inventario:
        modulo_titulo = 'Inventario'
        modulo_icono = 'bi-box-seam'
    elif nav_categorias:
        modulo_titulo = 'Categorías'
        modulo_icono = 'bi-tags'
    elif nav_equipos:
        modulo_titulo = 'Equipos'
        modulo_icono = 'bi-cpu'
    elif nav_componentes:
        modulo_titulo = 'Componentes'
        modulo_icono = 'bi-mouse2'
    elif nav_clientes:
        modulo_titulo = 'Clientes'
        modulo_icono = 'bi-people'
    elif nav_usuarios:
        modulo_titulo = 'Usuarios y Auditoría'
        modulo_icono = 'bi-person-badge'
    elif nav_reportes:
        modulo_titulo = 'Reportes'
        modulo_icono = 'bi-graph-up'

    user = getattr(request, 'user', None)
    rentas_activas = []
    if user and getattr(user, 'is_authenticated', False):
        rentas_activas = obtener_rentas_activas_payload()

    return {
        'nav_inicio': nav_inicio,
        'nav_rentas': nav_rentas,
        'nav_pos': nav_pos,
        'nav_inventario': nav_inventario,
        'nav_categorias': nav_categorias,
        'nav_revisiones': nav_revisiones,
        'nav_equipos': nav_equipos,
        'nav_componentes': nav_componentes,
        'nav_clientes': nav_clientes,
        'nav_usuarios': nav_usuarios,
        'nav_reportes': nav_reportes,
        'modulo_titulo': modulo_titulo,
        'modulo_icono': modulo_icono,
        'rentas_activas_global_json': json.dumps(rentas_activas),
    }
