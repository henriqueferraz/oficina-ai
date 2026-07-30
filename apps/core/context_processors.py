from pathlib import Path

from django.conf import settings

from apps.accounts.permissions import get_papel, is_administrador, user_pode
from apps.core.views import get_oficina


def _asset_version() -> str:
    """mtime dos assets para cache-bust (CSS/JS)."""
    base = Path(settings.BASE_DIR) / "static"
    mtimes = []
    for rel in ("css/app.css", "js/masks.js"):
        path = base / rel
        try:
            mtimes.append(int(path.stat().st_mtime))
        except OSError:
            continue
    return str(max(mtimes) if mtimes else 1)


def oficina_context(request):
    ctx = {
        "asset_version": _asset_version(),
        "app_version": getattr(settings, "APP_VERSION", "0.0.0"),
    }
    if not request.user.is_authenticated:
        return ctx
    # get_oficina primeiro: carrega perfil+oficina numa query e cacheia no user
    oficina = get_oficina(request)
    papel = get_papel(request.user)
    perfil = getattr(request.user, "perfil", None)
    papel_label = None
    papel_slug = None
    if perfil and papel:
        papel_label = papel.nome
        papel_slug = papel.slug
    admin = is_administrador(request.user)
    ctx.update(
        {
            "oficina_atual": oficina,
            "papel_atual": papel_slug,
            "papel_label": papel_label,
            "pode_ordens": user_pode(request.user, "ordens"),
            "pode_orcamentos": user_pode(request.user, "orcamentos"),
            "pode_clientes": user_pode(request.user, "clientes"),
            "pode_veiculos": user_pode(request.user, "veiculos"),
            "pode_catalogo": user_pode(request.user, "catalogo"),
            "pode_fornecedores": user_pode(request.user, "fornecedores"),
            "pode_compras": user_pode(request.user, "compras"),
            "pode_financeiro": user_pode(request.user, "financeiro"),
            "pode_relatorios": user_pode(request.user, "relatorios"),
            "pode_importar": user_pode(request.user, "importar"),
            "pode_agente": user_pode(request.user, "agente"),
            "pode_equipe": user_pode(request.user, "equipe"),
            "pode_configuracoes": user_pode(request.user, "configuracoes"),
            "pode_gerenciar_equipe": admin,
            "pode_painel_caixa": user_pode(request.user, "painel_caixa"),
            "pode_painel_ordens_recentes": user_pode(request.user, "painel_ordens_recentes"),
            "pode_painel_estoque": user_pode(request.user, "painel_estoque"),
            "eh_administrador": admin,
        }
    )
    return ctx
