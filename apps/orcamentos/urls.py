from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.permissions import requer_permissao
from apps.core.imagens import processar_foto_upload
from apps.core.pdf import gerar_pdf_orcamento
from apps.core.views import get_oficina
from apps.ordens.models import CHECKLIST_PADRAO, ChecklistItem, OrdemItem, OrdemServico

from .models import MAX_FOTOS_ORCAMENTO, Orcamento, OrcamentoFoto, OrcamentoItem

app_name = "orcamentos"


@login_required
@requer_permissao("orcamentos")
def lista(request):
    oficina = get_oficina(request)
    orcamentos = (
        Orcamento.objects.filter(oficina=oficina)
        .select_related("cliente", "veiculo")
        .prefetch_related("itens")
    )
    return render(request, "orcamentos/lista.html", {"orcamentos": orcamentos[:50]})


@login_required
@requer_permissao("orcamentos")
@require_http_methods(["GET", "POST"])
def criar(request):
    from apps.core.models import Cliente, Veiculo

    oficina = get_oficina(request)
    if request.method == "POST":
        cliente = get_object_or_404(Cliente, pk=request.POST.get("cliente"), oficina=oficina)
        veiculo_id = request.POST.get("veiculo") or None
        veiculo = get_object_or_404(Veiculo, pk=veiculo_id, oficina=oficina) if veiculo_id else None
        ultimo = Orcamento.objects.filter(oficina=oficina).aggregate(n=Max("numero"))["n"] or 0
        orc = Orcamento.objects.create(
            oficina=oficina,
            cliente=cliente,
            veiculo=veiculo,
            numero=ultimo + 1,
            observacoes=request.POST.get("observacoes", "").strip(),
        )
        return redirect("orcamentos:detalhe", pk=orc.pk)

    return render(
        request,
        "orcamentos/form.html",
        {
            "clientes": Cliente.objects.filter(oficina=oficina, ativo=True),
            "veiculos": Veiculo.objects.filter(oficina=oficina).select_related("cliente"),
        },
    )


@login_required
@requer_permissao("orcamentos")
def detalhe(request, pk):
    from apps.core.models import Peca, Servico

    oficina = get_oficina(request)
    orc = get_object_or_404(
        Orcamento.objects.select_related("cliente", "veiculo").prefetch_related("itens", "fotos"),
        pk=pk,
        oficina=oficina,
    )
    return render(
        request,
        "orcamentos/detalhe.html",
        {
            "orcamento": orc,
            "status_choices": Orcamento.Status.choices,
            "servicos": Servico.objects.filter(oficina=oficina, ativo=True),
            "pecas": Peca.objects.filter(oficina=oficina, ativo=True),
            "max_fotos": MAX_FOTOS_ORCAMENTO,
        },
    )


@login_required
@requer_permissao("orcamentos")
@require_POST
def adicionar_item(request, pk):
    from decimal import Decimal, InvalidOperation

    from apps.core.models import Peca, Servico

    oficina = get_oficina(request)
    orc = get_object_or_404(Orcamento, pk=pk, oficina=oficina)
    tipo = request.POST.get("tipo", OrcamentoItem.Tipo.SERVICO)
    servico = None
    peca = None
    descricao = request.POST.get("descricao", "").strip()

    def _dec(value, default="0"):
        try:
            return Decimal(str(value or default).replace(",", "."))
        except (InvalidOperation, TypeError):
            return Decimal(default)

    valor = _dec(request.POST.get("valor_unitario"))
    quantidade = _dec(request.POST.get("quantidade"), "1")

    if tipo == OrcamentoItem.Tipo.SERVICO and request.POST.get("servico_id"):
        servico = get_object_or_404(Servico, pk=request.POST.get("servico_id"), oficina=oficina)
        descricao = descricao or servico.nome
        if not request.POST.get("valor_unitario"):
            valor = servico.preco
    elif tipo == OrcamentoItem.Tipo.PECA and request.POST.get("peca_id"):
        peca = get_object_or_404(Peca, pk=request.POST.get("peca_id"), oficina=oficina)
        descricao = descricao or peca.nome
        if not request.POST.get("valor_unitario"):
            valor = peca.preco

    OrcamentoItem.objects.create(
        orcamento=orc,
        tipo=tipo,
        descricao=descricao,
        quantidade=quantidade,
        valor_unitario=valor,
        servico=servico,
        peca=peca,
    )
    if request.htmx:
        orc.refresh_from_db()
        return render(request, "orcamentos/partials/itens.html", {"orcamento": orc})
    return redirect("orcamentos:detalhe", pk=pk)


@login_required
@requer_permissao("orcamentos")
@require_POST
def atualizar_status(request, pk):
    oficina = get_oficina(request)
    orc = get_object_or_404(Orcamento, pk=pk, oficina=oficina)
    status = request.POST.get("status")
    if status in Orcamento.Status.values:
        orc.status = status
        orc.save(update_fields=["status", "atualizado_em"])
    return redirect("orcamentos:detalhe", pk=pk)


