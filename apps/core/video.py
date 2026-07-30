"""Helpers para URL de vídeo (YouTube / Vimeo / link genérico)."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse


def video_embed_url(url: str) -> str:
    """URL de embed para YouTube/Vimeo; vazio se for link genérico."""
    if not url:
        return ""
    url = url.strip()
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower().removeprefix("www.")

    if host in {"youtube.com", "m.youtube.com", "youtube-nocookie.com"}:
        qs = parse_qs(parsed.query)
        vid = qs.get("v", [None])[0]
        if not vid and parsed.path.startswith("/embed/"):
            vid = parsed.path.split("/embed/")[-1].split("/")[0]
        if not vid and parsed.path.startswith("/shorts/"):
            vid = parsed.path.split("/shorts/")[-1].split("/")[0]
        if vid:
            return f"https://www.youtube.com/embed/{vid}"
    if host == "youtu.be":
        vid = parsed.path.strip("/").split("/")[0]
        if vid:
            return f"https://www.youtube.com/embed/{vid}"
    if host in {"vimeo.com", "player.vimeo.com"}:
        match = re.search(r"/(\d+)", parsed.path)
        if match:
            return f"https://player.vimeo.com/video/{match.group(1)}"
    return ""
