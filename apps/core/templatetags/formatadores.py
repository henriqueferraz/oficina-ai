from django import template

from apps.core.validators import formatar_telefone

register = template.Library()


@register.filter(name="telefone")
def telefone_filter(value):
    """Exibe telefone mascarado: (XX) XXXX-XXXX ou (XX) XXXXX-XXXX."""
    if not value:
        return value
    return formatar_telefone(str(value))
