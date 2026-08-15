"""Tasks periódicas do agente (resumo diário, etc.)."""

from __future__ import annotations

import base64
import binascii

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

from agents.assistente import _tool_resumo
from apps.accounts.models import PerfilUsuario
from apps.core.models import Oficina


@shared_task(name="agentes.processar_mensagem_whatsapp")
def processar_mensagem_whatsapp(
    *,
    telefone: str,
    texto: str = "",
    media_id: str = "",
    mime: str = "",
    tipo: str = "text",
    message_id: str = "",
) -> str | None:
    """Processa uma mensagem WhatsApp fora da requisição do webhook."""
    from apps.agentes.whatsapp import processar_mensagem_entrada

    return processar_mensagem_entrada(
        telefone=telefone,
        texto=texto,
        media_id=media_id,
        mime=mime,
        tipo=tipo,
        message_id=message_id,
    )


@shared_task(name="agentes.processar_mensagem_n8n")
def processar_mensagem_n8n(
    *,
    telefone: str,
    texto: str = "",
    mime: str = "",
    tipo: str = "text",
    message_id: str = "",
    evento_id: str = "",
    instancia: str = "",
    media_base64: str = "",
) -> str | None:
    """Processa evento normalizado pelo n8n sem acessar a Evolution API."""
    from apps.agentes.whatsapp import processar_mensagem_entrada

    media_content = None
    if media_base64:
        try:
            media_content = base64.b64decode(media_base64, validate=True)
        except (binascii.Error, ValueError):
            return None

    return processar_mensagem_entrada(
        telefone=telefone,
        texto=texto,
        mime=mime,
        tipo=tipo,
        message_id=message_id,
        media_content=media_content,
        metadados_origem={
            key: value
            for key, value in {
                "evento_id": evento_id,
                "instancia": instancia,
                "origem": "n8n",
            }.items()
            if value
        },
    )


@shared_task(name="agentes.enviar_resumo_diario")
def enviar_resumo_diario() -> dict:
    """Gera e envia o resumo operacional diário para o dono de cada oficina."""
    enviados = 0
    pulados = 0

    for oficina in Oficina.objects.all().iterator():
        donos = (
            PerfilUsuario.objects.filter(
                oficina=oficina,
                papel__eh_administrador=True,
                ativo=True,
            )
            .select_related("user")
            .exclude(user__email="")
        )
        resumo = _tool_resumo(oficina)
        assunto = f"[Oficina AI] Resumo diário — {oficina.nome}"
        corpo = (
            f"Bom dia!\n\n"
            f"Resumo operacional de {oficina.nome}:\n"
            f"- OS abertas: {resumo['os_abertas']}\n"
            f"- OS prontas: {resumo['os_prontas']}\n"
            f"- Orçamentos enviados: {resumo['orcamentos_enviados']}\n"
            f"- Orçamentos em rascunho: {resumo['orcamentos_rascunho']}\n"
            f"- Clientes ativos: {resumo['clientes_ativos']}\n"
            f"- Veículos cadastrados: {resumo['veiculos']}\n\n"
            f"— Oficina AI\n"
        )

        destinatarios = [p.user.email for p in donos if p.user.email]
        if not destinatarios:
            pulados += 1
            continue

        send_mail(
            subject=assunto,
            message=corpo,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=destinatarios,
            fail_silently=True,
        )
        enviados += 1

    return {"oficinas_enviadas": enviados, "oficinas_puladas": pulados}
