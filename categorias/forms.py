from django import forms
from django.core.exceptions import ValidationError

from .models import Categoria


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ('nombre', 'descripcion')
        widgets = {
            'nombre': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Ej. Bebidas Calientes, Snacks, Papelería'}
            ),
            'descripcion': forms.Textarea(
                attrs={'class': 'form-control', 'rows': 3}
            ),
        }

    def clean_nombre(self):
        nombre = (self.cleaned_data.get('nombre') or '').strip()
        if not nombre:
            raise ValidationError('El nombre de la categoría es obligatorio.')
        qs = Categoria.objects.filter(nombre__iexact=nombre)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f'Ya existe una categoría con el nombre "{nombre}".')
        return nombre
