import re

from django import forms

from .models import Cliente


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ('nombre', 'apellido', 'dui', 'direccion', 'telefono', 'correo')
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Ej. Juan'}),
            'apellido': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Ej. Pérez'}),
            'dui': forms.TextInput(attrs={'class': 'form-control rounded-3', 'maxlength': '10', 'placeholder': '00000000-0'}),
            'direccion': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Dirección completa'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control rounded-3', 'maxlength': '8', 'placeholder': '70000000'}),
            'correo': forms.EmailInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'ejemplo@correo.com'}),
        }

    def clean_dui(self):
        dui = self.cleaned_data.get('dui', '').strip()
        # Si introdujo 9 dígitos continuos sin guion, formatear automáticamente
        solo_numeros = re.sub(r'\D', '', dui)
        if len(solo_numeros) == 9:
            dui = f"{solo_numeros[:8]}-{solo_numeros[8]}"
        elif not re.match(r'^\d{8}-\d{1}$', dui):
            raise forms.ValidationError("El DUI debe tener el formato 00000000-0 (8 dígitos y 1 verificador).")
        return dui

    def clean_telefono(self):
        telefono_val = self.cleaned_data.get('telefono')
        solo_digitos = re.sub(r'\D', '', str(telefono_val))
        if len(solo_digitos) < 7 or len(solo_digitos) > 8:
            raise forms.ValidationError("El teléfono debe contener entre 7 y 8 dígitos numéricos.")
        return int(solo_digitos)
