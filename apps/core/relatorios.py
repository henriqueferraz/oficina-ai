"""Relatórios operacionais e comissões."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce

from apps.financeiro.models import Lancamento
from apps.orcamentos.models import Orcamento
from apps.ordens.models import OrdemItem, OrdemServico


def ticket_medio(oficina) -> Decimal:
    """Média do total das OS entregues (soma itens − desconto via agregação aproximada)."""
    ordens = list(
        OrdemServico.objects.filter(
            oficina=oficina,
            status=OrdemServico.Status.ENTREGUE,
        ).prefetch_related("itens")
    )
    if not ordens:
        return Decimal("0")
    totais = [o.total for o in ordens]
    return (sum(totais, Decimal("0")) / len(totais)).quantize(Decimal("0.01"))


def pecas_mais_usadas(oficina, limite: int = 10):
    return (
        OrdemItem.objects.filter(
            ordem__oficina=oficina,
            tipo=OrdemItem.Tipo.PECA,
        )
        .exclude(ordem__status=OrdemServico.Status.CANCELADA)
        .values("descricao")
        .annotate(
            quantidade=Coalesce(Sum("quantidade"), Decimal("0")),
            usos=Count("id"),
        )
        .order_by("-quantidade")[:limite]
    )


def conversao_orcamento_os(oficina) -> dict:
    from django.db.models import Count, Q

    agg = Orcamento.objects.filter(oficina=oficina).aggregate(
        total=Count("id"),
        convertidos=Count("id", filter=Q(status=Orcamento.Status.CONVERTIDO)),
        aprovados=Count(
            "id",
            filter=Q(
                status__in=[Orcamento.Status.APROVADO, Orcamento.Status.CONVERTIDO]
            ),
        ),
    )
    total = agg["total"] or 0
    convertidos = agg["convertidos"] or 0
    aprovados = agg["aprovados"] or 0
    taxa = Decimal("0")
    if total:
        taxa = (Decimal(convertidos) / Decimal(total) * 100).quantize(Decimal("0.01"))
    return {
        "total": total,
        "convertidos": convertidos,
        "aprovados": aprovados,
        "taxa_percentual": taxa,
    }


def margem_operacional(
    oficina,
    *,
    receitas: Decimal | None = None,
    despesas: Decimal | None = None,
) -> dict:
    """Margem aproximada: receita paga − custo das peças nas OS entregues − despesas."""
    from django.db.models import F
    from django.db.models import Sum as DjSum
    from django.db.models.functions import Coalesce

    if receitas is None:
        receitas = Lancamento.objects.filter(
            oficina=oficina, tipo=Lancamento.Tipo.RECEITA, pago=True
        ).aggregate(s=Sum("valor"))["s"] or Decimal("0")
    if despesas is None:
        despesas = Lancamento.objects.filter(
            oficina=oficina, tipo=Lancamento.Tipo.DESPESA, pago=True
        ).aggregate(s=Sum("valor"))["s"] or Decimal("0")

    custo_pecas = (
        OrdemItem.objects.filter(
            ordem__oficina=oficina,
            ordem__status=OrdemServico.Status.ENTREGUE,
            tipo=OrdemItem.Tipo.PECA,
            peca__isnull=False,
        ).aggregate(s=Coalesce(DjSum(F("peca__custo") * F("quantidade")), Decimal("0")))[
            "s"
        ]
        or Decimal("0")
    )

    margem = receitas - despesas - custo_pecas
    margem_pct = Decimal("0")
    if receitas:
        margem_pct = (margem / receitas * 100).quantize(Decimal("0.01"))
    return {
        "receitas": receitas,
        "despesas": despesas,
        "custo_pecas": custo_pecas.quantize(Decimal("0.01")),
        "margem": margem.quantize(Decimal("0.01")),
        "margem_percentual": margem_pct,
    }


def comissoes_por_mecanico(oficina) -> list[dict]:
    """Comissão = percentual do mecânico × total das OS entregues sob sua responsabilidade."""
    from apps.accounts.models import PerfilUsuario

    ordens = (
        OrdemServico.objects.filter(
            oficina=oficina,
            status=OrdemServico.Status.ENTREGUE,
            responsavel__isnull=False,
        )
        .select_related("responsavel", "responsavel__perfil")
        .prefetch_related("itens")
    )

    por_user: dict[int, dict] = {}
    for ordem in ordens:
        user = ordem.responsavel
        bucket = por_user.setdefault(
            user.id,
            {
                "user": user,
                "ordens": 0,
                "faturamento": Decimal("0"),
                "comissao": Decimal("0"),
                "percentual": Decimal("0"),
            },
        )
        perfil = getattr(user, "perfil", None)
        if perfil and perfil.oficina_id == oficina.id:
            pct = perfil.percentual_comissao()
        else:
            pct = oficina.comissao_padrao_percentual
        total = ordem.total
        bucket["ordens"] += 1
        bucket["faturamento"] += total
        bucket["comissao"] += (total * pct / Decimal("100")).quantize(Decimal("0.01"))
        bucket["percentual"] = pct

    # Inclui quem recebe comissão sem OS no período (zerados)
    candidatos = PerfilUsuario.objects.filter(
        oficina=oficina,
        ativo=True,
        papel__isnull=False,
    ).select_related("user", "papel")
    for perfil in candidatos:
        papel = perfil.papel
        if not papel or papel.eh_administrador:
            continue
        if not (
            papel.slug == "mecanico" or "recebe_comissao" in (papel.permissoes or [])
        ):
            continue
        if perfil.user_id not in por_user:
            por_user[perfil.user_id] = {
                "user": perfil.user,
                "ordens": 0,
                "faturamento": Decimal("0"),
                "comissao": Decimal("0"),
                "percentual": perfil.percentual_comissao(),
            }

    resultado = sorted(por_user.values(), key=lambda x: x["comissao"], reverse=True)
    return resultado
