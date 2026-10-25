import os

from decimal import Decimal, ROUND_HALF_UP

from django import forms

from categorias.models import Categoria
from .models import Producto
from .utils import procesar_imagen_a_webp

MONTO_MAXIMO = Decimal('99999.99')


class ProductoForm(forms.ModelForm):
    imagen_upload = forms.ImageField(
        required=False,
        label='Imagen del Producto',
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
    )

    class Meta:
        model = Producto
        fields = ('nombre', 'categoria', 'precio_compra', 'precio_venta', 'cantidad')
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'precio_compra': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '99999.99'}),
            'precio_venta': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '99999.99'}),
            'cantidad': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categoria'].queryset = Categoria.objects.filter(activa=True).order_by('nombre')
        self.fields['categoria'].empty_label = 'Seleccione una categoría'

    def clean_precio_compra(self):
        precio = self.cleaned_data.get('precio_compra')
        if precio is None:
            return precio
        if precio < 0:
            raise forms.ValidationError("El precio de compra no puede ser negativo.")
        if precio > MONTO_MAXIMO:
            raise forms.ValidationError("El precio de compra no puede ser mayor a $99,999.99.")
        return precio.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def clean_precio_venta(self):
        precio = self.cleaned_data.get('precio_venta')
        if precio is None:
            return precio
        if precio < 0:
            raise forms.ValidationError("El precio de venta no puede ser negativo.")
        if precio > MONTO_MAXIMO:
            raise forms.ValidationError("El precio de venta no puede ser mayor a $99,999.99.")
        return precio.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def clean_cantidad(self):
        cantidad = self.cleaned_data.get('cantidad')
        if cantidad is not None and cantidad < 0:
            raise forms.ValidationError("La cantidad no puede ser negativa.")
        return cantidad

    def save(self, commit=True):
        producto = super().save(commit=False)
        archivo = self.cleaned_data.get('imagen_upload')
        if archivo:
            imagen_anterior = self.instance.imagen if (self.instance and self.instance.pk) else None
            producto.imagen = procesar_imagen_a_webp(
                archivo,
                nombre_producto=producto.nombre,
                imagen_anterior=imagen_anterior,
            )
        if commit:
            producto.save()
        return producto
