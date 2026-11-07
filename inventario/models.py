from django.db import models

from categorias.models import Categoria


class Producto(models.Model):
    producto_id = models.AutoField(primary_key=True)
    categoria = models.ForeignKey(
        Categoria,
        db_column='categoria_id',
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name='productos',
        verbose_name='Categoría',
    )
    nombre = models.CharField(max_length=255, verbose_name="Nombre")
    precio_compra = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Precio de compra",
    )
    precio_venta = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Precio de venta",
    )
    cantidad = models.PositiveIntegerField(verbose_name="Cantidad")
    imagen = models.CharField(max_length=255, null=True, blank=True, verbose_name="Imagen")
    activo = models.BooleanField(default=True)
    version = models.IntegerField(default=0, verbose_name="Versión de concurrencia")

    class Meta:
        managed = False
        db_table = 'productos'
        verbose_name = 'producto'
        verbose_name_plural = 'productos'

    def __str__(self) -> str:
        return self.nombre


class MovimientoInventario(models.Model):
    TIPO_CHOICES = [
        ('VENTA', 'Venta'),
        ('AJUSTE', 'Ajuste manual'),
        ('ANULACION', 'Anulación de venta'),
        ('ENTRADA', 'Entrada de mercancía'),
    ]

    movimiento_id = models.AutoField(primary_key=True)
    producto = models.ForeignKey(
        Producto,
        db_column='producto_id',
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name='movimientos',
        verbose_name='Producto',
    )
    usuario = models.ForeignKey(
        'usuarios.Usuario',
        db_column='usuario_id',
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name='movimientos_inventario',
        verbose_name='Usuario',
    )
    tipo = models.CharField(max_length=50, choices=TIPO_CHOICES, verbose_name='Tipo de movimiento')
    delta = models.IntegerField(verbose_name='Variación de stock')
    stock_resultante = models.IntegerField(verbose_name='Stock resultante')
    motivo = models.CharField(max_length=255, verbose_name='Motivo')
    referencia_id = models.IntegerField(null=True, blank=True, verbose_name='ID de referencia')
    fecha = models.DateTimeField(auto_now_add=True, verbose_name='Fecha y hora')

    class Meta:
        managed = False
        db_table = 'movimientos_inventario'
        verbose_name = 'movimiento de inventario'
        verbose_name_plural = 'movimientos de inventario'
        ordering = ['-fecha']

    def __str__(self):
        signo = '+' if self.delta > 0 else ''
        return f"{self.tipo} ({signo}{self.delta}) - {self.producto.nombre}"
