from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.permissions import requer_permissao
from apps.core.imagens import processar_foto_upload
from apps.core.pdf import gerar_pdf_ordem, gerar_pdf_recibo
from apps.core.pix import pix_para_ordem
from apps.core.services import baixar_estoque_ordem
from apps.core.views import get_oficina

from .models import (
    CHECKLIST_PADRAO,
    MAX_FOTOS_ORDEM,
    ChecklistItem,
    OrdemFoto,
    OrdemItem,
    OrdemServico,
)

app_name = "ordens"


@login_required
@requer_permissao("ordens")
def lista(request):
    oficina = get_oficina(request)
    status = request.GET.get("status", "")
    ordens = OrdemServico.objects.filter(oficina=oficina).select_related("cliente", "veiculo")
    if status:
        ordens = ordens.filter(status=status)
    return render(
        request,
        "ordens/lista.html",
        {
            "ordens": ordens[:50],
            "status_atual": status,
            "status_choices": OrdemServico.Status.choices,
        },
    )


@login_required
@requer_permissao("ordens")
@require_http_methods(["GET", "POST"])
def criar(request):
    from apps.core.models import Cliente, Veiculo

    oficina = get_oficina(request)
    if request.method == "POST":
        cliente = get_object_or_404(Cliente, pk=request.POST.get("cliente"), oficina=oficina)
        veiculo_id = request.POST.get("veiculo") or None
        veiculo = get_object_or_404(Veiculo, pk=veiculo_id, oficina=oficina) if veiculo_id else None
        ultimo = OrdemServico.objects.filter(oficina=oficina).aggregate(n=Max("numero"))["n"] or 0
        responsavel_id = request.POST.get("responsavel") or None
        ordem = OrdemServico.objects.create(
            oficina=oficina,
            cliente=cliente,
            veiculo=veiculo,
            numero=ultimo + 1,
            prioridade=request.POST.get("prioridade") or OrdemServico.Prioridade.NORMAL,
            diagnostico=request.POST.get("diagnostico", "").strip(),
            observacoes=request.POST.get("observacoes", "").strip(),
            responsavel_id=responsavel_id,
        )
        ChecklistItem.objects.bulk_create(
            [
                ChecklistItem(
                    ordem=ordem,
                    momento=ChecklistItem.Momento.ENTRADA,
                    item=nome,
                )
                for nome in CHECKLIST_PADRAO
            ]
        )
        return redirect("ordens:detalhe", pk=ordem.pk)

    mecanicos = oficina.usuarios.filter(ativo=True).select_related("user")
    return render(
        request,
        "ordens/form.html",
        {
            "clientes": Cliente.objects.filter(oficina=oficina, ativo=True),
            "veiculos": Veiculo.objects.filter(oficina=oficina).select_related("cliente"),
            "prioridades": OrdemServico.Prioridade.choices,
            "mecanicos": mecanicos,
        },
    )


@login_required
@requer_permissao("ordens")
def detalhe(request, pk):
    from apps.core.models import Peca, Servico

    oficina = get_oficina(request)
    ordem = get_object_or_404(
        OrdemServico.objects.select_related(
            "cliente", "veiculo", "orcamento", "responsavel"
        ).prefetch_related("itens", "checklist", "fotos"),
        pk=pk,
        oficina=oficina,
    )
    mecanicos = oficina.usuarios.filter(ativo=True).select_related("user")
    return render(
        request,
        "ordens/detalhe.html",
        {
            "ordem": ordem,
            "status_choices": OrdemServico.Status.choices,
            "servicos": Servico.objects.filter(oficina=oficina, ativo=True),
            "pecas": Peca.objects.filter(oficina=oficina, ativo=True),
            "checklist_entrada": ordem.checklist.filter(momento=ChecklistItem.Momento.ENTRADA),
            "checklist_saida": ordem.checklist.filter(momento=ChecklistItem.Momento.SAIDA),
            "pix": pix_para_ordem(ordem),
            "mecanicos": mecanicos,
            "max_fotos": MAX_FOTOS_ORDEM,
        },
    )


