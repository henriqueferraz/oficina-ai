"""Serviços transacionais do domínio de orçamentos."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max

from apps.core.models import Oficina
from apps.ordens.models import CHECKLIST_PADRAO, ChecklistItem, OrdemItem, OrdemServico

from .models import Orcamento


@transaction.atomic
def converter_orcamento_em_os(orcamento_id: int) -> OrdemServico:
    """Converte um orçamento em uma única OS, de forma idempotente."""
    orcamento = Orcamento.objects.select_for_update().get(pk=orcamento_id)
    existente = OrdemServico.objects.filter(orcamento=orcamento).first()
    if existente:
        if orcamento.status != Orcamento.Status.CONVERTIDO:
            orcamento.status = Orcamento.Status.CONVERTIDO
            orcamento.save(update_fields=["status", "atualizado_em"])
        return existente

    if orcamento.status != Orcamento.Status.APROVADO:
        raise ValidationError("A conversão em OS exige um orçamento aprovado.")

    Oficina.objects.select_for_update().get(pk=orcamento.oficina_id)
    ultimo = (
        OrdemServico.objects.filter(oficina_id=orcamento.oficina_id).aggregate(
            numero=Max("numero")
        )["numero"]
        or 0
    )
    ordem = OrdemServico.objects.create(
        oficina_id=orcamento.oficina_id,
        cliente=orcamento.cliente,
        veiculo=orcamento.veiculo,
        orcamento=orcamento,
        numero=ultimo + 1,
        diagnostico=orcamento.observacoes,
        desconto=orcamento.desconto,
    )
    OrdemItem.objects.bulk_create(
        [
            OrdemItem(
                ordem=ordem,
                tipo=item.tipo,
                descricao=item.descricao,
                quantidade=item.quantidade,
                valor_unitario=item.valor_unitario,
                total=item.total,
                servico=item.servico,
                peca=item.peca,
            )
            for item in orcamento.itens.all()
        ]
    )
    ChecklistItem.objects.bulk_create(
        [
            ChecklistItem(ordem=ordem, momento=ChecklistItem.Momento.ENTRADA, item=nome)
            for nome in CHECKLIST_PADRAO
        ]
    )
    orcamento.status = Orcamento.Status.CONVERTIDO
    orcamento.save(update_fields=["status", "atualizado_em"])
    return ordem
