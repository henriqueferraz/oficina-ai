"""Validação e normalização de fotos (OS / orçamentos).

Pacote: extensões jpg/jpeg/png/webp → quadrado 1280×1280 (crop central)
→ WebP com fallback JPEG → alvo ≤ 500 KB.
"""

from __future__ import annotations

import uuid
from io import BytesIO
from pathlib import PurePosixPath

from django.core.files.base import ContentFile
from PIL import Image, UnidentifiedImageError

EXTENSOES_PERMITIDAS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
CONTENT_TYPES_PERMITIDOS = frozenset(
    {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
    }
)

DEFAULT_MAX_UPLOAD_BYTES = 8 * 1024 * 1024
DEFAULT_LADO_PX = 1280
DEFAULT_MAX_SAIDA_BYTES = 500 * 1024
DEFAULT_QUALIDADE = 80
QUALIDADE_MINIMA = 35


def _cfg() -> dict:
    try:
        from django.conf import settings

        return {
            "max_upload": getattr(settings, "MAX_FOTO_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES),
            "lado": getattr(settings, "FOTO_LADO_PX", DEFAULT_LADO_PX),
            "max_saida": getattr(settings, "MAX_FOTO_SAIDA_BYTES", DEFAULT_MAX_SAIDA_BYTES),
            "qualidade": getattr(settings, "FOTO_QUALIDADE", DEFAULT_QUALIDADE),
        }
    except Exception:
        return {
            "max_upload": DEFAULT_MAX_UPLOAD_BYTES,
            "lado": DEFAULT_LADO_PX,
            "max_saida": DEFAULT_MAX_SAIDA_BYTES,
            "qualidade": DEFAULT_QUALIDADE,
        }


def _extensao(nome: str) -> str:
    return PurePosixPath(nome or "").suffix.lower()


def _nome_saida(nome_original: str, ext: str) -> str:
    base = PurePosixPath(nome_original or "foto").stem or "foto"
    # evita nomes longos / caracteres estranhos no storage
    base = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in base)[:40] or "foto"
    return f"{base}_{uuid.uuid4().hex[:8]}{ext}"


def _crop_central_quadrado(img: Image.Image) -> Image.Image:
    w, h = img.size
    lado = min(w, h)
    left = (w - lado) // 2
    top = (h - lado) // 2
    return img.crop((left, top, left + lado, top + lado))


def _para_rgb(img: Image.Image) -> Image.Image:
    if img.mode in ("RGB", "L"):
        return img.convert("RGB")
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        fundo = Image.new("RGB", rgba.size, (18, 18, 18))
        fundo.paste(rgba, mask=rgba.split()[-1])
        return fundo
    return img.convert("RGB")


def _para_webp_source(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "RGB"):
        return img
    if img.mode in ("LA", "P"):
        return img.convert("RGBA")
    if img.mode == "L":
        return img.convert("RGB")
    return img.convert("RGBA") if "A" in img.getbands() else img.convert("RGB")


def _salvar_com_qualidade(
    img: Image.Image,
    formato: str,
    qualidade_inicial: int,
    max_bytes: int,
) -> bytes | None:
    qualidade = qualidade_inicial
    melhor: bytes | None = None
    while qualidade >= QUALIDADE_MINIMA:
        buf = BytesIO()
        params: dict = {"format": formato, "optimize": True}
        if formato == "WEBP":
            params["quality"] = qualidade
            params["method"] = 4
        else:
            params["quality"] = qualidade
            params["progressive"] = True
        img.save(buf, **params)
        data = buf.getvalue()
        melhor = data
        if len(data) <= max_bytes:
            return data
        qualidade -= 5
    if melhor is not None and len(melhor) <= max_bytes:
        return melhor
    return melhor if melhor and len(melhor) <= max_bytes else None