@login_required
@requer_permissao("ordens")
@require_POST
def atualizar_status(request, pk):
    from apps.core.notifications import notificar_status_ordem

    oficina = get_oficina(request)
    ordem = get_object_or_404(OrdemServico, pk=pk, oficina=oficina)
    status = request.POST.get("status")
    if status in OrdemServico.Status.values:
        ordem.status = status
        ordem.save(update_fields=["status", "atualizado_em"])
        if status in {OrdemServico.Status.PRONTA, OrdemServico.Status.ENTREGUE}:
            baixar_estoque_ordem(ordem)
            ordem.refresh_from_db()
            notificar_status_ordem(ordem)
    if request.htmx:
        return render(
            request,
            "ordens/partials/status_badge.html",
            {"ordem": ordem, "status_choices": OrdemServico.Status.choices},
        )
    return redirect("ordens:detalhe", pk=pk)


@login_required
@requer_permissao("ordens")
@require_POST
def atualizar_responsavel(request, pk):
    oficina = get_oficina(request)
    ordem = get_object_or_404(OrdemServico, pk=pk, oficina=oficina)
    responsavel_id = request.POST.get("responsavel") or None
    if responsavel_id:
        get_object_or_404(oficina.usuarios, user_id=responsavel_id, ativo=True)
        ordem.responsavel_id = responsavel_id
    else:
        ordem.responsavel = None
    ordem.save(update_fields=["responsavel", "atualizado_em"])
    return redirect("ordens:detalhe", pk=pk)


@login_required
@requer_permissao("ordens")
@require_POST
def adicionar_item(request, pk):
    from decimal import Decimal, InvalidOperation

    from apps.core.models import Peca, Servico

    oficina = get_oficina(request)
    ordem = get_object_or_404(OrdemServico, pk=pk, oficina=oficina)
    tipo = request.POST.get("tipo", OrdemItem.Tipo.SERVICO)
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

    if tipo == OrdemItem.Tipo.SERVICO and request.POST.get("servico_id"):
        servico = get_object_or_404(Servico, pk=request.POST.get("servico_id"), oficina=oficina)
        descricao = descricao or servico.nome
        if not request.POST.get("valor_unitario"):
            valor = servico.preco
    elif tipo == OrdemItem.Tipo.PECA and request.POST.get("peca_id"):
        peca = get_object_or_404(Peca, pk=request.POST.get("peca_id"), oficina=oficina)
        descricao = descricao or peca.nome
        if not request.POST.get("valor_unitario"):
            valor = peca.preco

    OrdemItem.objects.create(
        ordem=ordem,
        tipo=tipo,
        descricao=descricao,
        quantidade=quantidade,
        valor_unitario=valor,
        servico=servico,
        peca=peca,
    )
    if request.htmx:
        ordem.refresh_from_db()
        return render(request, "ordens/partials/itens.html", {"ordem": ordem})
    return redirect("ordens:detalhe", pk=pk)


@login_required
@requer_permissao("ordens")
@require_POST
def checklist_add(request, pk):
    oficina = get_oficina(request)
    ordem = get_object_or_404(OrdemServico, pk=pk, oficina=oficina)
    item = request.POST.get("item", "").strip()
    momento = request.POST.get("momento") or ChecklistItem.Momento.ENTRADA
    if item and momento in ChecklistItem.Momento.values:
        ChecklistItem.objects.create(ordem=ordem, momento=momento, item=item)
    return redirect("ordens:detalhe", pk=pk)


@login_required
@requer_permissao("ordens")
@require_POST
def checklist_toggle(request, pk, item_pk):
    oficina = get_oficina(request)
    ordem = get_object_or_404(OrdemServico, pk=pk, oficina=oficina)
    item = get_object_or_404(ChecklistItem, pk=item_pk, ordem=ordem)
    item.ok = not item.ok
    item.observacao = request.POST.get("observacao", item.observacao).strip()
    item.save(update_fields=["ok", "observacao"])
    return redirect("ordens:detalhe", pk=pk)


