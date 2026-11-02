from decimal import Decimal
from unittest.mock import Mock, patch
from django.test import SimpleTestCase
from django.test.client import RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.auth.models import AnonymousUser

from clientes.models import Cliente
from inventario.models import Producto
from pos_app.models import Venta
from pos_app.views import procesar_venta


class PosIdempotenciaYConcurrenciaTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = Mock()
        self.user.is_authenticated = True
        self.user.es_cajero = True
        self.user.es_admin = False

    def _preparar_request(self, post_data, session_data=None):
        request = self.factory.post('/pos/venta/procesar/', post_data)
        request.user = self.user
        
        # Simular sesión y almacenamiento de mensajes
        setattr(request, 'session', session_data if session_data is not None else {})
        setattr(request, '_messages', FallbackStorage(request))
        return request

    def test_procesar_venta_rechaza_token_invalido_o_ausente(self):
        # Caso: Sin token de idempotencia en POST
        session = {'pos_token': 'token-secreto-123', 'carrito': {'1': 2}}
        request = self._preparar_request({'cliente_id': 1}, session_data=session)

        response = procesar_venta(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/pos/')

    @patch('pos_app.views.get_object_or_404')
    @patch('pos_app.views.Producto.objects')
    @patch('pos_app.views.transaction.atomic')
    def test_procesar_venta_rechaza_por_stock_insuficiente(self, mock_atomic, mock_prod_objects, mock_get_cliente):
        # Configurar producto con stock insuficiente
        mock_cliente = Mock(spec=Cliente, pk=1, correo=None)
        mock_get_cliente.return_value = mock_cliente

        prod_mock = Mock(spec=Producto, producto_id=10, nombre='Bebida Energética', cantidad=1, activo=True, precio_venta=Decimal('1.50'))
        mock_prod_objects.select_for_update.return_value.filter.return_value = [prod_mock]

        # Carrito solicita 2 unidades cuando solo hay 1
        session = {'pos_token': 'token-valido', 'carrito': {'10': 2}}
        request = self._preparar_request({'cliente_id': 1, 'pos_token': 'token-valido'}, session_data=session)

        response = procesar_venta(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/pos/')
        # El carrito debe mantenerse intacto para que el cajero lo ajuste
        self.assertEqual(request.session['carrito'], {'10': 2})

    @patch('pos_app.views.get_object_or_404')
    @patch('pos_app.views.Producto.objects')
    @patch('pos_app.views.transaction.atomic')
    def test_procesar_venta_rechaza_producto_desactivado(self, mock_atomic, mock_prod_objects, mock_get_cliente):
        mock_cliente = Mock(spec=Cliente, pk=1, correo=None)
        mock_get_cliente.return_value = mock_cliente

        # Producto inactivo
        prod_mock = Mock(spec=Producto, producto_id=12, nombre='Snack Descontinuado', cantidad=10, activo=False, precio_venta=Decimal('1.00'))
        mock_prod_objects.select_for_update.return_value.filter.return_value = [prod_mock]

        session = {'pos_token': 'token-valido', 'carrito': {'12': 1}}
        request = self._preparar_request({'cliente_id': 1, 'pos_token': 'token-valido'}, session_data=session)

        response = procesar_venta(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/pos/')
        self.assertEqual(request.session['carrito'], {'12': 1})
