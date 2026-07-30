from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.accounts.permissions import requer_permissao
from apps.core.views import get_oficina
from apps.ordens.models import OrdemServico

from .models import Lancamento

app_name = "financeiro"


def _dec(value, default="0"):
    try:
        return Decimal(str(value or default).replace(",", "."))
    except (InvalidOperation, TypeError):
        return Decimal(default)


@login_required
@requer_permissao("financeiro")
def lista(request):
    oficina = get_oficina(request)
    lancamentos = Lancamento.objects.filter(oficina=oficina).select_related("ordem")
    receitas = (
        lancamentos.filter(tipo=Lancamento.Tipo.RECEITA, pago=True).aggregate(s=Sum("valor"))["s"]
        or 0
    )
    despesas = (
        lancamentos.filter(tipo=Lancamento.Tipo.DESPESA, pago=True).aggregate(s=Sum("valor"))["s"]
        or 0
    )
    return render(
        request,
        "financeiro/lista.html",
        {
            "lancamentos": lancamentos[:50],
            "receitas": receitas,
            "despesas": despesas,
            "saldo": receitas - despesas,
        },
    )


@login_required
@requer_permissao("financeiro")
@require_http_methods(["GET", "POST"])
def criar(request):
    oficina = get_oficina(request)
    ordens = (
        OrdemServico.objects.filter(oficina=oficina)
        .exclude(status=OrdemServico.Status.CANCELADA)
        .select_related("cliente")[:100]
    )

    if request.method == "POST":
        ordem = None
        ordem_id = request.POST.get("ordem") or None
        if ordem_id:
            ordem = get_object_or_404(OrdemServico, pk=ordem_id, oficina=oficina)
        Lancamento.objects.create(
            oficina=oficina,
            ordem=ordem,
            tipo=request.POST.get("tipo"),
            descricao=request.POST.get("descricao", "").strip(),
            valor=_dec(request.POST.get("valor")),
            forma=request.POST.get("forma") or Lancamento.Forma.PIX,
            data=request.POST.get("data") or timezone.localdate(),
            pago=request.POST.get("pago") == "on",
        )
        return redirect("financeiro:lista")
    return render(
        request,
        "financeiro/form.html",
        {
            "tipos": Lancamento.Tipo.choices,
            "formas": Lancamento.Forma.choices,
            "hoje": timezone.localdate(),
            "ordens": ordens,
            "ordem_preselecionada": request.GET.get("ordem"),
        },
    )


urlpatterns = [
    path("", lista, name="lista"),
    path("novo/", criar, name="criar"),
]