def processar_foto_upload(arquivo) -> tuple[ContentFile | None, str | None]:
    """Normaliza a foto. Retorna (ContentFile, None) ou (None, mensagem_erro)."""
    cfg = _cfg()
    nome = getattr(arquivo, "name", "arquivo") or "arquivo"
    ext = _extensao(nome)
    if ext not in EXTENSOES_PERMITIDAS:
        permitidas = ", ".join(sorted(EXTENSOES_PERMITIDAS))
        return None, f"Extensão não permitida ({ext or 'sem extensão'}). Use: {permitidas}"

    content_type = (getattr(arquivo, "content_type", "") or "").lower()
    if content_type and content_type not in CONTENT_TYPES_PERMITIDOS:
        if not content_type.startswith("image/"):
            return None, f"Arquivo ignorado (não é imagem): {nome}"
        # alguns browsers mandam image/x-png etc.; ainda validamos pela extensão + Pillow

    tamanho = getattr(arquivo, "size", None)
    if tamanho is not None and tamanho > cfg["max_upload"]:
        mb = cfg["max_upload"] / (1024 * 1024)
        return None, f"Arquivo muito grande no envio (máx. {mb:.0f} MB): {nome}"

    try:
        pos = arquivo.tell()
    except Exception:
        pos = None

    try:
        data = arquivo.read()
        if not data:
            return None, f"Arquivo vazio: {nome}"
        if len(data) > cfg["max_upload"]:
            mb = cfg["max_upload"] / (1024 * 1024)
            return None, f"Arquivo muito grande no envio (máx. {mb:.0f} MB): {nome}"

        with Image.open(BytesIO(data)) as raw:
            raw.load()
            img = raw.copy()

        img = _crop_central_quadrado(img)
        lado = cfg["lado"]
        img = img.resize((lado, lado), Image.Resampling.LANCZOS)

        saida: bytes | None = None
        ext_saida = ".webp"
        # Preferência WebP; fallback JPEG
        try:
            saida = _salvar_com_qualidade(
                _para_webp_source(img),
                "WEBP",
                cfg["qualidade"],
                cfg["max_saida"],
            )
        except OSError:
            saida = None

        if saida is None:
            try:
                saida = _salvar_com_qualidade(
                    _para_rgb(img),
                    "JPEG",
                    cfg["qualidade"],
                    cfg["max_saida"],
                )
                ext_saida = ".jpg"
            except OSError:
                saida = None

        if saida is None:
            kb = cfg["max_saida"] // 1024
            return None, f"Não foi possível comprimir a imagem para ≤ {kb} KB: {nome}"

        content = ContentFile(saida, name=_nome_saida(nome, ext_saida))
        return content, None
    except UnidentifiedImageError:
        return None, f"Arquivo inválido ou corrompido: {nome}"
    except OSError:
        return None, f"Não foi possível ler a imagem: {nome}"
    finally:
        try:
            if pos is not None:
                arquivo.seek(pos)
            else:
                arquivo.seek(0)
        except Exception:
            pass


def validar_foto_upload(arquivo) -> str | None:
    """Compat: só valida sem processar. Prefira processar_foto_upload."""
    cfg = _cfg()
    nome = getattr(arquivo, "name", "arquivo") or "arquivo"
    ext = _extensao(nome)
    if ext not in EXTENSOES_PERMITIDAS:
        permitidas = ", ".join(sorted(EXTENSOES_PERMITIDAS))
        return f"Extensão não permitida ({ext or 'sem extensão'}). Use: {permitidas}"

    tamanho = getattr(arquivo, "size", None)
    if tamanho is not None and tamanho > cfg["max_upload"]:
        mb = cfg["max_upload"] / (1024 * 1024)
        return f"Arquivo muito grande no envio (máx. {mb:.0f} MB): {nome}"

    try:
        pos = arquivo.tell()
    except Exception:
        pos = None
    try:
        data = arquivo.read()
        if not data:
            return f"Arquivo vazio: {nome}"
        with Image.open(BytesIO(data)) as img:
            img.verify()
    except UnidentifiedImageError:
        return f"Arquivo inválido ou corrompido: {nome}"
    except OSError:
        return f"Não foi possível ler a imagem: {nome}"
    finally:
        try:
            if pos is not None:
                arquivo.seek(pos)
            else:
                arquivo.seek(0)
        except Exception:
            pass
    return None
