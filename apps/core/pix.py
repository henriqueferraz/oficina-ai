"""Geração de payload Pix (BR Code estático) e QR Code."""

from __future__ import annotations

import base64
import io
from decimal import Decimal


def _tlv(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}"


def _crc16(payload: str) -> str:
    crc = 0xFFFF
    for char in payload.encode("utf-8"):
        crc ^= char << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return f"{crc:04X}"


def montar_payload_pix(
    *,
    chave: str,
    nome: str,
    cidade: str,
    valor: Decimal | None = None,
    txid: str = "***",
) -> str:
    """Monta BR Code Pix estático (EMV QRCPS-MPM)."""
    chave = (chave or "").strip()
    if not chave:
        raise ValueError("Chave Pix não configurada")

    nome = (nome or "OFICINA")[:25].upper()
    cidade = (cidade or "SAO PAULO")[:15].upper()
    txid = (txid or "***")[:25]

    merchant_account = _tlv("00", "br.gov.bcb.pix") + _tlv("01", chave)
    additional = _tlv("05", txid)

    parts = [
        _tlv("00", "01"),
        _tlv("26", merchant_account),
        _tlv("52", "0000"),
        _tlv("53", "986"),
    ]
    if valor is not None and valor > 0:
        parts.append(_tlv("54", f"{valor:.2f}"))
    parts.extend(
        [
            _tlv("58", "BR"),
            _tlv("59", nome),
            _tlv("60", cidade),
            _tlv("62", additional),
        ]
    )
    payload = "".join(parts) + "6304"
    return payload + _crc16(payload)


def gerar_qr_png_base64(payload: str, box_size: int = 6) -> str:
    """Retorna data-URI PNG do QR Code."""
    import qrcode

    qr = qrcode.QRCode(version=None, box_size=box_size, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def pix_para_ordem(ordem) -> dict | None:
    """Monta payload + QR para uma OS, se a oficina tiver chave Pix."""
    oficina = ordem.oficina
    chave = getattr(oficina, "pix_chave", "") or ""
    if not chave.strip():
        return None
    nome = (oficina.pix_nome or oficina.nome or "OFICINA").strip()
    cidade = (oficina.cidade or "SAO PAULO").strip()
    try:
        payload = montar_payload_pix(
            chave=chave,
            nome=nome,
            cidade=cidade,
            valor=ordem.total,
            txid=f"OS{ordem.numero}",
        )
    except ValueError:
        return None
    return {
        "payload": payload,
        "qr_data_uri": gerar_qr_png_base64(payload),
        "chave": chave,
        "nome": nome,
        "valor": ordem.total,
    }
