"""Entrada unificada de mensagem (texto e/ou áudio) para o agente."""

from __future__ import annotations

import logging
from typing import Any

from agents.assistente import chat
from agents.audio import (
    AudioInvalido,
    TranscricaoErro,
    TranscricaoIndisponivel,
    normalizar_mime,
    transcrever_audio,
    validar_audio,
)
from apps.agentes.models import MensagemAgente

logger = logging.getLogger(__name__)

_MSG_FALHA_TRANSCRICAO = (
    "Não consegui entender o áudio. Tente gravar de novo, com menos ruído, "
    "ou envie a mensagem em texto."
)
_MSG_AUDIO_INVALIDO_PREFIXO = "Não foi possível usar o áudio: "


def processar_entrada_usuario(
    conversa,
    *,
    texto: str = "",
    audio=None,
    mime: str | None = None,
    metadados_extra: dict[str, Any] | None = None,
) -> str:
    """
    Processa texto e/ou áudio do usuário.
    Com áudio: valida, transcreve, persiste arquivo e segue o fluxo do chat().
    Retorna a resposta do assistente.
    """
    texto = (texto or "").strip()
    meta: dict[str, Any] = dict(metadados_extra or {})

    if audio is None:
        if not texto:
            return ""
        return chat(conversa, texto, metadados=meta or None)

    mime_n = normalizar_mime(mime or getattr(audio, "content_type", "") or "")
    try:
        validar_audio(audio, mime=mime_n or None)
    except AudioInvalido as exc:
        resposta = f"{_MSG_AUDIO_INVALIDO_PREFIXO}{exc}"
        MensagemAgente.objects.create(
            conversa=conversa,
            papel=MensagemAgente.Papel.ASSISTANT,
            conteudo=resposta,
            metadados={"tipo": "audio_erro", "erro": str(exc)},
        )
        conversa.save(update_fields=["atualizado_em"])
        return resposta

    try:
        transcricao = transcrever_audio(audio, mime=mime_n or None)
    except (TranscricaoIndisponivel, TranscricaoErro) as exc:
        logger.info("Transcrição falhou: %s", exc)
        if hasattr(audio, "seek"):
            try:
                audio.seek(0)
            except Exception:
                pass
        conteudo_user = texto or "[Áudio — falha na transcrição]"
        meta.update(
            {
                "tipo": "audio",
                "transcricao_ok": False,
                "erro": str(exc),
                "mime": mime_n,
            }
        )
        if texto:
            meta["texto_extra"] = texto
        chat_msg = MensagemAgente(
            conversa=conversa,
            papel=MensagemAgente.Papel.USER,
            conteudo=conteudo_user,
            metadados=meta,
        )
        chat_msg.audio = audio
        chat_msg.save()
        resposta = _MSG_FALHA_TRANSCRICAO
        if isinstance(exc, TranscricaoIndisponivel):
            resposta = (
                "Recebi o áudio, mas a transcrição não está configurada "
                "(defina OPENAI_API_KEY). Envie em texto por enquanto."
            )
        MensagemAgente.objects.create(
            conversa=conversa,
            papel=MensagemAgente.Papel.ASSISTANT,
            conteudo=resposta,
        )
        conversa.save(update_fields=["atualizado_em"])
        return resposta

    if hasattr(audio, "seek"):
        try:
            audio.seek(0)
        except Exception:
            pass

    if not transcricao:
        conteudo = texto or "(Áudio sem fala detectável.)"
        meta.update({"tipo": "audio", "transcricao_ok": True, "vazio": True, "mime": mime_n})
        return chat(conversa, conteudo, audio=audio, metadados=meta)

    if texto and texto != transcricao:
        conteudo = f"{texto}\n\n[Áudio]: {transcricao}"
        meta["texto_extra"] = texto
    else:
        conteudo = transcricao

    meta.update({"tipo": "audio", "transcricao_ok": True, "mime": mime_n})
    return chat(conversa, conteudo, audio=audio, metadados=meta)
