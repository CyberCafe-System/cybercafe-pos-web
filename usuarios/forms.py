from django import forms
from django.contrib.auth.forms import AuthenticationForm, ReadOnlyPasswordHashField

from .models import Usuario
from .validators import validar_password_intermedia


class WebAuthenticationForm(AuthenticationForm):
    """
    Formulario de autenticación para la plataforma Web.
    Bloquea el inicio de sesión a usuarios con rol Asistente, reservándolo exclusivamente para la app móvil.
    """
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if getattr(user, 'es_asistente', False):
            raise forms.ValidationError(
                'El usuario con rol Asistente solo tiene acceso a través de la aplicación móvil.',
                code='asistente_web_blocked',
            )


class UsuarioCreationForm(forms.ModelForm):
    nombre = forms.CharField(
        max_length=50,
        label='Nombre completo',
        widget=forms.TextInput(attrs={'maxlength': '50'}),
    )
    username = forms.CharField(
        max_length=50,
        label='Nombre de usuario',
        widget=forms.TextInput(attrs={'maxlength': '50'}),
    )
    correo = forms.EmailField(
        max_length=75,
        label='Correo electrónico',
        widget=forms.EmailInput(attrs={'maxlength': '75'}),
    )
    password1 = forms.CharField(
        label='Contraseña',
        min_length=8,
        max_length=15,
        widget=forms.PasswordInput(attrs={'placeholder': '********', 'minlength': '8', 'maxlength': '15'}),
        help_text='Contraseña de 8 a 15 caracteres con al menos una mayúscula y un número.',
    )
    password2 = forms.CharField(
        label='Confirmar contraseña',
        min_length=8,
        max_length=15,
        widget=forms.PasswordInput(attrs={'placeholder': '********', 'minlength': '8', 'maxlength': '15'}),
    )

    class Meta:
        model = Usuario
        fields = ('username', 'nombre', 'correo', 'rol', 'activo', 'is_superuser')

    def clean_password1(self):
        password = self.cleaned_data.get('password1')
        if password:
            temp_user = Usuario(
                username=self.cleaned_data.get('username'),
                nombre=self.cleaned_data.get('nombre'),
                correo=self.cleaned_data.get('correo'),
            )
            validar_password_intermedia(password, user=temp_user)
        return password

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError('Las contraseñas no coinciden.')
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class UsuarioChangeForm(forms.ModelForm):
    nombre = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={'maxlength': '50'}),
    )
    username = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={'maxlength': '50'}),
    )
    correo = forms.EmailField(
        max_length=75,
        widget=forms.EmailInput(attrs={'maxlength': '75'}),
    )
    password = ReadOnlyPasswordHashField(label='Contraseña')

    class Meta:
        model = Usuario
        fields = (
            'username',
            'nombre',
            'correo',
            'rol',
            'activo',
            'is_superuser',
            'password',
            'last_login',
        )


class UsuarioCreateForm(forms.ModelForm):
    nombre = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control', 'maxlength': '50'}),
    )
    username = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control', 'maxlength': '50'}),
    )
    correo = forms.EmailField(
        max_length=75,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'maxlength': '75'}),
    )
    password = forms.CharField(
        label='Contraseña',
        min_length=8,
        max_length=15,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': '********',
            'minlength': '8',
            'maxlength': '15',
        }),
    )

    class Meta:
        model = Usuario
        fields = ('username', 'nombre', 'correo', 'rol')
        widgets = {
            'rol': forms.Select(attrs={'class': 'form-select'}),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        es_admin_rol = (user.rol_id == 1) or (
            getattr(user, 'rol', None) and getattr(user.rol, 'nombre', '').lower() == 'admin'
        )
        user.is_superuser = bool(es_admin_rol)
        if commit:
            user.save()
        return user

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if Usuario.objects.filter(username=username).exists():
            raise forms.ValidationError('No pueden haber dos usernames iguales.')
        return username

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if password:
            temp_user = Usuario(
                username=self.cleaned_data.get('username'),
                nombre=self.cleaned_data.get('nombre'),
                correo=self.cleaned_data.get('correo'),
            )
            validar_password_intermedia(password, user=temp_user)
        return password


class UsuarioEditForm(forms.ModelForm):
    nombre = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control', 'maxlength': '50'}),
    )
    username = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control', 'maxlength': '50'}),
    )
    correo = forms.EmailField(
        max_length=75,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'maxlength': '75'}),
    )

    class Meta:
        model = Usuario
        fields = ('username', 'nombre', 'correo', 'rol')
        widgets = {
            'rol': forms.Select(attrs={'class': 'form-select'}),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        es_admin_rol = (user.rol_id == 1) or (
            getattr(user, 'rol', None) and getattr(user.rol, 'nombre', '').lower() == 'admin'
        )
        user.is_superuser = bool(es_admin_rol)
        if commit:
            user.save()
        return user

    def clean_username(self):
        username = self.cleaned_data.get('username')
        qs = Usuario.objects.filter(username=username)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('No pueden haber dos usernames iguales.')
        return username
