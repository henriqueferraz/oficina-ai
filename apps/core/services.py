from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.ordens.models import OrdemItem, OrdemServico

from .models import Compra, CompraItem, Peca


@transaction.atomic
def registrar_compra(*, oficina, fornecedor, data, observacoes, itens):
    """Cria compra e entra estoque. itens: list[{peca_id, quantidade, custo_unitario}]."""
    from django.db.models import Max

    ultimo = Compra.objects.filter(oficina=oficina).aggregate(n=Max("numero"))["n"] or 0
    compra = Compra.objects.create(
        oficina=oficina,
        fornecedor=fornecedor,
        numero=ultimo + 1,
        data=data,
        observacoes=observacoes,
    )
    for row in itens:
        peca = Peca.objects.select_for_update().get(pk=row["peca_id"], oficina=oficina)
        qtd = Decimal(str(row["quantidade"]))
        custo = Decimal(str(row["custo_unitario"]))
        CompraItem.objects.create(
            compra=compra,
            peca=peca,
            quantidade=qtd,
            custo_unitario=custo,
        )
        peca.estoque = peca.estoque + qtd
        if custo > 0:
            peca.custo = custo
        peca.save(update_fields=["estoque", "custo", "atualizado_em"])
    return compra


@transaction.atomic
def baixar_estoque_ordem(ordem: OrdemServico) -> int:
    """Debita peças vinculadas à OS. Retorna quantidade de itens debitados."""
    if ordem.estoque_baixado:
        return 0
    if ordem.status not in {
        OrdemServico.Status.ENTREGUE,
        OrdemServico.Status.PRONTA,
    }:
        return 0

    debitados = 0
    itens = OrdemItem.objects.filter(
        ordem=ordem,
        tipo=OrdemItem.Tipo.PECA,
        peca__isnull=False,
    ).select_related("peca")
    for item in itens:
        peca = Peca.objects.select_for_update().get(pk=item.peca_id)
        peca.estoque = max(peca.estoque - item.quantidade, Decimal("0"))
        peca.save(update_fields=["estoque", "atualizado_em"])
        debitados += 1

    ordem.estoque_baixado = True
    if ordem.status == OrdemServico.Status.ENTREGUE and not ordem.entregue_em:
        ordem.entregue_em = timezone.now()
        ordem.save(update_fields=["estoque_baixado", "entregue_em", "atualizado_em"])
    else:
        ordem.save(update_fields=["estoque_baixado", "atualizado_em"])
    return debitados
