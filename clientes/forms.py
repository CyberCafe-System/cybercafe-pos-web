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

    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre', '').strip()
        if not nombre:
            raise forms.ValidationError("El nombre es obligatorio.")
        return nombre

    def clean_apellido(self):
        apellido = self.cleaned_data.get('apellido', '').strip()
        if not apellido:
            raise forms.ValidationError("El apellido es obligatorio.")
        return apellido

    def clean_direccion(self):
        direccion = self.cleaned_data.get('direccion', '').strip()
        if not direccion:
            raise forms.ValidationError("La dirección es obligatoria.")
        return direccion

    def clean_dui(self):
        dui = self.cleaned_data.get('dui', '').strip()
        if not dui:
            raise forms.ValidationError("El DUI es obligatorio.")
        solo_numeros = re.sub(r'\D', '', dui)
        if len(solo_numeros) == 9:
            dui = f"{solo_numeros[:8]}-{solo_numeros[8]}"
        elif not re.match(r'^\d{8}-\d{1}$', dui):
            raise forms.ValidationError("El DUI debe tener el formato 00000000-0 (8 dígitos y 1 verificador).")

        qs = Cliente.objects.filter(dui=dui)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"Ya existe un cliente registrado con el DUI {dui}.")
        return dui

    def clean_telefono(self):
        telefono_val = self.cleaned_data.get('telefono')
        if not telefono_val and telefono_val != 0:
            raise forms.ValidationError("El número de teléfono es obligatorio.")
        solo_digitos = re.sub(r'\D', '', str(telefono_val))
        if len(solo_digitos) != 8:
            raise forms.ValidationError("El número de teléfono debe contener exactamente 8 números.")
        return int(solo_digitos)
