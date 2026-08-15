"""Webhooks de transporte do WhatsApp."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from base64 import b64decode
from binascii import Error as Base64Error
from datetime import UTC, datetime

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.agentes.tasks import processar_mensagem_n8n, processar_mensagem_whatsapp
from apps.agentes.whatsapp import extrair_mensagens_webhook

logger = logging.getLogger(__name__)


def assinatura_n8n_valida(request) -> bool:
    """Valida HMAC e expiração do evento normalizado enviado pelo n8n."""
    segredo = (getattr(settings, "N8N_INBOUND_SECRET", "") or "").encode()
    timestamp = request.headers.get("X-N8N-Timestamp", "")
    assinatura = request.headers.get("X-N8N-Signature", "")
    if not segredo or not timestamp or not assinatura.startswith("sha256="):
        return False

    try:
        enviado_em = datetime.fromtimestamp(int(timestamp), tz=UTC)
    except ValueError:
        return False

    idade = abs((datetime.now(UTC) - enviado_em).total_seconds())
    if idade > settings.N8N_WEBHOOK_MAX_AGE_SECONDS:
        return False

    corpo_assinado = timestamp.encode() + b"." + request.body
    esperada = hmac.new(segredo, corpo_assinado, hashlib.sha256).hexdigest()
    return hmac.compare_digest(assinatura.removeprefix("sha256="), esperada)


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


@csrf_exempt
@require_http_methods(["POST"])
def n8n_whatsapp_webhook(request):
    """Recebe texto ou mídia normalizada pelo workflow n8n."""
    if not assinatura_n8n_valida(request):
        return HttpResponseForbidden("Assinatura n8n inválida")

    try:
        evento = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    campos = ("evento_id", "mensagem_id_provedor", "telefone", "tipo")
    if any(not isinstance(evento.get(campo), str) or not evento[campo].strip() for campo in campos):
        return JsonResponse({"erro": "Evento n8n inválido"}, status=400)

    tipo = evento["tipo"].strip().lower()
    if tipo not in {"text", "audio", "image", "file"}:
        return JsonResponse({"erro": "Tipo de mídia inválido"}, status=400)
    if tipo == "text" and not isinstance(evento.get("texto", ""), str):
        return JsonResponse({"erro": "Texto inválido"}, status=400)
    media_base64 = evento.get("midia_base64", "")
    if media_base64 and not isinstance(media_base64, str):
        return JsonResponse({"erro": "Mídia inválida"}, status=400)
    if media_base64:
        try:
            media_size = len(b64decode(media_base64, validate=True))
        except Base64Error:
            return JsonResponse({"erro": "Mídia inválida"}, status=400)
        if media_size > settings.N8N_MAX_MEDIA_BYTES:
            return JsonResponse({"erro": "Mídia excede o limite"}, status=413)

    processar_mensagem_n8n.delay(
        telefone=evento["telefone"],
        texto=evento.get("texto", ""),
        mime=evento.get("mime", ""),
        tipo=tipo,
        message_id=evento["mensagem_id_provedor"],
        evento_id=evento["evento_id"],
        instancia=evento.get("instancia", ""),
        media_base64=media_base64,
    )
    return JsonResponse({"ok": True, "evento_id": evento["evento_id"]}, status=202)


@csrf_exempt
@require_http_methods(["POST"])
def n8n_delivery_callback(request):
    """Aceita callbacks de entrega do n8n sem expor dados do provedor."""
    if not assinatura_n8n_valida(request):
        return HttpResponseForbidden("Assinatura n8n inválida")
    try:
        evento = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    if not isinstance(evento.get("mensagem_id_provedor"), str) or not isinstance(
        evento.get("status"), str
    ):
        return JsonResponse({"erro": "Callback n8n inválido"}, status=400)
    logger.info("Callback n8n recebido para mensagem %s", evento["mensagem_id_provedor"])
    return JsonResponse({"ok": True})
