from unittest.mock import Mock, patch

from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase
from django.test.client import RequestFactory

from .models import Rol, Usuario
from .views import usuario_edit, usuario_toggle


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



class UsuarioGestionRolesTests(SimpleTestCase):
    """Reglas de rol/estado y serialización para evitar carreras entre administradores."""

    def setUp(self):
        self.factory = RequestFactory()
        self.mock_atomic = self._patch('usuarios.views.transaction.atomic')
        self.mock_ids_admin = self._patch('usuarios.views._ids_roles_administrador')
        self.mock_ids_admin.return_value = {1}
        self.mock_lock = self._patch('usuarios.views._bloquear_administradores')
        self.mock_lock.return_value = []
        self.mock_audit = self._patch('usuarios.views.registrar_auditoria')
        self.mock_error = self._patch('usuarios.views.messages.error')
        self.mock_success = self._patch('usuarios.views.messages.success')

    def _patch(self, target):
        patcher = patch(target)
        mock = patcher.start()
        self.addCleanup(patcher.stop)
        return mock

    def _request(self, actor_id, target_id, rol=None, url='/modificar_usuario/'):
        data = {'usuario_id': str(target_id)}
        if rol is not None:
            data['rol'] = str(rol)
        request = self.factory.post(url, data=data)
        request.user = Mock()
        request.user.is_authenticated = True
        request.user.es_admin = True
        request.user.usuario_id = actor_id
        return request

    def _usuario(self, usuario_id, rol_id, activo=True):
        usuario = Mock()
        usuario.usuario_id = usuario_id
        usuario.pk = usuario_id
        usuario.rol_id = rol_id
        usuario.activo = activo
        usuario.nombre = f'Usuario {usuario_id}'
        usuario.correo = f'usuario{usuario_id}@test.com'
        usuario.username = f'usuario{usuario_id}'
        return usuario

    def _form_edit(self, valido, guardado=None):
        mock_form_cls = self._patch('usuarios.views.UsuarioEditForm')
        mock_form_cls.return_value.is_valid.return_value = valido
        mock_form_cls.return_value.errors = {}
        if guardado is not None:
            mock_form_cls.return_value.save.return_value = guardado
        return mock_form_cls

    def _target(self, usuario):
        self._patch('usuarios.views.get_object_or_404').return_value = usuario

    # --- Cambio de rol ---------------------------------------------------

    def test_admin_cannot_change_own_role(self):
        usuario_actual = self._usuario(7, 1)
        self._target(usuario_actual)
        mock_form_cls = self._form_edit(valido=True)
        self.mock_lock.return_value = [usuario_actual]

        response = usuario_edit(self._request(actor_id=7, target_id=7, rol=2))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/usuarios/')
        mock_form_cls.assert_not_called()
        self.mock_error.assert_called_once()
        self.assertIn('propio rol', self.mock_error.call_args[0][1])

    def test_admin_can_save_own_profile_keeping_same_role(self):
        usuario_actual = self._usuario(7, 1)
        self._target(usuario_actual)
        mock_form_cls = self._form_edit(valido=False)
        self.mock_lock.return_value = [usuario_actual]

        response = usuario_edit(self._request(actor_id=7, target_id=7, rol=1))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/usuarios/')
        mock_form_cls.assert_called_once()
        self.mock_error.assert_not_called()

    def test_admin_can_change_role_of_another_user(self):
        otro_usuario = self._usuario(8, 2)
        self._target(otro_usuario)
        mock_form_cls = self._form_edit(valido=False)
        self.mock_lock.return_value = [self._usuario(7, 1), otro_usuario]

        response = usuario_edit(self._request(actor_id=7, target_id=8, rol=3))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/usuarios/')
        mock_form_cls.assert_called_once()
        self.mock_error.assert_not_called()

    def test_cannot_demote_last_active_admin(self):
        # Escenario de carrera: el actor ya fue degradado por otra transacción,
        # por lo que el único admin activo restante es el objetivo.
        objetivo = self._usuario(8, 1, activo=True)
        self._target(objetivo)
        guardado = self._usuario(8, 2, activo=True)
        self._form_edit(valido=True, guardado=guardado)
        self.mock_lock.return_value = [objetivo]

        response = usuario_edit(self._request(actor_id=7, target_id=8, rol=2))

        self.assertEqual(response.status_code, 302)
        self.mock_error.assert_called_once()
        self.assertIn('único Administrador activo', self.mock_error.call_args[0][1])
        guardado.save.assert_not_called()
        self.mock_audit.assert_not_called()

    def test_can_demote_admin_when_another_active_admin_remains(self):
        objetivo = self._usuario(8, 1, activo=True)
        self._target(objetivo)
        guardado = self._usuario(8, 2, activo=True)
        self._form_edit(valido=True, guardado=guardado)
        self.mock_lock.return_value = [objetivo, self._usuario(9, 1, activo=True)]

        response = usuario_edit(self._request(actor_id=7, target_id=8, rol=2))

        self.assertEqual(response.status_code, 302)
        guardado.save.assert_called_once()
        self.mock_audit.assert_called_once()
        self.mock_success.assert_called_once()
        self.mock_error.assert_not_called()

    # --- Activación / desactivación --------------------------------------

    def test_cannot_deactivate_last_active_admin(self):
        objetivo = self._usuario(8, 1, activo=True)
        self._target(objetivo)
        self.mock_lock.return_value = [objetivo]

        response = usuario_toggle(self._request(actor_id=7, target_id=8, url='/desactivar_usuario/'))

        self.assertEqual(response.status_code, 302)
        self.mock_error.assert_called_once()
        self.assertIn('único Administrador activo', self.mock_error.call_args[0][1])
        objetivo.save.assert_not_called()
        self.mock_audit.assert_not_called()

    def test_can_deactivate_admin_when_another_active_admin_remains(self):
        objetivo = self._usuario(8, 1, activo=True)
        self._target(objetivo)
        self.mock_lock.return_value = [objetivo, self._usuario(9, 1, activo=True)]

        response = usuario_toggle(self._request(actor_id=7, target_id=8, url='/desactivar_usuario/'))

        self.assertEqual(response.status_code, 302)
        objetivo.save.assert_called_once_with(update_fields=['activo'])
        self.mock_audit.assert_called_once()
        self.mock_success.assert_called_once()
        self.mock_error.assert_not_called()

    def test_cannot_deactivate_own_account(self):
        objetivo = self._usuario(7, 1, activo=True)
        self._target(objetivo)
        self.mock_lock.return_value = [objetivo, self._usuario(9, 1, activo=True)]

        response = usuario_toggle(self._request(actor_id=7, target_id=7, url='/desactivar_usuario/'))

        self.assertEqual(response.status_code, 302)
        self.mock_error.assert_called_once()
        self.assertIn('propia cuenta', self.mock_error.call_args[0][1])
        objetivo.save.assert_not_called()


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





