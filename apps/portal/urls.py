from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path
from django.views.decorators.http import require_POST

from apps.orcamentos.models import Orcamento
from apps.ordens.models import OrdemServico

app_name = "portal"


def os_publica(request, token):
    from apps.core.pix import pix_para_ordem

    ordem = get_object_or_404(
        OrdemServico.objects.select_related("cliente", "veiculo", "oficina"),
        token_publico=token,
    )
    return render(
        request,
        "portal/os.html",
        {
            "ordem": ordem,
            "itens": ordem.itens.all(),
            "oficina": ordem.oficina,
            "pix": pix_para_ordem(ordem),
        },
    )


def orcamento_publico(request, token):
    orc = get_object_or_404(
        Orcamento.objects.select_related("cliente", "veiculo", "oficina"),
        token_publico=token,
    )
    return render(
        request,
        "portal/orcamento.html",
        {
            "orcamento": orc,
            "itens": orc.itens.all(),
            "oficina": orc.oficina,
            "pode_decidir": orc.status == Orcamento.Status.ENVIADO,
        },
    )


@require_POST
def orcamento_aprovar(request, token):
    orc = get_object_or_404(Orcamento, token_publico=token)
    if orc.status != Orcamento.Status.ENVIADO:
        messages.error(request, "Este orçamento não está disponível para aprovação.")
        return redirect("portal:orcamento_publico", token=token)
    orc.status = Orcamento.Status.APROVADO
    orc.save(update_fields=["status", "atualizado_em"])
    messages.success(request, "Orçamento aprovado. Obrigado!")
    return redirect("portal:orcamento_publico", token=token)


@require_POST
def orcamento_recusar(request, token):
    orc = get_object_or_404(Orcamento, token_publico=token)
    if orc.status != Orcamento.Status.ENVIADO:
        messages.error(request, "Este orçamento não está disponível para recusa.")
        return redirect("portal:orcamento_publico", token=token)
    orc.status = Orcamento.Status.RECUSADO
    orc.save(update_fields=["status", "atualizado_em"])
    messages.success(request, "Orçamento recusado. Entraremos em contato se necessário.")
    return redirect("portal:orcamento_publico", token=token)


urlpatterns = [
    path("os/<str:token>/", os_publica, name="os_publica"),
    path("orcamento/<str:token>/", orcamento_publico, name="orcamento_publico"),
    path("orcamento/<str:token>/aprovar/", orcamento_aprovar, name="orcamento_aprovar"),
    path("orcamento/<str:token>/recusar/", orcamento_recusar, name="orcamento_recusar"),
]
