from django.db import models

from clientes.models import Cliente
from inventario.models import Producto
from usuarios.models import Usuario


class Venta(models.Model):
    venta_id = models.AutoField(primary_key=True)
    cliente = models.ForeignKey(
        Cliente,
        db_column='cliente_id',
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name='ventas',
    )
    usuario = models.ForeignKey(
        Usuario,
        db_column='usuario_id',
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name='ventas',
    )
    clave_idempotencia = models.CharField(max_length=32, null=True, blank=True)
    fecha = models.DateTimeField()
    iva = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(max_length=50, default='COMPLETADA')
    efectivo_recibido = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cambio = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    anulada_por = models.ForeignKey(
        Usuario,
        db_column='anulada_por',
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True,
        blank=True,
        related_name='ventas_anuladas',
    )
    anulada_en = models.DateTimeField(null=True, blank=True)
    motivo_anulacion = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'ventas'
        verbose_name = 'venta'
        verbose_name_plural = 'ventas'

    def __str__(self):
        return f'Venta #{self.venta_id}'

    @property
    def total(self):
        return self.subtotal + self.iva

    @property
    def es_anulada(self):
        return self.estado == 'ANULADA'


class DetalleVenta(models.Model):
    detalle_venta_id = models.AutoField(primary_key=True)
    venta = models.ForeignKey(
        Venta,
        db_column='venta_id',
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name='detalles',
    )
    producto = models.ForeignKey(
        Producto,
        db_column='producto_id',
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name='detalles_venta',
    )
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    cantidad = models.IntegerField()
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        managed = False
        db_table = 'detalle_venta'
        verbose_name = 'detalle de venta'
        verbose_name_plural = 'detalles de venta'

    def __str__(self):
        return f'{self.cantidad} x {self.producto}'
