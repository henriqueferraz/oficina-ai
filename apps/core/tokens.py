"""Geração de tokens públicos (OS / orçamento)."""

from __future__ import annotations

import secrets


def gerar_token(nbytes: int = 24) -> str:
    """Token URL-safe (~32 chars com nbytes=24)."""
    return secrets.token_urlsafe(nbytes)
