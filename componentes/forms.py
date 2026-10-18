from django import forms

from equipos.models import Equipo

from .models import Componente


class ComponenteForm(forms.ModelForm):
    # Campos separados para capturar Marca y Modelo antes de unirlos en descripcion
    marca = forms.CharField(
        required=False,
        label='Marca',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Logitech, Dell, Samsung'}),
    )
    modelo = forms.CharField(
        required=False,
        label='Modelo',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. G203, OptiPlex, LC27G55'}),
    )

    class Meta:
        model = Componente
        fields = ('nombre', 'numero_serie', 'tipo', 'estado', 'equipo', 'observaciones')
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Mouse Gamer Principal'}),
            'numero_serie': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. SN-A4K-98203'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'estado': forms.Select(attrs={'class': 'form-select'}),
            'equipo': forms.Select(attrs={'class': 'form-select'}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Anotaciones adicionales'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Cargar equipos disponibles, ordenados, haciendo el campo opcional
        self.fields['equipo'].queryset = Equipo.objects.all().order_by('nombre')
        self.fields['equipo'].required = False
        self.fields['equipo'].empty_label = '— Sin asignar (Bodega) —'
        # Obtener marca y modelo actuales desde descripcion para pre-rellenar en edición
        if self.instance and self.instance.descripcion:
            desc = self.instance.descripcion
            for parte in desc.split(' | '):
                if parte.startswith('Marca:'):
                    self.fields['marca'].initial = parte.replace('Marca:', '').strip()
                elif parte.startswith('Modelo:'):
                    self.fields['modelo'].initial = parte.replace('Modelo:', '').strip()

    def save(self, commit=True):
        componente = super().save(commit=False)
        # Formatear Marca y Modelo en el campo descripcion
        marca = self.cleaned_data.get('marca', '').strip()
        modelo = self.cleaned_data.get('modelo', '').strip()
        partes_desc = []
        if marca:
            partes_desc.append(f'Marca: {marca}')
        if modelo:
            partes_desc.append(f'Modelo: {modelo}')
        componente.descripcion = ' | '.join(partes_desc) if partes_desc else None
        if commit:
            componente.save()
        return componente
