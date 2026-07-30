"""Validação e formatação de documentos (CNPJ/CPF)."""

from __future__ import annotations


def apenas_digitos(valor: str) -> str:
    return "".join(ch for ch in (valor or "") if ch.isdigit())


def maiusculo(valor: str) -> str:
    """Normaliza texto de cadastro para maiúsculas."""
    return (valor or "").strip().upper()


def _digito_verificador(base: str, pesos: list[int]) -> int:
    soma = sum(int(base[i]) * pesos[i] for i in range(len(pesos)))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def cpf_valido(cpf: str) -> bool:
    """Valida CPF pelos dígitos verificadores (aceita mascarado ou só números)."""
    digitos = apenas_digitos(cpf)
    if len(digitos) != 11:
        return False
    if digitos == digitos[0] * 11:
        return False
    d1 = _digito_verificador(digitos[:9], list(range(10, 1, -1)))
    if int(digitos[9]) != d1:
        return False
    d2 = _digito_verificador(digitos[:10], list(range(11, 1, -1)))
    return int(digitos[10]) == d2


def formatar_cpf(cpf: str) -> str:
    digitos = apenas_digitos(cpf)
    if len(digitos) != 11:
        return (cpf or "").strip()
    return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"


def cnpj_valido(cnpj: str) -> bool:
    """Valida CNPJ pelos dígitos verificadores (aceita mascarado ou só números)."""
    digitos = apenas_digitos(cnpj)
    if len(digitos) != 14:
        return False
    if digitos == digitos[0] * 14:
        return False
    d1 = _digito_verificador(digitos[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    if int(digitos[12]) != d1:
        return False
    d2 = _digito_verificador(digitos[:13], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return int(digitos[13]) == d2


def formatar_cnpj(cnpj: str) -> str:
    digitos = apenas_digitos(cnpj)
    if len(digitos) != 14:
        return (cnpj or "").strip()
    return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"


def formatar_telefone(telefone: str) -> str:
    """Formata telefone BR: (XX) XXXX-XXXX ou (XX) XXXXX-XXXX."""
    digitos = apenas_digitos(telefone)[:11]
    if not digitos:
        return ""
    if len(digitos) <= 2:
        return f"({digitos}"
    ddd, num = digitos[:2], digitos[2:]
    if len(num) <= 4:
        return f"({ddd}) {num}"
    if len(digitos) <= 10:
        return f"({ddd}) {num[:4]}-{num[4:]}"
    return f"({ddd}) {num[:5]}-{num[5:]}"


UF_CHOICES = [
    ("", "—"),
    ("AC", "AC"),
    ("AL", "AL"),
    ("AP", "AP"),
    ("AM", "AM"),
    ("BA", "BA"),
    ("CE", "CE"),
    ("DF", "DF"),
    ("ES", "ES"),
    ("GO", "GO"),
    ("MA", "MA"),
    ("MT", "MT"),
    ("MS", "MS"),
    ("MG", "MG"),
    ("PA", "PA"),
    ("PB", "PB"),
    ("PR", "PR"),
    ("PE", "PE"),
    ("PI", "PI"),
    ("RJ", "RJ"),
    ("RN", "RN"),
    ("RS", "RS"),
    ("RO", "RO"),
    ("RR", "RR"),
    ("SC", "SC"),
    ("SP", "SP"),
    ("SE", "SE"),
    ("TO", "TO"),
]
