from django.db import models


class Equipo(models.Model):
    TIPO_CHOICES = [
        ('PC', 'PC'),
        ('CONSOLA', 'Consola'),
    ]

    ESTADO_CHOICES = [
        ('DISPONIBLE', 'Disponible'),
        ('DANIOS_MENORES', 'Daños Menores'),
        ('DEFECTUOSO', 'Defectuoso'),
        ('EN_MANTENIMIENTO', 'En Mantenimiento'),
    ]

    equipo_id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=255, verbose_name="Nombre")
    descripcion = models.TextField(null=True, blank=True, verbose_name="Descripción")
    tarifa_por_hora = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Tarifa por hora")
    imagen = models.CharField(max_length=255, null=True, blank=True, verbose_name="Imagen")
    tipo = models.CharField(max_length=50, choices=TIPO_CHOICES, default='PC')
    estado = models.CharField(max_length=50, choices=ESTADO_CHOICES, default='DISPONIBLE')

    class Meta:
        managed = False
        db_table = 'equipos'
        verbose_name = 'equipo'
        verbose_name_plural = 'equipos'

    def __str__(self):
        return f"{self.nombre} ({self.tipo})"
