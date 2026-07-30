"""Transcrição de áudio para os agentes (OpenAI Whisper)."""

from __future__ import annotations

import logging
from typing import BinaryIO

from django.conf import settings

logger = logging.getLogger(__name__)

AUDIO_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
AUDIO_MIME_PERMITIDOS = frozenset(
    {
        "audio/mpeg",
        "audio/mp3",
        "audio/mp4",
        "audio/m4a",
        "audio/x-m4a",
        "audio/wav",
        "audio/x-wav",
        "audio/webm",
        "audio/ogg",
        "audio/opus",
        "audio/aac",
        "application/ogg",
    }
)
_EXT_POR_MIME = {
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "m4a",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/opus": "ogg",
    "audio/aac": "aac",
    "application/ogg": "ogg",
}


class AudioInvalido(ValueError):
    """Arquivo de áudio rejeitado na validação."""


class TranscricaoErro(RuntimeError):
    """Falha ao transcrever áudio."""


class TranscricaoIndisponivel(TranscricaoErro):
    """API de transcrição não configurada."""


def normalizar_mime(content_type: str | None) -> str:
    raw = (content_type or "").split(";")[0].strip().lower()
    if raw == "audio/mp3":
        return "audio/mpeg"
    return raw


def extensao_para_mime(mime: str) -> str:
    return _EXT_POR_MIME.get(normalizar_mime(mime), "ogg")


def validar_audio(arquivo, *, mime: str | None = None) -> None:
    """Valida tamanho e MIME. Levanta AudioInvalido se inválido."""
    if arquivo is None:
        raise AudioInvalido("Nenhum áudio enviado.")
    tamanho = getattr(arquivo, "size", None)
    if tamanho is not None and tamanho <= 0:
        raise AudioInvalido("Áudio vazio.")
    if tamanho is not None and tamanho > AUDIO_MAX_BYTES:
        raise AudioInvalido("Áudio muito grande (máx. 10 MB).")
    mime_n = normalizar_mime(mime or getattr(arquivo, "content_type", "") or "")
    nome = (getattr(arquivo, "name", "") or "").lower()
    if mime_n and mime_n not in AUDIO_MIME_PERMITIDOS:
        # Alguns browsers enviam octet-stream; aceita pela extensão
        if mime_n not in ("application/octet-stream", "") or not any(
            nome.endswith(f".{ext}") for ext in ("ogg", "mp3", "wav", "webm", "m4a", "aac", "opus")
        ):
            raise AudioInvalido(f"Formato de áudio não suportado ({mime_n or 'desconhecido'}).")
    if not mime_n and not any(
        nome.endswith(f".{ext}") for ext in ("ogg", "mp3", "wav", "webm", "m4a", "aac", "opus")
    ):
        raise AudioInvalido("Formato de áudio não suportado.")


def _nome_arquivo_whisper(arquivo, mime: str) -> str:
    nome = getattr(arquivo, "name", "") or ""
    if "." in nome:
        return nome.rsplit("/", 1)[-1]
    return f"audio.{extensao_para_mime(mime)}"


def transcrever_audio(arquivo: BinaryIO, *, mime: str | None = None) -> str:
    """
    Transcreve áudio via OpenAI Whisper.
    O ponteiro do arquivo deve estar no início; a função tenta seek(0) ao final.
    """
    api_key = getattr(settings, "OPENAI_API_KEY", "") or ""
    if not api_key:
        raise TranscricaoIndisponivel("Transcrição indisponível: configure OPENAI_API_KEY.")

    mime_n = normalizar_mime(mime or getattr(arquivo, "content_type", "") or "audio/ogg")
    validar_audio(arquivo, mime=mime_n)

    if hasattr(arquivo, "seek"):
        try:
            arquivo.seek(0)
        except Exception:
            pass

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    model = getattr(settings, "OPENAI_TRANSCRIPTION_MODEL", None) or "whisper-1"
    filename = _nome_arquivo_whisper(arquivo, mime_n)

    try:
        result = client.audio.transcriptions.create(
            model=model,
            file=(filename, arquivo, mime_n or "audio/ogg"),
            language="pt",
        )
    except Exception as exc:
        logger.exception("Falha na transcrição Whisper")
        raise TranscricaoErro("Não foi possível transcrever o áudio.") from exc
    finally:
        if hasattr(arquivo, "seek"):
            try:
                arquivo.seek(0)
            except Exception:
                pass

    texto = (getattr(result, "text", None) or "").strip()
    return texto
