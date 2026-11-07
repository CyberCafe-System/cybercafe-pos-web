from django.db import models
from rentas.models import DetalleRenta
from usuarios.models import Usuario


class RevisionEquipo(models.Model):
    revision_equipo_id = models.AutoField(primary_key=True)
    detalle_renta = models.ForeignKey(
        DetalleRenta,
        db_column='detalle_renta_id',
        on_delete=models.CASCADE,
        db_constraint=False,
        related_name='revisiones',
        verbose_name='Sesión de Renta',
    )
    usuario = models.ForeignKey(
        Usuario,
        db_column='usuario_id',
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name='revisiones_realizadas',
        verbose_name='Inspector / Técnico',
    )
    inspeccion_pasada = models.BooleanField(
        default=True,
        verbose_name='¿Pasó la Inspección?',
    )
    observaciones = models.TextField(
        null=True,
        blank=True,
        verbose_name='Observaciones y Diagnóstico',
    )
    fecha_revision = models.DateTimeField(
        verbose_name='Fecha y Hora de Revisión',
    )

    class Meta:
        managed = False
        db_table = 'revisiones_equipo'
        verbose_name = 'revisión de equipo'
        verbose_name_plural = 'revisiones de equipos'
        ordering = ['-fecha_revision']

    def __str__(self):
        resultado = "Aprobada" if self.inspeccion_pasada else "Con Daños"
        equipo_nombre = (
            self.detalle_renta.equipo.nombre
            if self.detalle_renta and self.detalle_renta.equipo
            else f"Detalle #{self.detalle_renta_id}"
        )
        return f"Revisión #{self.revision_equipo_id} - {equipo_nombre} ({resultado})"


class RevisionComponente(models.Model):
    id = models.AutoField(primary_key=True)
    revision_equipo = models.ForeignKey(
        RevisionEquipo,
        db_column='revision_equipo_id',
        on_delete=models.CASCADE,
        db_constraint=False,
        related_name='componentes_revisados',
        verbose_name='Revisión de Equipo',
    )
    componente = models.ForeignKey(
        'componentes.Componente',
        db_column='componente_id',
        on_delete=models.CASCADE,
        db_constraint=False,
        related_name='revisiones_componente',
        verbose_name='Componente',
    )
    estado_previo = models.CharField(max_length=50, verbose_name='Estado Previo')
    estado_nuevo = models.CharField(max_length=50, verbose_name='Estado Nuevo')
    descripcion = models.TextField(null=True, blank=True, verbose_name='Descripción de la novedad')

    class Meta:
        managed = False
        db_table = 'revision_componentes'
        verbose_name = 'revisión de componente'
        verbose_name_plural = 'revisiones de componentes'

    def __str__(self):
        return f"Componente #{self.componente_id} en Rev #{self.revision_equipo_id}: {self.estado_previo} -> {self.estado_nuevo}"
