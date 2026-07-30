"""Webhook WhatsApp Cloud API (Meta)."""

from __future__ import annotations

import json
import logging

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.agentes.whatsapp import extrair_mensagens_webhook, processar_mensagem_entrada

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def whatsapp_webhook(request):
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge", "")
        verify = getattr(settings, "WHATSAPP_VERIFY_TOKEN", "") or ""
        if mode == "subscribe" and verify and token == verify:
            return HttpResponse(challenge, content_type="text/plain")
        return HttpResponseForbidden("Verify token inválido")

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    respostas = []
    for msg in extrair_mensagens_webhook(payload):
        try:
            resposta = processar_mensagem_entrada(
                telefone=msg["from"],
                texto=msg.get("text") or "",
                media_id=msg.get("media_id") or "",
                mime=msg.get("mime") or "",
                tipo=msg.get("type") or "text",
            )
            if resposta:
                respostas.append({"to": msg["from"], "reply": resposta})
        except Exception:
            logger.exception("Erro processando mensagem WhatsApp %s", msg.get("id"))

    return JsonResponse({"ok": True, "respostas": len(respostas)})
