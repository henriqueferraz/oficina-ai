"""Controle de acesso por papéis configuráveis da oficina."""

from __future__ import annotations

from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect
from django.utils.text import slugify

# Catálogo fixo de permissões (códigos → rótulo)
PERMISSOES_CATALOGO: list[tuple[str, str]] = [
    ("ordens", "Ordens de serviço"),
    ("orcamentos", "Orçamentos"),
    ("clientes", "Clientes"),
    ("veiculos", "Veículos"),
    ("catalogo", "Catálogo"),
    ("fornecedores", "Fornecedores"),
    ("compras", "Compras"),
    ("financeiro", "Financeiro"),
    ("relatorios", "Relatórios e comissões"),
    ("importar", "Importar CSV"),
    ("agente", "Agente IA"),
    ("equipe", "Equipe"),
    ("configuracoes", "Configurações e papéis"),
    ("painel_caixa", "Caixa no painel"),
    ("painel_ordens_recentes", "Ordens recentes no painel"),
    ("painel_estoque", "Estoque baixo no painel"),
    ("recebe_comissao", "Recebe comissão (mecânico)"),
]

PERMISSOES_CODIGOS: frozenset[str] = frozenset(c for c, _ in PERMISSOES_CATALOGO)
TODAS_PERMISSOES: list[str] = [c for c, _ in PERMISSOES_CATALOGO]

# Defaults dos 4 papéis de sistema (slug → config)
PAPEIS_PADRAO: dict[str, dict] = {
    "dono": {
        "nome": "Administrador",
        "eh_administrador": True,
        "permissoes": list(TODAS_PERMISSOES),
    },
    "recepcao": {
        "nome": "Recepção",
        "eh_administrador": False,
        "permissoes": [
            "ordens",
            "orcamentos",
            "clientes",
            "veiculos",
            "catalogo",
            "fornecedores",
            "compras",
            "importar",
            "agente",
            "equipe",
            "painel_caixa",
            "painel_ordens_recentes",
            "painel_estoque",
        ],
    },
    "mecanico": {
        "nome": "Mecânico",
        "eh_administrador": False,
        "permissoes": ["ordens", "orcamentos", "equipe", "recebe_comissao"],
    },
    "financeiro": {
        "nome": "Financeiro",
        "eh_administrador": False,
        "permissoes": [
            "ordens",
            "orcamentos",
            "clientes",
            "veiculos",
            "catalogo",
            "fornecedores",
            "compras",
            "financeiro",
            "relatorios",
            "importar",
            "agente",
            "equipe",
            "painel_caixa",
            "painel_ordens_recentes",
            "painel_estoque",
        ],
    },
}


def garantir_papeis_padrao(oficina):
    """Garante os 4 papéis padrão da oficina; retorna dict slug → PapelOficina."""
    from apps.accounts.models import PapelOficina

    resultado = {}
    for slug, cfg in PAPEIS_PADRAO.items():
        papel, created = PapelOficina.objects.get_or_create(
            oficina=oficina,
            slug=slug,
            defaults={
                "nome": cfg["nome"],
                "eh_administrador": cfg["eh_administrador"],
                "permissoes": list(cfg["permissoes"]),
                "ativo": True,
            },
        )
        if not created and papel.eh_administrador:
            if set(papel.permissoes or []) != set(TODAS_PERMISSOES):
                papel.permissoes = list(TODAS_PERMISSOES)
                papel.save(update_fields=["permissoes"])
        resultado[slug] = papel
    return resultado


def slug_papel_unico(oficina, nome: str, base: str | None = None) -> str:
    """Gera slug único na oficina a partir do nome."""
    from apps.accounts.models import PapelOficina

    root = slugify(base or nome) or "papel"
    root = root[:40]
    slug = root
    n = 2
    while PapelOficina.objects.filter(oficina=oficina, slug=slug).exists():
        slug = f"{root}-{n}"
        n += 1
    return slug


def get_papel(user):
    """Retorna o PapelOficina do usuário ativo, ou None."""
    perfil = getattr(user, "perfil", None)
    if not perfil or not perfil.ativo:
        return None
    return getattr(perfil, "papel", None)


def is_administrador(user) -> bool:
    papel = get_papel(user)
    return bool(papel and papel.eh_administrador)


def user_pode(user, codigo: str) -> bool:
    """Verifica se o usuário autenticado tem a permissão."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    papel = get_papel(user)
    if not papel or not papel.ativo:
        return False
    if papel.eh_administrador:
        return True
    return codigo in (papel.permissoes or [])


def requer_permissao(*codigos: str):
    """Decorator: exige autenticação + ao menos uma das permissões."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("accounts:login")
            if not any(user_pode(request.user, c) for c in codigos):
                messages.error(request, "Você não tem permissão para acessar esta área.")
                return redirect("core:dashboard")
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
