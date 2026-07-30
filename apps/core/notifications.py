"""Notificações ao cliente (e-mail / WhatsApp)."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

logger = logging.getLogger(__name__)


def _absolute_url(path: str) -> str:
    base = getattr(settings, "PUBLIC_BASE_URL", "").rstrip("/")
    if base:
        return f"{base}{path}"
    return path


def notificar_status_ordem(ordem) -> dict:
    """
    Notifica o cliente quando a OS fica pronta ou entregue.
    Retorna dict com canais usados (email, whatsapp).
    """
    from apps.ordens.models import OrdemServico

    if ordem.status not in {OrdemServico.Status.PRONTA, OrdemServico.Status.ENTREGUE}:
        return {"email": False, "whatsapp": False}

    if not ordem.token_publico:
        from apps.core.tokens import gerar_token

        ordem.token_publico = gerar_token()
        ordem.save(update_fields=["token_publico"])

    link = _absolute_url(reverse("portal:os_publica", kwargs={"token": ordem.token_publico}))
    status_label = ordem.get_status_display()
    assunto = f"Sua OS #{ordem.numero} está {status_label.lower()}"
    corpo = (
        f"Olá {ordem.cliente.nome},\n\n"
        f"A ordem de serviço #{ordem.numero} da oficina {ordem.oficina.nome} "
        f"está com status: {status_label}.\n\n"
        f"Acompanhe pelo link: {link}\n\n"
        f"— {ordem.oficina.nome}\n"
    )

    enviou_email = False
    if ordem.cliente.email:
        enviou_email = bool(
            send_mail(
                subject=assunto,
                message=corpo,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[ordem.cliente.email],
                fail_silently=True,
            )
        )

    enviou_wa = False
    if ordem.cliente.telefone:
        from apps.agentes.whatsapp import enviar_whatsapp

        enviou_wa = enviar_whatsapp(
            telefone=ordem.cliente.telefone,
            texto=corpo,
            oficina=ordem.oficina,
        )

    return {"email": enviou_email, "whatsapp": enviou_wa}
