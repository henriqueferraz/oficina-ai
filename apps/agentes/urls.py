from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path
from django.views.decorators.http import require_http_methods

from agents.entrada import processar_entrada_usuario
from apps.accounts.permissions import requer_permissao
from apps.core.views import get_oficina

from .models import ConversaAgente
from .webhook import n8n_delivery_callback, n8n_whatsapp_webhook, whatsapp_webhook

app_name = "agentes"


@login_required
@requer_permissao("agente")
def painel(request):
    oficina = get_oficina(request)
    conversas = ConversaAgente.objects.filter(oficina=oficina, canal=ConversaAgente.Canal.PAINEL)[
        :20
    ]
    return render(request, "agentes/painel.html", {"conversas": conversas})


@login_required
@requer_permissao("agente")
@require_http_methods(["POST"])
def nova_conversa(request):
    oficina = get_oficina(request)
    conversa = ConversaAgente.objects.create(
        oficina=oficina,
        usuario=request.user,
        canal=ConversaAgente.Canal.PAINEL,
        titulo=request.POST.get("titulo", "").strip() or "Nova conversa",
    )
    return redirect("agentes:conversa", pk=conversa.pk)


@login_required
@requer_permissao("agente")
@require_http_methods(["GET", "POST"])
def conversa(request, pk):
    oficina = get_oficina(request)
    conversa_obj = get_object_or_404(ConversaAgente, pk=pk, oficina=oficina)
    if request.method == "POST":
        mensagem = request.POST.get("mensagem", "").strip()
        audio = request.FILES.get("audio")
        if mensagem or audio:
            processar_entrada_usuario(conversa_obj, texto=mensagem, audio=audio)
        if request.htmx:
            return render(
                request,
                "agentes/partials/mensagens.html",
                {"conversa": conversa_obj},
            )
        return redirect("agentes:conversa", pk=pk)
    return render(request, "agentes/conversa.html", {"conversa": conversa_obj})


urlpatterns = [
    path("", painel, name="painel"),
    path("nova/", nova_conversa, name="nova"),
    path("whatsapp/webhook/", whatsapp_webhook, name="whatsapp_webhook"),
    path("whatsapp/n8n/entrada/", n8n_whatsapp_webhook, name="n8n_whatsapp_webhook"),
    path("whatsapp/n8n/entrega/", n8n_delivery_callback, name="n8n_delivery_callback"),
    path("<int:pk>/", conversa, name="conversa"),
]
