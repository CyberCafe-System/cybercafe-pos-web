from unittest.mock import Mock, patch
from django.test import SimpleTestCase
from django.test.client import RequestFactory

from clientes.forms import ClienteForm
from clientes.models import Cliente
from clientes.views import cliente_create, cliente_edit


class ClienteFormValidationTests(SimpleTestCase):
    @patch.object(Cliente.objects, 'filter')
    def test_telefono_must_have_exactly_8_digits(self, mock_filter):
        mock_filter.return_value.exists.return_value = False

        # Caso 1: 7 dígitos (inválido)
        data_7 = {
            'nombre': 'Carlos',
            'apellido': 'López',
            'dui': '01234567-8',
            'direccion': 'San Salvador',
            'telefono': '7123456',
            'correo': 'carlos@test.com'
        }
        form = ClienteForm(data=data_7)
        self.assertFalse(form.is_valid())
        self.assertIn('telefono', form.errors)
        self.assertIn('exactamente 8 números', form.errors['telefono'][0])

        # Caso 2: 9 dígitos (inválido)
        data_9 = dict(data_7, telefono='712345678')
        form = ClienteForm(data=data_9)
        self.assertFalse(form.is_valid())
        self.assertIn('telefono', form.errors)
        self.assertIn('exactamente 8 números', form.errors['telefono'][0])

        # Caso 3: exactamente 8 dígitos (válido)
        data_8 = dict(data_7, telefono='71234567')
        form = ClienteForm(data=data_8)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['telefono'], 71234567)

    @patch.object(Cliente.objects, 'filter')
    def test_dui_formatting_and_validation(self, mock_filter):
        mock_filter.return_value.exists.return_value = False

        base_data = {
            'nombre': 'Ana',
            'apellido': 'Martínez',
            'direccion': 'Santa Ana',
            'telefono': '77889900',
        }

        # Caso 1: 9 dígitos sin guion -> se auto-formatea a 00000000-0
        data_autoformat = dict(base_data, dui='045678912')
        form = ClienteForm(data=data_autoformat)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['dui'], '04567891-2')

        # Caso 2: Formato estándar correcto
        data_standard = dict(base_data, dui='04567891-2')
        form = ClienteForm(data=data_standard)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['dui'], '04567891-2')

        # Caso 3: DUI incompleto (menos dígitos)
        data_invalid = dict(base_data, dui='1234567')
        form = ClienteForm(data=data_invalid)
        self.assertFalse(form.is_valid())
        self.assertIn('dui', form.errors)
        self.assertIn('formato 00000000-0', form.errors['dui'][0])

    @patch.object(Cliente.objects, 'filter')
    def test_duplicate_dui_is_rejected(self, mock_filter):
        mock_filter.return_value.exists.return_value = True

        data = {
            'nombre': 'Pedro',
            'apellido': 'Gómez',
            'dui': '01234567-8',
            'direccion': 'San Miguel',
            'telefono': '71112222',
        }
        form = ClienteForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('dui', form.errors)
        self.assertIn('Ya existe un cliente', form.errors['dui'][0])


class ClienteViewsAjaxTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch('clientes.views.messages.success')
    @patch.object(ClienteForm, 'save')
    @patch.object(Cliente.objects, 'filter')
    def test_cliente_create_ajax_success(self, mock_filter, mock_save, mock_msg):
        mock_filter.return_value.exists.return_value = False
        mock_cliente = Mock()
        mock_cliente.cliente_id = 99
        mock_cliente.nombre = 'Luis'
        mock_cliente.apellido = 'Flores'
        mock_cliente.dui = '09876543-2'
        mock_cliente.telefono = 70001122
        mock_cliente.correo = 'luis@test.com'
        mock_cliente.direccion = 'Colonia Escalón'
        mock_save.return_value = mock_cliente

        request = self.factory.post(
            '/clientes/crear_cliente/',
            data={
                'nombre': 'Luis',
                'apellido': 'Flores',
                'dui': '09876543-2',
                'telefono': '70001122',
                'correo': 'luis@test.com',
                'direccion': 'Colonia Escalón',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        request.user = Mock()
        request.user.is_authenticated = True
        request.user.es_admin = True

        response = cliente_create(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn('"success": true', response.content.decode())

    @patch.object(Cliente.objects, 'filter')
    def test_cliente_create_ajax_returns_400_with_errors_preserving_flow(self, mock_filter):
        mock_filter.return_value.exists.return_value = False

        # Datos con teléfono inválido (7 dígitos)
        request = self.factory.post(
            '/clientes/crear_cliente/',
            data={
                'nombre': 'Luis',
                'apellido': 'Flores',
                'dui': '09876543-2',
                'telefono': '7000112',  # Falta un dígito
                'direccion': 'Colonia Escalón',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        request.user = Mock()
        request.user.is_authenticated = True
        request.user.es_admin = True

        import json

        response = cliente_create(request)
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content.decode('utf-8'))
        self.assertFalse(data['success'])
        self.assertIn('telefono', data['errors'])
        self.assertIn('exactamente 8 números', data['errors']['telefono'][0])

    @patch('clientes.views.get_object_or_404')
    @patch.object(Cliente.objects, 'filter')
    def test_cliente_edit_ajax_validation_error_keeps_data(self, mock_filter, mock_get_obj):
        mock_filter.return_value.exclude.return_value.exists.return_value = False
        mock_cliente = Cliente(
            cliente_id=5,
            nombre='Mario',
            apellido='Santos',
            dui='01234567-9',
            telefono=77778888,
            direccion='Sonsonate',
            correo='mario@test.com'
        )
        mock_get_obj.return_value = mock_cliente

        import json

        # Enviar actualización con DUI incompleto
        request = self.factory.post(
            '/clientes/modificar_cliente/',
            data={
                'cliente_id': 5,
                'nombre': 'Mario',
                'apellido': 'Santos',
                'dui': '01234',  # Incompleto
                'telefono': '77778888',
                'direccion': 'Sonsonate',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        request.user = Mock()
        request.user.is_authenticated = True
        request.user.es_admin = True

        response = cliente_edit(request)
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content.decode('utf-8'))
        self.assertFalse(data['success'])
        self.assertIn('dui', data['errors'])

