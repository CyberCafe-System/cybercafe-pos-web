from django.db import models

from clientes.models import Cliente
from equipos.models import Equipo
from usuarios.models import Usuario


class Renta(models.Model):
    ESTADO_PAGO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('PAGADO', 'Pagado'),
    ]

    renta_id = models.AutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario,
        db_column='usuario_id',
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name='rentas',
        verbose_name="Atendido por",
    )
    cliente = models.ForeignKey(
        Cliente,
        db_column='cliente_id',
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name='rentas',
        verbose_name="Cliente",
    )
    fecha = models.DateTimeField(verbose_name="Fecha")
    total = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Total")
    estado_de_pago = models.CharField(
        max_length=50, choices=ESTADO_PAGO_CHOICES, default='PENDIENTE', verbose_name="Estado de Pago"
    )

    class Meta:
        managed = False
        db_table = 'rentas'
        verbose_name = 'renta'
        verbose_name_plural = 'rentas'

    def __str__(self):
        return f"Renta #{self.renta_id} - {self.cliente}"


class DetalleRenta(models.Model):
    ESTADO_CHOICES = [
        ('ACTIVA', 'Activa'),
        ('FINALIZADA', 'Finalizada'),
        ('PENDIENTE_REVISION', 'Pendiente de Revisión'),
    ]

    detalle_renta_id = models.AutoField(primary_key=True)
    renta = models.ForeignKey(
        Renta,
        db_column='renta_id',
        on_delete=models.CASCADE,
        db_constraint=False,
        related_name='detalles',
    )
    equipo = models.ForeignKey(
        Equipo,
        db_column='equipo_id',
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name='rentas_detalle',
    )
    hora_inicio = models.DateTimeField(verbose_name="Hora de Inicio")
    tiempo_de_renta = models.IntegerField(verbose_name="Tiempo de Renta (min)")
    tiempo_agregado = models.IntegerField(null=True, blank=True, default=0, verbose_name="Tiempo Agregado (min)")
    hora_fin = models.DateTimeField(null=True, blank=True, verbose_name="Hora Fin")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Subtotal")
    estado = models.CharField(max_length=50, choices=ESTADO_CHOICES, default='ACTIVA', verbose_name="Estado")

    class Meta:
        managed = False
        db_table = 'detalle_renta'
        verbose_name = 'detalle de renta'
        verbose_name_plural = 'detalles de renta'

    def __str__(self):
        return f"Detalle #{self.detalle_renta_id} - {self.equipo.nombre}"
