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
