import re
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password


class SeguridadIntermediaPasswordValidator:
    """
    Validador de seguridad para contraseñas de usuarios:
    - Longitud mínima de 8 caracteres.
    - Debe contener al menos una letra mayúscula.
    - Debe contener al menos un dígito numérico (0-9).
    """

    def __init__(self, min_length=8, max_length=128):
        self.min_length = min_length
        self.max_length = max_length

    def validate(self, password, user=None):
        if not password or len(password) < self.min_length:
            raise ValidationError(
                f'La contraseña debe tener al menos {self.min_length} caracteres.',
                code='password_too_short',
            )
        if len(password) > self.max_length:
            raise ValidationError(
                f'La contraseña no debe superar los {self.max_length} caracteres.',
                code='password_too_long',
            )
        if not re.search(r'[A-Z]', password):
            raise ValidationError(
                'La contraseña debe contener al menos una letra mayúscula.',
                code='password_no_upper',
            )
        if not re.search(r'\d', password):
            raise ValidationError(
                'La contraseña debe contener al menos un número.',
                code='password_no_numbers',
            )

    def get_help_text(self):
        return f'Tu contraseña debe tener al menos {self.min_length} caracteres, con al menos una mayúscula y un número.'


def validar_password_intermedia(password, user=None):
    """
    Ejecuta el conjunto completo de validaciones de seguridad de contraseñas de Django
    (incluyendo similitud con usuario, longitud mínima, mayúscula, número, no ser común).
    """
    validator = SeguridadIntermediaPasswordValidator(min_length=8, max_length=128)
    validator.validate(password, user=user)
    validate_password(password, user=user)
