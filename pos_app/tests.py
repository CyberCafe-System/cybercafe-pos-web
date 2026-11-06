import json
from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import SimpleTestCase
from django.test.client import RequestFactory
from django.urls import resolve, reverse

from clientes.models import Cliente
from config.context_processors import contexto_global_sistema
from equipos.forms import EquipoForm
from equipos.models import Equipo
from equipos.views import equipo_delete
from inventario.models import Producto
from pos_app.views import procesar_venta
from rentas.views import api_rentas_activas
from revisiones.models import RevisionEquipo
from revisiones.views import editar_revision


class PosIdempotenciaYConcurrenciaTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = Mock()
        self.user.is_authenticated = True
        self.user.es_cajero = True
        self.user.es_admin = True
        self.user.es_asistente = False

    def _preparar_request(self, path, post_data, session_data=None):
        request = self.factory.post(path, post_data)
        request.user = self.user
        setattr(request, 'session', session_data if session_data is not None else {})
        setattr(request, '_messages', FallbackStorage(request))
        return request

    def test_procesar_venta_rechaza_token_invalido_o_ausente(self):
        session = {'pos_token': 'token-secreto-123', 'carrito': {'1': 2}}
        request = self._preparar_request('/procesar_venta/', {'cliente_id': 1}, session_data=session)

        response = procesar_venta(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/pos/')

    @patch('pos_app.views.get_object_or_404')
    @patch('pos_app.views.Producto.objects')
    @patch('pos_app.views.transaction.atomic')
    def test_procesar_venta_rechaza_por_stock_insuficiente(self, mock_atomic, mock_prod_objects, mock_get_cliente):
        mock_cliente = Mock(spec=Cliente, pk=1, correo=None)
        mock_get_cliente.return_value = mock_cliente

        cat_mock = Mock(activa=True)
        prod_mock = Mock(
            spec=Producto,
            producto_id=10,
            nombre='Bebida Energética',
            cantidad=1,
            activo=True,
            categoria=cat_mock,
            precio_venta=Decimal('1.50'),
        )
        mock_prod_objects.select_for_update.return_value.select_related.return_value.filter.return_value = [prod_mock]

        session = {'pos_token': 'token-valido', 'carrito': {'10': 2}}
        request = self._preparar_request(
            '/procesar_venta/',
            {'cliente_id': 1, 'pos_token': 'token-valido'},
            session_data=session,
        )

        response = procesar_venta(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/pos/')
        self.assertEqual(request.session['carrito'], {'10': 2})

    @patch('pos_app.views.get_object_or_404')
    @patch('pos_app.views.Producto.objects')
    @patch('pos_app.views.transaction.atomic')
    def test_procesar_venta_rechaza_producto_desactivado(self, mock_atomic, mock_prod_objects, mock_get_cliente):
        mock_cliente = Mock(spec=Cliente, pk=1, correo=None)
        mock_get_cliente.return_value = mock_cliente

        cat_mock = Mock(activa=True)
        prod_mock = Mock(
            spec=Producto,
            producto_id=12,
            nombre='Snack Descontinuado',
            cantidad=10,
            activo=False,
            categoria=cat_mock,
            precio_venta=Decimal('1.00'),
        )
        mock_prod_objects.select_for_update.return_value.select_related.return_value.filter.return_value = [prod_mock]

        session = {'pos_token': 'token-valido', 'carrito': {'12': 1}}
        request = self._preparar_request(
            '/procesar_venta/',
            {'cliente_id': 1, 'pos_token': 'token-valido'},
            session_data=session,
        )

        response = procesar_venta(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/pos/')
        self.assertEqual(request.session['carrito'], {'12': 1})

    @patch('pos_app.views.get_object_or_404')
    @patch('pos_app.views.Producto.objects')
    @patch('pos_app.views.transaction.atomic')
    def test_procesar_venta_rechaza_categoria_desactivada(self, mock_atomic, mock_prod_objects, mock_get_cliente):
        mock_cliente = Mock(spec=Cliente, pk=1, correo=None)
        mock_get_cliente.return_value = mock_cliente

        cat_mock = Mock(activa=False)
        prod_mock = Mock(
            spec=Producto,
            producto_id=15,
            nombre='Café Espresso',
            cantidad=10,
            activo=True,
            categoria=cat_mock,
            precio_venta=Decimal('2.00'),
        )
        mock_prod_objects.select_for_update.return_value.select_related.return_value.filter.return_value = [prod_mock]

        session = {'pos_token': 'token-valido', 'carrito': {'15': 1}}
        request = self._preparar_request(
            '/procesar_venta/',
            {'cliente_id': 1, 'pos_token': 'token-valido'},
            session_data=session,
        )

        response = procesar_venta(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/pos/')
        self.assertEqual(request.session['carrito'], {'15': 1})

    @patch('equipos.views.DetalleRenta.objects')
    @patch('equipos.views.get_object_or_404')
    def test_equipo_delete_bloqueado_con_historial_rentas(self, mock_get_equipo, mock_dr_objects):
        equipo_mock = Mock(spec=Equipo, equipo_id=3, nombre='PC-Gamer-03')
        mock_get_equipo.return_value = equipo_mock
        mock_dr_objects.filter.return_value.exists.return_value = True

        request = self._preparar_request('/eliminar_equipo/', {'equipo_id': 3})
        response = equipo_delete(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/equipos/')
        equipo_mock.delete.assert_not_called()

    @patch('revisiones.views.transaction.atomic')
    @patch('revisiones.views.get_object_or_404')
    def test_ruta_editar_revision_registrada_y_valida_estado(self, mock_get_obj, mock_atomic):
        url = reverse('editar_revision', kwargs={'revision_id': 5})
        self.assertEqual(url, '/revisiones/editar/5/')

        rev_mock = Mock(spec=RevisionEquipo, revision_equipo_id=5)
        rev_mock.detalle_renta = Mock(equipo_id=7)
        eq_mock = Mock(spec=Equipo, equipo_id=7, estado='DISPONIBLE')
        mock_get_obj.side_effect = [rev_mock, eq_mock]

        request = self._preparar_request(
            url,
            {
                'observaciones': 'Falla en fuente',
                'inspeccion_pasada': 'false',
                'estado_si_daniado': 'ESTADO_INVALIDO_INYECTADO',
            },
        )
        response = editar_revision(request, revision_id=5)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(eq_mock.estado, 'DANIOS_MENORES')

    @patch('rentas.views.verificar_vencimiento_rentas_locales')
    @patch('rentas.views.obtener_rentas_activas_payload')
    def test_api_rentas_activas_notificaciones_globales(self, mock_payload, mock_verificar):
        mock_payload.return_value = [
            {
                'detalle_id': 42,
                'equipo_id': 1,
                'equipo_nombre': 'PC-01',
                'cliente_nombre': 'Juan Pérez',
                'inicio_iso': '2026-11-01T23:00:00+00:00',
                'tiempo_total': 60,
                'notif_key': '42_60',
            }
        ]
        url = reverse('api_rentas_activas')
        self.assertEqual(url, '/api/rentas_activas/')
        request = self.factory.get(url)
        request.user = self.user

        response = api_rentas_activas(request)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(len(data['rentas']), 1)
        self.assertEqual(data['rentas'][0]['equipo_nombre'], 'PC-01')

    @patch('config.context_processors.obtener_rentas_activas_payload')
    def test_contexto_global_sistema_navegacion_y_notificaciones(self, mock_payload):
        mock_payload.return_value = [{'detalle_id': 9, 'equipo_nombre': 'PC-02'}]
        request = self.factory.get('/usuarios/')
        request.user = self.user
        request.resolver_match = resolve('/usuarios/')

        ctx = contexto_global_sistema(request)
        self.assertTrue(ctx['nav_usuarios'])
        self.assertFalse(ctx['nav_inicio'])
        self.assertEqual(ctx['modulo_titulo'], 'Usuarios y Auditoría')
        self.assertEqual(ctx['modulo_icono'], 'bi-person-badge')
        self.assertIn('PC-02', ctx['rentas_activas_global_json'])

    @patch('equipos.forms.Equipo.objects')
    def test_equipo_form_rechaza_nombre_duplicado(self, mock_equipo_objects):
        mock_equipo_objects.filter.return_value.exists.return_value = True
        form = EquipoForm(
            data={
                'nombre': 'PC-01',
                'tipo': 'PC',
                'tarifa_por_hora': '1,50',
                'estado': 'DISPONIBLE',
                'descripcion': 'Estación principal',
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn('nombre', form.errors)


    @patch('pos_app.views.Venta.objects')
    @patch('pos_app.views.get_object_or_404')
    @patch('pos_app.views.Producto.objects')
    @patch('pos_app.views.transaction.atomic')
    def test_procesar_venta_valida_efectivo_y_cambio_y_maximo(self, mock_atomic, mock_prod_objects, mock_get_cliente, mock_venta_objects):
        mock_venta_objects.filter.return_value.first.return_value = None
        mock_venta_objects.select_for_update.return_value.filter.return_value.first.return_value = None
        mock_cliente = Mock(spec=Cliente, pk=1, correo=None, activo=True)
        mock_get_cliente.return_value = mock_cliente

        session = {'pos_token': 'token-valido', 'carrito': {'10': 1}}
        # 1. Rechaza efectivo menor al total
        req_insuficiente = self._preparar_request(
            '/procesar_venta/',
            {'cliente_id': 1, 'pos_token': 'token-valido', 'efectivo_recibido': '0.50'},
            session_data=session,
        )
        res_insuf = procesar_venta(req_insuficiente)
        self.assertEqual(res_insuf.status_code, 302)

        # 2. Rechaza efectivo mayor al limite de $100
        req_excedido = self._preparar_request(
            '/procesar_venta/',
            {'cliente_id': 1, 'pos_token': 'token-valido', 'efectivo_recibido': '150.00'},
            session_data=session,
        )
        res_exc = procesar_venta(req_excedido)
        self.assertEqual(res_exc.status_code, 302)

    @patch('pos_app.views.registrar_auditoria')
    @patch('pos_app.views.MovimientoInventario.objects.create')
    @patch('pos_app.views.Producto.objects')
    @patch('pos_app.views.Venta.objects')
    @patch('pos_app.views.transaction.atomic')
    def test_anular_venta_por_admin_restituye_stock(self, mock_atomic, mock_venta_objs, mock_prod_objs, mock_mov_create, mock_aud):
        from pos_app.views import anular_venta
        venta_mock = Mock(venta_id=88, estado='PAGADA')
        det_mock = Mock(producto_id=5, cantidad=2)
        venta_mock.detalles.select_related.return_value = [det_mock]
        mock_venta_objs.select_for_update.return_value.get.return_value = venta_mock

        prod_mock = Mock(producto_id=5, cantidad=10, version=1)
        mock_prod_objs.select_for_update.return_value.get.return_value = prod_mock

        req = self._preparar_request('/pos/anular/88/', {'motivo': 'Cliente devolvió el producto por defecto'})
        res = anular_venta(req, venta_id=88)

        self.assertEqual(res.status_code, 302)
        self.assertEqual(venta_mock.estado, 'ANULADA')
        self.assertEqual(prod_mock.cantidad, 12)
        mock_mov_create.assert_called_once()
        mock_aud.assert_called_once()

    def test_equipo_es_rentable_bloquea_si_componente_daniado(self):
        eq = Equipo(nombre='PC-01', tipo='PC', tarifa_por_hora=Decimal('1.50'), estado='DISPONIBLE')
        # Sin componentes
        self.assertTrue(eq.es_rentable)
        self.assertTrue(eq.evaluar_rentabilidad()[0])

        # Estado en daños menores bloquea directamente
        eq.estado = 'DANIOS_MENORES'
        self.assertFalse(eq.es_rentable)
        self.assertFalse(eq.evaluar_rentabilidad()[0])
