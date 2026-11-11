import io
from pathlib import Path
from unittest.mock import Mock, patch
from PIL import Image
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from categorias.models import Categoria
from inventario.forms import ProductoForm
from inventario.models import Producto
from inventario.utils import procesar_imagen_a_webp


class WebPImageProcessingTests(SimpleTestCase):
    def test_image_conversion_to_webp(self):
        # Crear una imagen PNG en memoria (1000x800 px)
        buffer = io.BytesIO()
        test_img = Image.new('RGBA', (1000, 800), color=(255, 0, 0, 128))
        test_img.save(buffer, format='PNG')
        buffer.seek(0)

        uploaded = SimpleUploadedFile('test_photo.png', buffer.read(), content_type='image/png')

        # Procesar con la utilidad
        relative_path = procesar_imagen_a_webp(uploaded, 'Bebida Energizante')
        self.assertTrue(relative_path.endswith('.webp'))
        self.assertTrue(relative_path.startswith('productos/'))

        # Verificar que el archivo resultante en disco sea un WEBP válido y no exceda 600x600
        full_path = settings.MEDIA_ROOT / relative_path
        self.assertTrue(full_path.exists())

        try:
            with Image.open(full_path) as result_img:
                self.assertEqual(result_img.format, 'WEBP')
                self.assertLessEqual(result_img.width, 600)
                self.assertLessEqual(result_img.height, 600)
        finally:
            # Limpiar archivo de prueba
            if full_path.exists():
                full_path.unlink()

    def test_producto_form_rejects_negative_numbers(self):
        with patch.object(Categoria.objects, 'filter') as mock_cat_filter:
            mock_cat_filter.return_value.order_by.return_value = Categoria.objects.none()
            form = ProductoForm(data={
                'nombre': 'Doritos',
                'categoria': 1,
                'precio_compra': '-0.50',
                'precio_venta': '1.00',
                'cantidad': '-5',
            })
            self.assertFalse(form.is_valid())
            self.assertIn('precio_compra', form.errors)
            self.assertIn('cantidad', form.errors)

    def test_producto_form_rejects_oversized_images(self):
        with patch.object(Categoria.objects, 'filter') as mock_cat_filter:
            mock_cat_filter.return_value.order_by.return_value = Categoria.objects.none()
            # Crear un JPEG válido y expandir su tamaño por encima de 3 MB
            buf = io.BytesIO()
            img = Image.new('RGB', (20, 20), color='blue')
            img.save(buf, format='JPEG')
            raw = buf.getvalue() + (b'\x00' * (4 * 1024 * 1024))
            oversized_file = SimpleUploadedFile(
                'foto_pesada.jpg',
                raw,
                content_type='image/jpeg',
            )
            form = ProductoForm(
                data={
                    'nombre': 'Doritos',
                    'categoria': 1,
                    'precio_compra': '0.50',
                    'precio_venta': '1.00',
                    'cantidad': '5',
                },
                files={'imagen_upload': oversized_file},
            )
            self.assertFalse(form.is_valid())
            self.assertIn('imagen_upload', form.errors)
            self.assertIn('supera el tamaño máximo permitido de 3 MB', form.errors['imagen_upload'][0])

    def test_producto_list_filtros_categoria_estado_stock(self):
        from django.test.client import RequestFactory
        from inventario.views import producto_list

        factory = RequestFactory()
        req = factory.get('/inventario/?q=Doritos&categoria=2&estado=activos&stock=bajo_stock')
        req.user = Mock()
        req.user.is_authenticated = True
        req.user.es_admin = True

        with patch('inventario.views.Producto.objects.select_related') as mock_sr, \
             patch('inventario.views.Categoria.objects.filter') as mock_cat, \
             patch('inventario.views.render') as mock_render:
            mock_qs = mock_sr.return_value.all.return_value.order_by.return_value
            mock_qs.filter.return_value = mock_qs

            producto_list(req)
            self.assertTrue(mock_qs.filter.called)
            mock_render.assert_called_once()
            ctx = mock_render.call_args[0][2]
            self.assertEqual(ctx['q'], 'Doritos')
            self.assertEqual(ctx['categoria_id'], '2')
            self.assertEqual(ctx['estado'], 'activos')
            self.assertEqual(ctx['stock'], 'bajo_stock')