@login_required
@requer_permissao("ordens")
@require_POST
def foto_upload(request, pk):
    oficina = get_oficina(request)
    ordem = get_object_or_404(OrdemServico, pk=pk, oficina=oficina)
    arquivos = request.FILES.getlist("imagens") or []
    unico = request.FILES.get("imagem")
    if unico and not arquivos:
        arquivos = [unico]

    if not arquivos:
        messages.error(request, "Selecione ao menos uma foto.")
        return redirect("ordens:detalhe", pk=pk)

    restantes = ordem.fotos_restantes
    if restantes <= 0:
        messages.error(request, f"Limite de {MAX_FOTOS_ORDEM} fotos atingido.")
        return redirect("ordens:detalhe", pk=pk)

    legenda = request.POST.get("legenda", "").strip()
    salvas = 0
    for arquivo in arquivos[:restantes]:
        processada, erro = processar_foto_upload(arquivo)
        if erro or processada is None:
            messages.warning(request, erro or f"Falha ao processar: {arquivo.name}")
            continue
        OrdemFoto.objects.create(ordem=ordem, imagem=processada, legenda=legenda)
        salvas += 1

    if salvas:
        messages.success(request, f"{salvas} foto(s) enviada(s).")
    if len(arquivos) > restantes:
        messages.warning(
            request,
            f"Apenas {restantes} foto(s) couberam no limite de {MAX_FOTOS_ORDEM}.",
        )
    return redirect("ordens:detalhe", pk=pk)


@login_required
@requer_permissao("ordens")
@require_POST
def foto_delete(request, pk, foto_pk):
    oficina = get_oficina(request)
    ordem = get_object_or_404(OrdemServico, pk=pk, oficina=oficina)
    foto = get_object_or_404(OrdemFoto, pk=foto_pk, ordem=ordem)
    foto.delete()
    messages.success(request, "Foto removida.")
    return redirect("ordens:detalhe", pk=pk)


@login_required
@requer_permissao("ordens")
@require_POST
def video_salvar(request, pk):
    oficina = get_oficina(request)
    ordem = get_object_or_404(OrdemServico, pk=pk, oficina=oficina)
    ordem.video_url = request.POST.get("video_url", "").strip()
    ordem.video_titulo = request.POST.get("video_titulo", "").strip()
    ordem.save(update_fields=["video_url", "video_titulo", "atualizado_em"])
    if ordem.video_url:
        messages.success(request, "Vídeo salvo.")
    else:
        messages.success(request, "Vídeo removido.")
    return redirect("ordens:detalhe", pk=pk)


@login_required
@requer_permissao("ordens")
def pdf(request, pk):
    oficina = get_oficina(request)
    ordem = get_object_or_404(
        OrdemServico.objects.select_related("oficina", "cliente", "veiculo").prefetch_related(
            "itens"
        ),
        pk=pk,
        oficina=oficina,
    )
    return gerar_pdf_ordem(ordem)


@login_required
@requer_permissao("ordens")
def recibo(request, pk):
    oficina = get_oficina(request)
    ordem = get_object_or_404(
        OrdemServico.objects.select_related("oficina", "cliente", "veiculo").prefetch_related(
            "itens"
        ),
        pk=pk,
        oficina=oficina,
    )
    return gerar_pdf_recibo(ordem)


urlpatterns = [
    path("", lista, name="lista"),
    path("nova/", criar, name="criar"),
    path("<int:pk>/", detalhe, name="detalhe"),
    path("<int:pk>/status/", atualizar_status, name="atualizar_status"),
    path("<int:pk>/responsavel/", atualizar_responsavel, name="atualizar_responsavel"),
    path("<int:pk>/itens/", adicionar_item, name="adicionar_item"),
    path("<int:pk>/checklist/", checklist_add, name="checklist_add"),
    path("<int:pk>/checklist/<int:item_pk>/toggle/", checklist_toggle, name="checklist_toggle"),
    path("<int:pk>/fotos/", foto_upload, name="foto_upload"),
    path("<int:pk>/fotos/<int:foto_pk>/remover/", foto_delete, name="foto_delete"),
    path("<int:pk>/video/", video_salvar, name="video_salvar"),
    path("<int:pk>/pdf/", pdf, name="pdf"),
    path("<int:pk>/recibo/", recibo, name="recibo"),
]
