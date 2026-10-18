import os

from django import forms
from django.conf import settings

from categorias.models import Categoria

from .models import Producto


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
            'precio_compra': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'precio_venta': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'cantidad': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categoria'].queryset = Categoria.objects.filter(activa=True).order_by('nombre')
        self.fields['categoria'].empty_label = 'Seleccione una categoría'

    def save(self, commit=True):
        producto = super().save(commit=False)
        archivo = self.cleaned_data.get('imagen_upload')
        if archivo:
            # Guardar en media/productos/
            carpeta = settings.MEDIA_ROOT / 'productos'
            carpeta.mkdir(parents=True, exist_ok=True)
            nombre_archivo = f"{producto.nombre.lower().replace(' ', '_')}_{archivo.name}"
            ruta_fisica = carpeta / nombre_archivo
            with open(ruta_fisica, 'wb+') as destino:
                for chunk in archivo.chunks():
                    destino.write(chunk)
            producto.imagen = f"productos/{nombre_archivo}"
        if commit:
            producto.save()
        return producto
