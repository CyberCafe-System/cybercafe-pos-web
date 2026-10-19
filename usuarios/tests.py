from unittest.mock import patch

from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase

from .models import Rol, Usuario


class UsuarioModelTests(SimpleTestCase):
    def test_user_model_maps_existing_database_schema(self):
        self.assertEqual(Usuario._meta.db_table, 'usuarios')
        self.assertFalse(Usuario._meta.managed)
        self.assertEqual(Usuario._meta.pk.name, 'usuario_id')
        self.assertEqual(Usuario._meta.get_field('rol').db_column, 'rol_id')
        self.assertFalse(Usuario._meta.get_field('rol').db_constraint)
        self.assertEqual(Rol._meta.db_table, 'roles')
        self.assertFalse(Rol._meta.managed)

    def test_migration_state_keeps_the_role_relation(self):
        loader = MigrationLoader(None, ignore_no_migrations=True)
        migrated_user = loader.project_state().apps.get_model('usuarios', 'Usuario')

        self.assertEqual(migrated_user._meta.get_field('rol').db_column, 'rol_id')

    def test_superuser_manager_sets_password_and_status(self):
        with patch.object(Usuario, 'save'):
            user = Usuario.objects.create_superuser(
                username='admin',
                password='example-password',
                nombre='Administrador',
                correo='admin@example.test',
                rol=1,
            )

        self.assertEqual(user.rol_id, 1)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.check_password('example-password'))

    def test_superuser_manager_rejects_non_superuser_flag(self):
        with self.assertRaisesMessage(
            ValueError,
            'Un superusuario debe tener is_superuser=True.',
        ):
            Usuario.objects.create_superuser(
                username='admin',
                password='example-password',
                nombre='Administrador',
                correo='admin@example.test',
                rol=1,
                is_superuser=False,
            )

    def test_role_properties_and_superuser_sync(self):
        from django.contrib.auth.base_user import AbstractBaseUser

        user = Usuario(username='test_user', rol_id=1)
        with patch.object(AbstractBaseUser, 'save', autospec=True):
            user.save()
            self.assertTrue(user.es_admin)
            self.assertFalse(user.es_cajero)
            self.assertFalse(user.es_asistente)
            self.assertTrue(user.is_superuser)

            # Cambiar a Cajero
            user.rol_id = 2
            user.save()
            self.assertFalse(user.es_admin)
            self.assertTrue(user.es_cajero)
            self.assertFalse(user.es_asistente)
            self.assertFalse(user.is_superuser)

            # Cambiar a Asistente
            user.rol_id = 3
            user.save()
            self.assertFalse(user.es_admin)
            self.assertFalse(user.es_cajero)
            self.assertTrue(user.es_asistente)
            self.assertFalse(user.is_superuser)



