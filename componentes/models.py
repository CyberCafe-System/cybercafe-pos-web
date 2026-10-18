from django.db import models

from equipos.models import Equipo


class Componente(models.Model):
    TIPO_CHOICES = [
        ('MOUSE', 'Mouse'),
        ('TECLADO', 'Teclado'),
        ('MONITOR', 'Monitor'),
        ('CONTROL', 'Control'),
    ]

    ESTADO_CHOICES = [
        ('DISPONIBLE', 'Disponible'),
        ('DANIOS_MENORES', 'Daños Menores'),
        ('REQUIERE_REEMPLAZO', 'Requiere Reemplazo'),
    ]

    componente_id = models.AutoField(primary_key=True)
    equipo = models.ForeignKey(
        Equipo,
        db_column='equipo_id',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
        related_name='componentes',
        verbose_name="Equipo Asignado",
    )
    nombre = models.CharField(max_length=255, verbose_name="Nombre")
    numero_serie = models.CharField(
        max_length=100, null=True, blank=True, verbose_name="Número de Serie"
    )
    tipo = models.CharField(
        max_length=50, choices=TIPO_CHOICES, default='MOUSE', verbose_name="Tipo"
    )
    estado = models.CharField(
        max_length=50, choices=ESTADO_CHOICES, default='DISPONIBLE', verbose_name="Estado"
    )
    descripcion = models.TextField(null=True, blank=True, verbose_name="Descripción")
    observaciones = models.TextField(null=True, blank=True, verbose_name="Observaciones")
    imagen = models.CharField(max_length=255, null=True, blank=True, verbose_name="Imagen")
    activo = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = 'componentes'
        verbose_name = 'componente'
        verbose_name_plural = 'componentes'

    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_display()})"
