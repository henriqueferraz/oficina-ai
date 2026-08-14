"""Cliente WhatsApp Cloud API (Meta) com dry-run para testes/dev."""

from __future__ import annotations

import logging
import re
from typing import Any

from django.conf import settings
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

# Outbox em memória para testes / dry-run (não persiste entre workers)
OUTBOX: list[dict[str, Any]] = []


def normalizar_telefone(telefone: str) -> str:
    return re.sub(r"\D+", "", telefone or "")


def whatsapp_configurado() -> bool:
    return bool(
        getattr(settings, "WHATSAPP_ACCESS_TOKEN", "")
        and getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "")
    )


def enviar_whatsapp(*, telefone: str, texto: str, oficina=None) -> bool:
    """
    Envia mensagem WhatsApp. Sem credenciais, registra em OUTBOX (dry-run) e retorna True
    se o telefone for válido — suficiente para testes e dev local.
    """
    digits = normalizar_telefone(telefone)
    if not digits or not (texto or "").strip():
        return False

    payload = {
        "telefone": digits,
        "texto": texto,
        "oficina_id": getattr(oficina, "id", None),
    }

    if not whatsapp_configurado() or getattr(settings, "WHATSAPP_DRY_RUN", True):
        OUTBOX.append(payload)
        logger.info("WhatsApp dry-run → %s", digits)
        return True

    try:
        import httpx

        url = f"https://graph.facebook.com/v21.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }
        body = {
            "messaging_product": "whatsapp",
            "to": digits,
            "type": "text",
            "text": {"body": texto[:4096]},
        }
        resp = httpx.post(url, headers=headers, json=body, timeout=20)
        resp.raise_for_status()
        OUTBOX.append({**payload, "api_ok": True})
        return True
    except Exception:
        logger.exception("Falha ao enviar WhatsApp para %s", digits)
        return False


def extrair_mensagens_webhook(payload: dict) -> list[dict[str, Any]]:
    """Extrai mensagens de texto e áudio do payload Cloud API."""
    mensagens: list[dict[str, Any]] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for msg in value.get("messages") or []:
                remetente = msg.get("from") or ""
                if not remetente:
                    continue
                tipo = msg.get("type")
                base = {"from": remetente, "id": msg.get("id") or "", "type": tipo or ""}
                if tipo == "text":
                    texto = (msg.get("text") or {}).get("body") or ""
                    if texto:
                        mensagens.append({**base, "text": texto})
                elif tipo == "audio":
                    audio = msg.get("audio") or {}
                    media_id = audio.get("id") or ""
                    if media_id:
                        mensagens.append(
                            {
                                **base,
                                "text": "",
                                "media_id": media_id,
                                "mime": (audio.get("mime_type") or "audio/ogg"),
                                "voice": bool(audio.get("voice")),
                            }
                        )
    return mensagens


def baixar_midia_whatsapp(media_id: str) -> tuple[bytes, str]:
    """
    Baixa mídia da Graph API. Retorna (bytes, mime).
    Em dry-run sem token, levanta RuntimeError (testes devem mockar).
    """
    if not media_id:
        raise RuntimeError("media_id vazio")
    token = getattr(settings, "WHATSAPP_ACCESS_TOKEN", "") or ""
    if not token:
        raise RuntimeError("WHATSAPP_ACCESS_TOKEN não configurado para baixar mídia")

    import httpx

    headers = {"Authorization": f"Bearer {token}"}
    meta_url = f"https://graph.facebook.com/v21.0/{media_id}"
    meta_resp = httpx.get(meta_url, headers=headers, timeout=20)
    meta_resp.raise_for_status()
    data = meta_resp.json()
    download_url = data.get("url") or ""
    mime = (data.get("mime_type") or "audio/ogg").split(";")[0].strip()
    if not download_url:
        raise RuntimeError("URL de mídia ausente na Graph API")

    bin_resp = httpx.get(download_url, headers=headers, timeout=60)
    bin_resp.raise_for_status()
    return bin_resp.content, mime


def resolver_oficina_e_cliente(telefone: str):
    """Localiza cliente pelo telefone; devolve (oficina, cliente) ou (None, None)."""
    from apps.core.models import Cliente

    digits = normalizar_telefone(telefone)
    if not digits:
        return None, None

    for cliente in Cliente.objects.filter(ativo=True).select_related("oficina"):
        if normalizar_telefone(cliente.telefone) == digits or normalizar_telefone(
            cliente.telefone
        ).endswith(digits[-9:]):
            return cliente.oficina, cliente

    # Fallback: oficina default via settings
    oficina_id = getattr(settings, "WHATSAPP_DEFAULT_OFICINA_ID", None) or ""
    if oficina_id:
        from apps.core.models import Oficina

        try:
            return Oficina.objects.get(pk=int(oficina_id)), None
        except (Oficina.DoesNotExist, ValueError, TypeError):
            pass
    return None, None


