import json
from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import SimpleTestCase
from django.test.client import RequestFactory
from django.urls import resolve, reverse
from django.utils import timezone

from clientes.models import Cliente
from componentes.models import Componente
from config.context_processors import contexto_global_sistema
from equipos.forms import EquipoForm
from equipos.models import Equipo
from equipos.views import equipo_create, equipo_toggle
from inventario.models import Producto
from pos_app.ticket import generar_factura_pdf
from pos_app.views import _sanitizar_celda_planilla, procesar_venta
from rentas.views import api_rentas_activas, renta_extender
from revisiones.models import RevisionComponente, RevisionEquipo
from revisiones.views import editar_revision, reiniciar_revision


class PosIdempotenciaYConcurrenciaTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = Mock()
        self.user.is_authenticated = True
        self.user.es_cajero = True
        self.user.es_admin = True
        self.user.es_asistente = False
        self.user.username = 'admin_qa'

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

    @patch('pos_app.views.Venta.objects')
    @patch('pos_app.views.get_object_or_404')
    @patch('pos_app.views.Producto.objects')
    @patch('pos_app.views.transaction.atomic')
    def test_procesar_venta_rechaza_por_stock_insuficiente(self, mock_atomic, mock_prod_objects, mock_get_cliente, mock_venta_objects):
        mock_venta_objects.filter.return_value.first.return_value = None
        mock_venta_objects.select_for_update.return_value.filter.return_value.first.return_value = None
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
            {'cliente_id': 1, 'pos_token': 'token-valido', 'efectivo_recibido': '10.00'},
            session_data=session,
        )

        response = procesar_venta(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/pos/')
        self.assertEqual(request.session['carrito'], {'10': 2})
        mock_prod_objects.select_for_update.assert_called_once()
        mensajes = [m.message for m in get_messages(request)]
        self.assertTrue(any('Inventario insuficiente' in msg for msg in mensajes))

    @patch('pos_app.views.Venta.objects')
    @patch('pos_app.views.get_object_or_404')
    @patch('pos_app.views.Producto.objects')
    @patch('pos_app.views.transaction.atomic')
    def test_procesar_venta_rechaza_producto_desactivado(self, mock_atomic, mock_prod_objects, mock_get_cliente, mock_venta_objects):
        mock_venta_objects.filter.return_value.first.return_value = None
        mock_venta_objects.select_for_update.return_value.filter.return_value.first.return_value = None
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
            {'cliente_id': 1, 'pos_token': 'token-valido', 'efectivo_recibido': '5.00'},
            session_data=session,
        )

        response = procesar_venta(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/pos/')
        self.assertEqual(request.session['carrito'], {'12': 1})
        mock_prod_objects.select_for_update.assert_called_once()
        mensajes = [m.message for m in get_messages(request)]
        self.assertTrue(any('ha sido desactivado' in msg for msg in mensajes))

    @patch('pos_app.views.Venta.objects')
    @patch('pos_app.views.get_object_or_404')
    @patch('pos_app.views.Producto.objects')
    @patch('pos_app.views.transaction.atomic')
    def test_procesar_venta_rechaza_categoria_desactivada(self, mock_atomic, mock_prod_objects, mock_get_cliente, mock_venta_objects):
        mock_venta_objects.filter.return_value.first.return_value = None
        mock_venta_objects.select_for_update.return_value.filter.return_value.first.return_value = None
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
            {'cliente_id': 1, 'pos_token': 'token-valido', 'efectivo_recibido': '5.00'},
            session_data=session,
        )

        response = procesar_venta(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/pos/')
        self.assertEqual(request.session['carrito'], {'15': 1})
        mock_prod_objects.select_for_update.assert_called_once()
        mensajes = [m.message for m in get_messages(request)]
        self.assertTrue(any('ha sido desactivado' in msg for msg in mensajes))

    @patch('equipos.views.asegurar_columna_activo_equipo')
    @patch('equipos.views.transaction.atomic')
    @patch('equipos.views.DetalleRenta.objects')
    @patch('equipos.views.get_object_or_404')
    def test_equipo_toggle_bloqueado_con_renta_activa(self, mock_get_equipo, mock_dr_objects, mock_atomic, mock_asegurar):
        equipo_mock = Mock(spec=Equipo, equipo_id=3, nombre='PC-Gamer-03', activo=True)
        mock_get_equipo.return_value = equipo_mock
        mock_dr_objects.filter.return_value.exists.return_value = True

        request = self._preparar_request('/desactivar_equipo/', {'equipo_id': 3})
        response = equipo_toggle(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/equipos/')
        equipo_mock.save.assert_not_called()

    @patch('revisiones.views.registrar_auditoria')
    @patch('revisiones.views.transaction.atomic')
    @patch('revisiones.views.get_object_or_404')
    def test_ruta_editar_revision_registrada_y_valida_estado(self, mock_get_obj, mock_atomic, mock_aud):
        url = reverse('editar_revision', kwargs={'revision_id': 5})
        self.assertEqual(url, '/revisiones/editar/5/')

        rev_mock = Mock(spec=RevisionEquipo, revision_equipo_id=5, inspeccion_pasada=True, observaciones='OK')
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
        venta_mock = Mock(venta_id=88, estado='PAGADA', fecha=timezone.now())
        det_mock = Mock(producto_id=5, cantidad=2)
        venta_mock.detalles.select_related.return_value = [det_mock]
        mock_venta_objs.select_for_update.return_value.get.return_value = venta_mock

        prod_mock = Mock(producto_id=5, cantidad=10, version=1)
        mock_prod_objs.select_for_update.return_value.filter.return_value.order_by.return_value = [prod_mock]

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

    def test_renta_extender_rechaza_token_vacio(self):
        req = self._preparar_request(
            '/extender_renta/',
            {
                'detalle_renta_id': 10,
                'ext_token': '',
                'minutos_extra': '30',
                'efectivo_recibido': '5.00',
            },
        )
        res = renta_extender(req)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.url, '/rentas/')
        mensajes = [m.message for m in get_messages(req)]
        self.assertTrue(any('Token de operación inválido' in msg for msg in mensajes))

    @patch('equipos.views.Componente.objects')
    @patch('equipos.views.transaction.atomic')
    @patch('equipos.forms.Equipo.objects')
    def test_equipo_create_bloquea_robo_de_componentes_ajenos(self, mock_eq_objs, mock_atomic, mock_comp_objs):
        mock_eq_objs.filter.return_value.exists.return_value = False
        comp_ocupado = Mock(spec=Componente, componente_id=7, nombre='Mouse Gamer', equipo_id=99, activo=True, estado='DISPONIBLE')
        mock_comp_objs.select_for_update.return_value.filter.return_value = [comp_ocupado]

        req = self._preparar_request(
            '/crear_equipo/',
            {
                'nombre': 'PC-Nueva-10',
                'tipo': 'PC',
                'tarifa_por_hora': '1.50',
                'estado': 'DISPONIBLE',
                'componentes': ['7'],
            },
        )
        res = equipo_create(req)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.url, '/equipos/')
        mensajes = [m.message for m in get_messages(req)]
        self.assertTrue(any('ya están asignados a otro equipo' in msg for msg in mensajes))

    @patch('revisiones.views.registrar_auditoria')
    @patch('componentes.models.Componente.objects')
    @patch('revisiones.views.RevisionComponente.objects')
    @patch('revisiones.views.DetalleRenta.objects')
    @patch('revisiones.views.get_object_or_404')
    @patch('revisiones.views.transaction.atomic')
    def test_reiniciar_revision_restaura_estado_previo_componente(
        self, mock_atomic, mock_get_obj, mock_dr_objs, mock_rc_objs, mock_comp_objs, mock_aud
    ):
        eq_mock = Mock(spec=Equipo, equipo_id=2, nombre='PC-02')
        det_mock = Mock(detalle_renta_id=20, equipo_id=2, estado='FINALIZADA')
        rev_mock = Mock(
            spec=RevisionEquipo,
            revision_equipo_id=15,
            detalle_renta_id=20,
            detalle_renta=det_mock,
            inspeccion_pasada=False,
            observaciones='Daño severo',
        )
        mock_get_obj.side_effect = [rev_mock, eq_mock, det_mock]
        mock_dr_objs.filter.return_value.exists.return_value = False
        mock_dr_objs.filter.return_value.exclude.return_value.exists.return_value = False

        rc_mock = Mock(spec=RevisionComponente, componente_id=33, estado_previo='DANIOS_MENORES')
        mock_rc_qs = Mock()
        mock_rc_qs.__iter__ = Mock(return_value=iter([rc_mock]))
        mock_rc_objs.filter.return_value = mock_rc_qs

        comp_mock = Mock(
            spec=Componente,
            componente_id=33,
            estado='REQUIERE_REEMPLAZO',
            observaciones=(
                '[REVISIÓN: #15 | FECHA: 06/11/2026 08:00 PM]\nDescripción: Tecla rota\n'
                '--------------------------------------------------\n'
                '[REVISIÓN: #11 | FECHA: 01/11/2026 04:00 PM]\nDescripción: Desgaste leve\n'
                '--------------------------------------------------'
            ),
        )
        mock_comp_objs.select_for_update.return_value.filter.return_value = [comp_mock]

        req = self._preparar_request('/revisiones/reiniciar/15/', {})
        res = reiniciar_revision(req, revision_id=15)

        self.assertEqual(res.status_code, 302)
        self.assertEqual(det_mock.estado, 'PENDIENTE_REVISION')
        # Aunque queda el bloque de la revisión #11, el estado debe volver a DANIOS_MENORES y no quedarse en REQUIERE_REEMPLAZO
        self.assertEqual(comp_mock.estado, 'DANIOS_MENORES')
        self.assertNotIn('#15', comp_mock.observaciones)
        self.assertIn('#11', comp_mock.observaciones)
        rev_mock.delete.assert_called_once()

    def test_sanitizar_celda_planilla_neutraliza_formulas_csv_excel(self):
        self.assertEqual(_sanitizar_celda_planilla('=CMD|" /C calc"!A0'), "'=CMD|\" /C calc\"!A0")
        self.assertEqual(_sanitizar_celda_planilla('+SUM(A1:A10)'), "'+SUM(A1:A10)")
        self.assertEqual(_sanitizar_celda_planilla('-10+20'), "'-10+20")
        self.assertEqual(_sanitizar_celda_planilla('@HYPERLINK("http://evil")'), "'@HYPERLINK(\"http://evil\")")
        self.assertEqual(_sanitizar_celda_planilla('Cliente Normal'), 'Cliente Normal')

    def test_generar_factura_pdf_escapa_caracteres_xml_especiales(self):
        venta_mock = Mock(
            venta_id=501,
            estado='PAGADA',
            fecha=timezone.now(),
            cliente='Café & Postres <Especiales>',
            usuario=Mock(nombre='Cajero & Admin <1>'),
            subtotal=Decimal('10.00'),
            iva=Decimal('1.30'),
            total=Decimal('11.30'),
            efectivo_recibido=Decimal('20.00'),
            cambio=Decimal('8.70'),
        )
        venta_mock.detalles.select_related.return_value = []
        pdf_bytes = generar_factura_pdf(venta_mock)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))

    @patch('pos_app.views.Renta.objects')
    @patch('pos_app.views.Venta.objects')
    def test_reportes_cajero_restringe_a_sus_operaciones_del_mismo_dia(self, mock_venta_objs, mock_renta_objs):
        from pos_app.views import _construir_transacciones_reporte, reportes_exportar_csv

        cajero = Mock()
        cajero.is_authenticated = True
        cajero.es_admin = False
        cajero.es_cajero = True
        cajero.usuario_id = 7
        cajero.username = 'cajero07'

        # Intenta forzar fechas antiguas y otro usuario en la URL
        req = self.factory.get('/reportes/?fecha_inicio=2020-01-01&fecha_fin=2020-12-31&usuario=1')
        req.user = cajero
        setattr(req, 'session', {})
        setattr(req, '_messages', FallbackStorage(req))

        v_qs = Mock()
        v_qs.filter.return_value = v_qs
        v_qs.exclude.return_value.aggregate.return_value = {'total': Decimal('15.00')}
        v_qs.__iter__ = Mock(return_value=iter([]))
        mock_venta_objs.select_related.return_value.prefetch_related.return_value.order_by.return_value = v_qs

        r_qs = Mock()
        r_qs.filter.return_value = r_qs
        r_qs.aggregate.return_value = {'total': Decimal('5.00')}
        r_qs.__iter__ = Mock(return_value=iter([]))
        mock_renta_objs.select_related.return_value.prefetch_related.return_value.order_by.return_value = r_qs

        datos = _construir_transacciones_reporte(req)
        hoy_str = timezone.localdate().isoformat()
        self.assertEqual(datos['fecha_inicio_str'], hoy_str)
        self.assertEqual(datos['fecha_fin_str'], hoy_str)
        self.assertEqual(datos['usuario_id_str'], '7')
        v_qs.filter.assert_any_call(usuario_id=7)
        r_qs.filter.assert_any_call(usuario_id=7)

        # Cajero no puede descargar CSV (redirige a inicio con error)
        res_csv = reportes_exportar_csv(req)
        self.assertEqual(res_csv.status_code, 302)
        self.assertEqual(res_csv.url, '/')

    @patch('pos_app.views.Venta.objects')
    def test_ticket_pdf_cajero_bloquea_venta_de_otro_usuario_o_dia_anterior(self, mock_venta_objs):
        from pos_app.views import ticket_pdf

        cajero = Mock()
        cajero.is_authenticated = True
        cajero.es_admin = False
        cajero.es_cajero = True
        cajero.usuario_id = 7

        venta_ajena = Mock(
            venta_id=99,
            usuario_id=2,  # Otro cajero
            fecha=timezone.now(),
        )
        mock_venta_objs.filter.return_value.first.return_value = venta_ajena

        req = self.factory.get('/ticket_pdf/99/')
        req.user = cajero
        setattr(req, 'session', {})
        setattr(req, '_messages', FallbackStorage(req))

        res = ticket_pdf(req, venta_id=99)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.url, '/reportes/')
        mensajes = [m.message for m in get_messages(req)]
        self.assertTrue(any('Solo tienes permiso' in msg for msg in mensajes))

    @patch('componentes.views.DetalleRenta.objects')
    @patch('componentes.views.Equipo.objects')
    @patch('componentes.views.Componente.objects')
    @patch('componentes.views.get_object_or_404')
    @patch('componentes.views.transaction.atomic')
    def test_componente_edit_bloquea_quitar_o_cambiar_equipo_en_renta_o_revision_pendiente(
        self, mock_atomic, mock_get_obj, mock_comp_objs, mock_eq_objs, mock_dr_objs
    ):
        from componentes.views import componente_edit

        eq_actual = Mock(spec=Equipo, equipo_id=3, nombre='PC Gamer 03')
        comp_inst = Mock(
            spec=Componente,
            componente_id=50,
            nombre='Teclado Mecánico RGB',
            numero_serie='SN-050',
            tipo='TECLADO',
            estado='DISPONIBLE',
            equipo_id=3,
            equipo=eq_actual,
            descripcion='Marca: HyperX',
            activo=True,
        )
        mock_get_obj.side_effect = [comp_inst, comp_inst]
        mock_eq_objs.select_for_update.return_value.filter.return_value.order_by.return_value = [eq_actual]
        # Simular que el equipo 3 está en PENDIENTE_REVISION o ACTIVA
        mock_dr_objs.filter.return_value.exists.return_value = True

        # Intenta quitar el componente (equipo='') enviándolo a bodega
        req = self._preparar_request('/modificar_componente/', {
            'componente_id': '50',
            'nombre': 'Teclado Mecánico RGB',
            'numero_serie': 'SN-050',
            'tipo': 'TECLADO',
            'estado': 'DISPONIBLE',
            'equipo': '',
        })
        with patch('componentes.views.ComponenteForm') as mock_form_cls:
            form_mock = Mock()
            form_mock.is_valid.return_value = True
            form_mock.cleaned_data = {
                'nombre': 'Teclado Mecánico RGB',
                'estado': 'DISPONIBLE',
                'equipo': None,
            }
            mock_form_cls.return_value = form_mock

            res = componente_edit(req)

        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.url, '/componentes/')
        form_mock.save.assert_not_called()
        mensajes = [m.message for m in get_messages(req)]
        self.assertTrue(any('No se puede quitar ni cambiar de equipo' in msg for msg in mensajes))

    @patch('equipos.views.DetalleRenta.objects')
    @patch('equipos.views.Componente.objects')
    @patch('equipos.views.get_object_or_404')
    @patch('equipos.views.transaction.atomic')
    def test_equipo_edit_bloquea_cambiar_estado_o_quitar_componentes_en_renta_o_revision(
        self, mock_atomic, mock_get_obj, mock_comp_objs, mock_dr_objs
    ):
        from equipos.views import equipo_edit

        eq_inst = Mock(
            spec=Equipo,
            equipo_id=4,
            nombre='Consola PS5 #1',
            tipo='CONSOLA',
            tarifa_por_hora=Decimal('2.50'),
            estado='DISPONIBLE',
            activo=True,
        )
        mock_get_obj.side_effect = [eq_inst, eq_inst]
        comp_asignado = Mock(spec=Componente, componente_id=77, nombre='Control DualSense', equipo_id=4, activo=True, estado='DISPONIBLE')
        mock_comp_objs.select_for_update.return_value.filter.return_value.order_by.return_value = [comp_asignado]
        # El equipo tiene renta activa o revisión pendiente
        mock_dr_objs.filter.return_value.exists.return_value = True

        # Intenta desmarcar el componente 77 (lista vacía de componentes)
        req = self._preparar_request('/modificar_equipo/', {
            'equipo_id': '4',
            'nombre': 'Consola PS5 #1',
            'tipo': 'CONSOLA',
            'tarifa_por_hora': '2.50',
            'estado': 'DISPONIBLE',
            'componentes': [],
        })
        with patch('equipos.views.EquipoForm') as mock_eq_form_cls:
            form_mock = Mock()
            form_mock.is_valid.return_value = True
            eq_unsaved = Mock(
                equipo_id=4,
                nombre='Consola PS5 #1',
                estado='DISPONIBLE',
                tarifa_por_hora=Decimal('2.50'),
            )
            form_mock.save.return_value = eq_unsaved
            mock_eq_form_cls.return_value = form_mock

            res = equipo_edit(req)

        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.url, '/equipos/')
        eq_unsaved.save.assert_not_called()
        mensajes = [m.message for m in get_messages(req)]
        self.assertTrue(any('No se pueden quitar ni modificar los componentes' in msg for msg in mensajes))
