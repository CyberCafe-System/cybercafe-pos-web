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

    def evaluar_rentabilidad(self):
        """
        Evalúa si el equipo puede rentarse según las reglas de negocio:
        - El estado del equipo debe ser DISPONIBLE.
        - Ningún componente activo asignado puede estar en REQUIERE_REEMPLAZO ni DANIOS_MENORES.
        """
        if self.estado != 'DISPONIBLE':
            return False, f"El equipo se encuentra en estado '{self.get_estado_display()}'."

        try:
            comps_bloqueantes = self.componentes.filter(
                activo=True,
                estado__in=['REQUIERE_REEMPLAZO', 'DANIOS_MENORES']
            )
            if comps_bloqueantes.exists():
                nombres = ", ".join([f"{c.nombre} ({c.get_estado_display()})" for c in comps_bloqueantes])
                return False, f"Tiene componentes con reporte: {nombres}"
        except Exception:
            pass

        return True, "Disponible"

    @property
    def es_rentable(self) -> bool:
        if hasattr(self, '_es_rentable_override'):
            return self._es_rentable_override
        return self.evaluar_rentabilidad()[0]

    @es_rentable.setter
    def es_rentable(self, valor: bool):
        self._es_rentable_override = bool(valor)