def _obter_ou_criar_conversa(*, telefone: str, oficina, cliente):
    from apps.agentes.models import ConversaAgente

    digits = normalizar_telefone(telefone)
    conversa = (
        ConversaAgente.objects.filter(
            oficina=oficina,
            canal=ConversaAgente.Canal.WHATSAPP,
            telefone_externo=digits,
            ativa=True,
        )
        .order_by("-atualizado_em")
        .first()
    )
    if not conversa:
        conversa = ConversaAgente.objects.create(
            oficina=oficina,
            cliente=cliente,
            canal=ConversaAgente.Canal.WHATSAPP,
            telefone_externo=digits,
            titulo=f"WhatsApp {digits}",
        )
    elif cliente and not conversa.cliente_id:
        conversa.cliente = cliente
        conversa.save(update_fields=["cliente", "atualizado_em"])
    return conversa, digits


def processar_mensagem_entrada(
    *,
    telefone: str,
    texto: str = "",
    media_id: str = "",
    mime: str = "",
    tipo: str = "text",
    message_id: str = "",
) -> str | None:
    """Cria/reusa conversa WhatsApp e responde via agente. Retorna resposta ou None."""
    from agents.audio import extensao_para_mime
    from agents.entrada import processar_entrada_usuario
    from apps.agentes.models import MensagemAgente

    oficina, cliente = resolver_oficina_e_cliente(telefone)
    if not oficina:
        logger.warning("WhatsApp sem oficina para telefone %s", telefone)
        return None

    conversa, digits = _obter_ou_criar_conversa(telefone=telefone, oficina=oficina, cliente=cliente)

    if message_id and MensagemAgente.objects.filter(whatsapp_message_id=message_id).exists():
        logger.info("Mensagem WhatsApp duplicada ignorada: %s", message_id)
        return None

    if conversa.contexto_expirado():
        conversa.etapa = conversa.Etapa.INICIAL
        conversa.contexto_json = {}
        conversa.veiculo = None
        conversa.orcamento = None
        conversa.expira_em = None
        conversa.save(
            update_fields=[
                "etapa",
                "contexto_json",
                "veiculo",
                "orcamento",
                "expira_em",
                "atualizado_em",
            ]
        )

    audio_file = None
    mime_n = mime
    if tipo == "audio" and media_id:
        try:
            raw, mime_api = baixar_midia_whatsapp(media_id)
            mime_n = mime or mime_api
            ext = extensao_para_mime(mime_n)
            audio_file = ContentFile(raw, name=f"wa_{media_id}.{ext}")
        except Exception as exc:
            logger.warning(
                "Falha ao baixar áudio WhatsApp media_id=%s: %s",
                media_id,
                exc,
            )
            resposta = (
                "Recebi seu áudio, mas não consegui baixá-lo agora. "
                "Pode enviar de novo ou escrever em texto?"
            )
            MensagemAgente.objects.create(
                conversa=conversa,
                papel=MensagemAgente.Papel.USER,
                conteudo="[Áudio — falha no download]",
                metadados={"tipo": "audio", "transcricao_ok": False, "media_id": media_id},
                whatsapp_message_id=message_id or None,
                tipo=MensagemAgente.Tipo.AUDIO,
                status=MensagemAgente.StatusProcessamento.ERRO,
                erro_processamento="Falha ao baixar mídia WhatsApp",
            )
            MensagemAgente.objects.create(
                conversa=conversa,
                papel=MensagemAgente.Papel.ASSISTANT,
                conteudo=resposta,
            )
            conversa.save(update_fields=["atualizado_em"])
            enviar_whatsapp(telefone=digits, texto=resposta, oficina=oficina)
            return resposta

    resposta = processar_entrada_usuario(
        conversa,
        texto=texto,
        audio=audio_file,
        mime=mime_n or None,
        metadados_extra={
            key: value
            for key, value in {
                "whatsapp_media_id": media_id,
                "whatsapp_message_id": message_id,
                "tipo": "audio" if tipo == "audio" else "texto",
            }.items()
            if value
        },
    )
    if resposta:
        enviar_whatsapp(telefone=digits, texto=resposta, oficina=oficina)
    return resposta
