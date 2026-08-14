"""Webhook WhatsApp Cloud API (Meta)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.agentes.tasks import processar_mensagem_whatsapp
from apps.agentes.whatsapp import extrair_mensagens_webhook

logger = logging.getLogger(__name__)


def assinatura_valida(request) -> bool:
    """Confere o X-Hub-Signature-256 (HMAC-SHA256 do corpo cru com o App Secret).

    O webhook é público e aciona tools que criam orçamento e mudam status de OS,
    então fora do dry-run a assinatura é obrigatória: sem App Secret configurado
    a requisição é recusada.
    """
    segredo = (getattr(settings, "WHATSAPP_APP_SECRET", "") or "").encode()
    if not segredo:
        if getattr(settings, "WHATSAPP_DRY_RUN", True):
            # Dev/testes: sem credenciais Meta e sem chamadas reais à Graph API
            return True
        logger.error("WHATSAPP_APP_SECRET não configurado — webhook recusado.")
        return False

    recebida = request.headers.get("X-Hub-Signature-256", "")
    if not recebida.startswith("sha256="):
        logger.warning("Webhook WhatsApp sem X-Hub-Signature-256.")
        return False

    esperada = hmac.new(segredo, request.body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(recebida.removeprefix("sha256="), esperada):
        logger.warning("Webhook WhatsApp com assinatura inválida.")
        return False
    return True


@csrf_exempt
@require_http_methods(["GET", "POST"])
def whatsapp_webhook(request):
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge", "")
        verify = getattr(settings, "WHATSAPP_VERIFY_TOKEN", "") or ""
        if mode == "subscribe" and verify and hmac.compare_digest(token or "", verify):
            return HttpResponse(challenge, content_type="text/plain")
        return HttpResponseForbidden("Verify token inválido")

    if not assinatura_valida(request):
        return HttpResponseForbidden("Assinatura inválida")

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    respostas = []
    for msg in extrair_mensagens_webhook(payload):
        try:
            processar_mensagem_whatsapp.delay(
                telefone=msg["from"],
                texto=msg.get("text") or "",
                media_id=msg.get("media_id") or "",
                mime=msg.get("mime") or "",
                tipo=msg.get("type") or "text",
                message_id=msg.get("id") or "",
            )
            respostas.append({"to": msg["from"]})
        except Exception:
            logger.exception("Erro processando mensagem WhatsApp %s", msg.get("id"))

    return JsonResponse({"ok": True, "respostas": len(respostas)})