class UsuarioValidationRulesTests(SimpleTestCase):
    def test_password_validator_rejects_under_8_chars(self):
        from usuarios.validators import SeguridadIntermediaPasswordValidator
        from django.core.exceptions import ValidationError

        validator = SeguridadIntermediaPasswordValidator(min_length=8, max_length=15)
        with self.assertRaises(ValidationError) as ctx:
            validator.validate('Pass1')
        self.assertEqual(ctx.exception.code, 'password_too_short')

    def test_password_validator_rejects_over_15_chars(self):
        from usuarios.validators import SeguridadIntermediaPasswordValidator
        from django.core.exceptions import ValidationError

        validator = SeguridadIntermediaPasswordValidator(min_length=8, max_length=15)
        with self.assertRaises(ValidationError) as ctx:
            validator.validate('Password123456789')
        self.assertEqual(ctx.exception.code, 'password_too_long')

    def test_password_validator_requires_uppercase(self):
        from usuarios.validators import SeguridadIntermediaPasswordValidator
        from django.core.exceptions import ValidationError

        validator = SeguridadIntermediaPasswordValidator(min_length=8, max_length=15)
        with self.assertRaises(ValidationError) as ctx:
            validator.validate('password123')
        self.assertEqual(ctx.exception.code, 'password_no_upper')

    def test_password_validator_requires_number(self):
        from usuarios.validators import SeguridadIntermediaPasswordValidator
        from django.core.exceptions import ValidationError

        validator = SeguridadIntermediaPasswordValidator(min_length=8, max_length=15)
        with self.assertRaises(ValidationError) as ctx:
            validator.validate('PasswordABC')
        self.assertEqual(ctx.exception.code, 'password_no_numbers')

    def test_password_validator_accepts_valid_password(self):
        from usuarios.validators import SeguridadIntermediaPasswordValidator

        validator = SeguridadIntermediaPasswordValidator(min_length=8, max_length=15)
        self.assertIsNone(validator.validate('Clave123'))
        self.assertIsNone(validator.validate('Clave1234567890'))

    def test_form_max_lengths(self):
        from usuarios.forms import UsuarioCreateForm, UsuarioEditForm

        create_form = UsuarioCreateForm()
        self.assertEqual(create_form.fields['nombre'].max_length, 50)
        self.assertEqual(create_form.fields['username'].max_length, 50)
        self.assertEqual(create_form.fields['correo'].max_length, 75)
        self.assertEqual(create_form.fields['password'].max_length, 15)
        self.assertEqual(create_form.fields['password'].min_length, 8)

        edit_form = UsuarioEditForm()
        self.assertEqual(edit_form.fields['nombre'].max_length, 50)
        self.assertEqual(edit_form.fields['username'].max_length, 50)
        self.assertEqual(edit_form.fields['correo'].max_length, 75)

    def test_username_normalized_to_lowercase_on_save_and_forms(self):
        from django.contrib.auth.base_user import AbstractBaseUser
        from usuarios.forms import UsuarioCreateForm, UsuarioEditForm, WebAuthenticationForm

        user = Usuario(username='  CaJeRo_PrInCiPaL  ', rol_id=2)
        with patch.object(AbstractBaseUser, 'save', autospec=True):
            user.save()
        self.assertEqual(user.username, 'cajero_principal')

        form_create = UsuarioCreateForm()
        form_create.cleaned_data = {'username': '  AdMiN_NuEvO  '}
        with patch('usuarios.forms.Usuario.objects.filter') as mock_filter:
            mock_filter.return_value.exists.return_value = False
            self.assertEqual(form_create.clean_username(), 'admin_nuevo')
            mock_filter.assert_called_once_with(username__iexact='admin_nuevo')

        form_edit = UsuarioEditForm()
        form_edit.instance = Mock(pk=5)
        form_edit.cleaned_data = {'username': '  UsUaRiO_EdItAdO '}
        with patch('usuarios.forms.Usuario.objects.filter') as mock_filter_edit:
            mock_filter_edit.return_value.exclude.return_value.exists.return_value = False
            self.assertEqual(form_edit.clean_username(), 'usuario_editado')
            mock_filter_edit.assert_called_once_with(username__iexact='usuario_editado')

        auth_form = WebAuthenticationForm()
        auth_form.cleaned_data = {'username': '  CAJERO01 '}
        self.assertEqual(auth_form.clean_username(), 'cajero01')

    def test_obtener_ip_cliente_y_middleware_detras_de_proxy_vps(self):
        from usuarios.middleware import RealClientIPMiddleware
        from usuarios.models import obtener_ip_cliente, registrar_auditoria

        factory = RequestFactory()
        # 1. X-Forwarded-For con IP pública del cliente y proxy interno
        req = factory.get(
            '/usuarios/',
            REMOTE_ADDR='127.0.0.1',
            HTTP_X_FORWARDED_FOR='190.86.45.12, 10.0.0.1',
        )
        self.assertEqual(obtener_ip_cliente(req), '190.86.45.12')

        # 2. Cloudflare CF-Connecting-IP tiene prioridad
        req_cf = factory.get(
            '/usuarios/',
            REMOTE_ADDR='127.0.0.1',
            HTTP_CF_CONNECTING_IP='168.243.10.99',
            HTTP_X_FORWARDED_FOR='172.18.0.2',
        )
        self.assertEqual(obtener_ip_cliente(req_cf), '168.243.10.99')

        # 3. Middleware actualiza REMOTE_ADDR para todas las vistas y axes
        middleware = RealClientIPMiddleware(lambda r: r)
        middleware(req)
        self.assertEqual(req.META['REMOTE_ADDR'], '190.86.45.12')
        self.assertEqual(req.client_ip, '190.86.45.12')

        # 4. registrar_auditoria limpia la IP antes de guardar
        with patch('usuarios.models.Auditoria.objects.create') as mock_create:
            registrar_auditoria(
                usuario=None,
                accion='CREAR_USUARIO',
                entidad='Usuario',
                entidad_id=1,
                ip='::ffff:190.86.45.12',
            )
            mock_create.assert_called_once()
            self.assertEqual(mock_create.call_args.kwargs['ip'], '190.86.45.12')
