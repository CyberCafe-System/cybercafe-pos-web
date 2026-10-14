from django.db import models


class Cliente(models.Model):
    cliente_id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=255, verbose_name="Nombre")
    apellido = models.CharField(max_length=255, verbose_name="Apellido")
    dui = models.CharField(max_length=10, verbose_name="DUI")
    direccion = models.CharField(max_length=255, verbose_name="Dirección")
    telefono = models.IntegerField(verbose_name="Teléfono")
    correo = models.EmailField(max_length=255, null=True, blank=True, verbose_name="Correo")

    class Meta:
        managed = False
        db_table = 'clientes'
        verbose_name = 'cliente'
        verbose_name_plural = 'clientes'

    def __str__(self) -> str:
        return f'{self.nombre} {self.apellido}'
