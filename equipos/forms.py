from django import forms

from .models import Equipo


class EquipoForm(forms.ModelForm):
    class Meta:
        model = Equipo
        fields = ('nombre', 'tipo', 'tarifa_por_hora', 'estado', 'descripcion')
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. PC-01, Consola PS5'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'tarifa_por_hora': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'estado': forms.Select(attrs={'class': 'form-select'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Detalles técnicos o ubicación'}),
        }
