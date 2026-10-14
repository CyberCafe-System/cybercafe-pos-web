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

    class Meta:
        managed = False
        db_table = 'productos'
        verbose_name = 'producto'
        verbose_name_plural = 'productos'

    def __str__(self) -> str:
        return self.nombre
