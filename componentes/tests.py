from unittest.mock import Mock, patch
from django.test import SimpleTestCase
from django.test.client import RequestFactory

from componentes.models import Componente
from componentes.views import componente_list


class ComponenteFiltrosTests(SimpleTestCase):
    def test_componente_list_filtros_tipo_estado_activo(self):
        factory = RequestFactory()
        req = factory.get('/componentes/?q=Logitech&tipo=MOUSE&estado=DISPONIBLE&activo=activos')
        req.user = Mock()
        req.user.is_authenticated = True
        req.user.es_admin = True

        with patch('componentes.views.Componente.objects.select_related') as mock_sr, \
             patch('componentes.views.Equipo.objects.all') as mock_eq, \
             patch('componentes.views.DetalleRenta.objects.filter') as mock_dr, \
             patch('componentes.views.render') as mock_render:
            mock_qs = mock_sr.return_value.all.return_value.order_by.return_value
            mock_qs.filter.return_value = mock_qs
            mock_eq.return_value.order_by.return_value = []
            mock_dr.return_value.values_list.return_value = []

            componente_list(req)
            self.assertTrue(mock_qs.filter.called)
            mock_render.assert_called_once()
            ctx = mock_render.call_args[0][2]
            self.assertEqual(ctx['q'], 'Logitech')
            self.assertEqual(ctx['tipo'], 'MOUSE')
            self.assertEqual(ctx['estado'], 'DISPONIBLE')
            self.assertEqual(ctx['activo'], 'activos')