class DecoratorTests(SimpleTestCase):
    def test_admin_required_blocks_cajero_and_allows_admin(self):
        from unittest.mock import Mock
        from usuarios.decorators import admin_required

        mock_view = Mock(return_value='success')
        decorated = admin_required(mock_view)

        # Caso Cajero
        request_cajero = Mock()
        request_cajero.user.is_authenticated = True
        request_cajero.user.es_admin = False
        response = decorated(request_cajero)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')
        mock_view.assert_not_called()

        # Caso Admin
        request_admin = Mock()
        request_admin.user.is_authenticated = True
        request_admin.user.es_admin = True
        response_admin = decorated(request_admin)
        self.assertEqual(response_admin, 'success')
        mock_view.assert_called_once()

    def test_cajero_o_admin_required_blocks_asistente(self):
        from unittest.mock import Mock
        from usuarios.decorators import cajero_o_admin_required

        mock_view = Mock(return_value='success')
        decorated = cajero_o_admin_required(mock_view)

        # Caso Asistente
        request_asistente = Mock()
        request_asistente.user.is_authenticated = True
        request_asistente.user.es_admin = False
        request_asistente.user.es_cajero = False
        response = decorated(request_asistente)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')
        mock_view.assert_not_called()

        # Caso Cajero
        request_cajero = Mock()
        request_cajero.user.is_authenticated = True
        request_cajero.user.es_admin = False
        request_cajero.user.es_cajero = True
        response_cajero = decorated(request_cajero)
        self.assertEqual(response_cajero, 'success')
        mock_view.assert_called_once()

    def test_asistente_o_admin_required_delegates_to_admin_in_web(self):
        from unittest.mock import Mock
        from usuarios.decorators import asistente_o_admin_required

        mock_view = Mock(return_value='success')
        decorated = asistente_o_admin_required(mock_view)

        # Caso Cajero (Bloqueado)
        request_cajero = Mock()
        request_cajero.user.is_authenticated = True
        request_cajero.user.es_admin = False
        response = decorated(request_cajero)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')
        mock_view.assert_not_called()

        # Caso Asistente (Bloqueado en la web)
        request_asistente = Mock()
        request_asistente.user.is_authenticated = True
        request_asistente.user.es_admin = False
        request_asistente.user.es_asistente = True
        response_asistente = decorated(request_asistente)
        self.assertEqual(response_asistente.status_code, 302)
        self.assertEqual(response_asistente.url, '/')
        mock_view.assert_not_called()

        # Caso Admin (Permitido)
        request_admin = Mock()
        request_admin.user.is_authenticated = True
        request_admin.user.es_admin = True
        response_admin = decorated(request_admin)
        self.assertEqual(response_admin, 'success')
        mock_view.assert_called_once()


class WebSecurityIsolationTests(SimpleTestCase):
    def test_web_auth_form_blocks_asistente(self):
        from unittest.mock import Mock
        from django.core.exceptions import ValidationError
        from usuarios.forms import WebAuthenticationForm

        form = WebAuthenticationForm()
        mock_asistente = Mock()
        mock_asistente.is_active = True
        mock_asistente.es_asistente = True

        with self.assertRaises(ValidationError) as ctx:
            form.confirm_login_allowed(mock_asistente)

        self.assertEqual(ctx.exception.code, 'asistente_web_blocked')

    def test_web_auth_form_allows_admin_and_cajero(self):
        from unittest.mock import Mock
        from usuarios.forms import WebAuthenticationForm

        form = WebAuthenticationForm()

        mock_admin = Mock()
        mock_admin.is_active = True
        mock_admin.es_asistente = False
        self.assertIsNone(form.confirm_login_allowed(mock_admin))

        mock_cajero = Mock()
        mock_cajero.is_active = True
        mock_cajero.es_asistente = False
        self.assertIsNone(form.confirm_login_allowed(mock_cajero))

    def test_middleware_blocks_and_logs_out_asistente(self):
        from unittest.mock import Mock, patch
        from usuarios.middleware import BloqueoAsistenteWebMiddleware

        mock_get_response = Mock(return_value='next_response')
        middleware = BloqueoAsistenteWebMiddleware(mock_get_response)

        mock_request = Mock()
        mock_request.user.is_authenticated = True
        mock_request.user.es_asistente = True

        with patch('usuarios.middleware.logout') as mock_logout, \
             patch('usuarios.middleware.messages.warning') as mock_warning:
            response = middleware(mock_request)

            mock_logout.assert_called_once_with(mock_request)
            mock_warning.assert_called_once()
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, '/login/')
            mock_get_response.assert_not_called()

    def test_middleware_allows_admin_and_cajero(self):
        from unittest.mock import Mock, patch
        from usuarios.middleware import BloqueoAsistenteWebMiddleware

        mock_get_response = Mock(return_value='next_response')
        middleware = BloqueoAsistenteWebMiddleware(mock_get_response)

        mock_request = Mock()
        mock_request.user.is_authenticated = True
        mock_request.user.es_asistente = False

        with patch('usuarios.middleware.logout') as mock_logout:
            response = middleware(mock_request)
            mock_logout.assert_not_called()
            self.assertEqual(response, 'next_response')
            mock_get_response.assert_called_once_with(mock_request)