@login_required
@requer_permissao("orcamentos")
@require_POST
def foto_upload(request, pk):
    oficina = get_oficina(request)
    orc = get_object_or_404(Orcamento, pk=pk, oficina=oficina)
    arquivos = request.FILES.getlist("imagens") or []
    unico = request.FILES.get("imagem")
    if unico and not arquivos:
        arquivos = [unico]

    if not arquivos:
        messages.error(request, "Selecione ao menos uma foto.")
        return redirect("orcamentos:detalhe", pk=pk)

    restantes = orc.fotos_restantes
    if restantes <= 0:
        messages.error(request, f"Limite de {MAX_FOTOS_ORCAMENTO} fotos atingido.")
        return redirect("orcamentos:detalhe", pk=pk)

    legenda = request.POST.get("legenda", "").strip()
    salvas = 0
    for arquivo in arquivos[:restantes]:
        processada, erro = processar_foto_upload(arquivo)
        if erro or processada is None:
            messages.warning(request, erro or f"Falha ao processar: {arquivo.name}")
            continue
        OrcamentoFoto.objects.create(orcamento=orc, imagem=processada, legenda=legenda)
        salvas += 1

    if salvas:
        messages.success(request, f"{salvas} foto(s) enviada(s).")
    if len(arquivos) > restantes:
        messages.warning(
            request,
            f"Apenas {restantes} foto(s) couberam no limite de {MAX_FOTOS_ORCAMENTO}.",
        )
    return redirect("orcamentos:detalhe", pk=pk)


@login_required
@requer_permissao("orcamentos")
@require_POST
def foto_delete(request, pk, foto_pk):
    oficina = get_oficina(request)
    orc = get_object_or_404(Orcamento, pk=pk, oficina=oficina)
    foto = get_object_or_404(OrcamentoFoto, pk=foto_pk, orcamento=orc)
    foto.delete()
    messages.success(request, "Foto removida.")
    return redirect("orcamentos:detalhe", pk=pk)


@login_required
@requer_permissao("orcamentos")
@require_POST
def video_salvar(request, pk):
    oficina = get_oficina(request)
    orc = get_object_or_404(Orcamento, pk=pk, oficina=oficina)
    orc.video_url = request.POST.get("video_url", "").strip()
    orc.video_titulo = request.POST.get("video_titulo", "").strip()
    orc.save(update_fields=["video_url", "video_titulo", "atualizado_em"])
    if orc.video_url:
        messages.success(request, "Vídeo salvo.")
    else:
        messages.success(request, "Vídeo removido.")
    return redirect("orcamentos:detalhe", pk=pk)


@login_required
@requer_permissao("orcamentos")
@require_POST
@transaction.atomic
def converter_os(request, pk):
    oficina = get_oficina(request)
    orc = get_object_or_404(
        Orcamento.objects.prefetch_related("itens"),
        pk=pk,
        oficina=oficina,
    )
    if orc.status == Orcamento.Status.CONVERTIDO:
        existente = orc.ordens.first()
        if existente:
            messages.info(request, "Este orçamento já foi convertido.")
            return redirect("ordens:detalhe", pk=existente.pk)

    ultimo = OrdemServico.objects.filter(oficina=oficina).aggregate(n=Max("numero"))["n"] or 0
    ordem = OrdemServico.objects.create(
        oficina=oficina,
        cliente=orc.cliente,
        veiculo=orc.veiculo,
        orcamento=orc,
        numero=ultimo + 1,
        diagnostico=orc.observacoes,
        desconto=orc.desconto,
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
            for item in orc.itens.all()
        ]
    )
    ChecklistItem.objects.bulk_create(
        [
            ChecklistItem(ordem=ordem, momento=ChecklistItem.Momento.ENTRADA, item=nome)
            for nome in CHECKLIST_PADRAO
        ]
    )
    orc.status = Orcamento.Status.CONVERTIDO
    orc.save(update_fields=["status", "atualizado_em"])
    messages.success(request, f"Orçamento convertido na OS #{ordem.numero}.")
    return redirect("ordens:detalhe", pk=ordem.pk)


@login_required
@requer_permissao("orcamentos")
def pdf(request, pk):
    oficina = get_oficina(request)
    orc = get_object_or_404(
        Orcamento.objects.select_related("oficina", "cliente", "veiculo").prefetch_related("itens"),
        pk=pk,
        oficina=oficina,
    )
    return gerar_pdf_orcamento(orc)


urlpatterns = [
    path("", lista, name="lista"),
    path("novo/", criar, name="criar"),
    path("<int:pk>/", detalhe, name="detalhe"),
    path("<int:pk>/itens/", adicionar_item, name="adicionar_item"),
    path("<int:pk>/status/", atualizar_status, name="atualizar_status"),
    path("<int:pk>/fotos/", foto_upload, name="foto_upload"),
    path("<int:pk>/fotos/<int:foto_pk>/remover/", foto_delete, name="foto_delete"),
    path("<int:pk>/video/", video_salvar, name="video_salvar"),
    path("<int:pk>/converter/", converter_os, name="converter_os"),
    path("<int:pk>/pdf/", pdf, name="pdf"),
]
