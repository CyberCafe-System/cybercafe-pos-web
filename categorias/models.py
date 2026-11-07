from django.db import models


class Categoria(models.Model):
    categoria_id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=150, verbose_name="Nombre")
    descripcion = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="Descripcion"
    )
    activa = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = 'categorias'
        verbose_name = 'categoria'
        verbose_name_plural = 'categorias'

    def __str__(self) -> str:
        return self.nombre
