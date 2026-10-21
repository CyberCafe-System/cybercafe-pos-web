import re
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password


class SeguridadIntermediaPasswordValidator:
    """
    Validador de seguridad intermedia para contraseñas de usuarios:
    - Longitud mínima de 8 caracteres.
    - Debe contener al menos una letra (mayúscula o minúscula).
    - Debe contener al menos un dígito numérico (0-9).
    """

    def __init__(self, min_length=8):
        self.min_length = min_length

    def validate(self, password, user=None):
        if not password or len(password) < self.min_length:
            raise ValidationError(
                f'La contraseña debe tener al menos {self.min_length} caracteres.',
                code='password_too_short',
            )
        if not re.search(r'[A-Za-z]', password):
            raise ValidationError(
                'La contraseña debe contener al menos una letra.',
                code='password_no_letters',
            )
        if not re.search(r'\d', password):
            raise ValidationError(
                'La contraseña debe contener al menos un número.',
                code='password_no_numbers',
            )

    def get_help_text(self):
        return f'Tu contraseña debe tener al menos {self.min_length} caracteres y combinar letras y números.'


def validar_password_intermedia(password, user=None):
    """
    Ejecuta el conjunto completo de validaciones de seguridad de contraseñas de Django
    (incluyendo similitud con usuario, longitud mínima, no ser común y regla intermedia).
    """
    # 1. Validación de seguridad intermedia explícita con mensajes claros en español
    validator = SeguridadIntermediaPasswordValidator(min_length=8)
    validator.validate(password, user=user)

    # 2. Validadores configurados en Django settings (Common, Similarity, Numeric)
    validate_password(password, user=user)
