from io import BytesIO

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="TituloDoc",
            parent=styles["Heading1"],
            fontSize=16,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SubDoc",
            parent=styles["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#555555"),
            spaceAfter=12,
        )
    )
    return styles


def _tabela_itens(itens):
    data = [["Tipo", "Descrição", "Qtd", "Unitário", "Total"]]
    for item in itens:
        data.append(
            [
                item.get_tipo_display(),
                item.descricao,
                f"{item.quantidade}",
                f"R$ {item.valor_unitario:.2f}",
                f"R$ {item.total:.2f}",
            ]
        )
    table = Table(data, colWidths=[2.2 * cm, 8 * cm, 2 * cm, 2.8 * cm, 2.8 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2a24")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f7f5")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def pdf_response(filename: str, build_story) -> HttpResponse:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )
    styles = _styles()
    doc.build(build_story(styles))
    pdf = buffer.getvalue()
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


def gerar_pdf_ordem(ordem) -> HttpResponse:
    def story(styles):
        elems = [
            Paragraph(f"Ordem de Serviço #{ordem.numero}", styles["TituloDoc"]),
            Paragraph(ordem.oficina.nome, styles["SubDoc"]),
            Paragraph(f"<b>Cliente:</b> {ordem.cliente.nome}", styles["Normal"]),
        ]
        if ordem.veiculo:
            elems.append(Paragraph(f"<b>Veículo:</b> {ordem.veiculo}", styles["Normal"]))
        elems.append(
            Paragraph(
                f"<b>Status:</b> {ordem.get_status_display()} · "
                f"<b>Prioridade:</b> {ordem.get_prioridade_display()}",
                styles["Normal"],
            )
        )
        if ordem.diagnostico:
            elems.append(Spacer(1, 8))
            elems.append(Paragraph(f"<b>Diagnóstico:</b> {ordem.diagnostico}", styles["Normal"]))
        elems.append(Spacer(1, 14))
        elems.append(_tabela_itens(ordem.itens.all()))
        elems.append(Spacer(1, 12))
        elems.append(Paragraph(f"<b>Total:</b> R$ {ordem.total:.2f}", styles["Heading2"]))
        if ordem.observacoes:
            elems.append(Spacer(1, 8))
            elems.append(Paragraph(f"<b>Observações:</b> {ordem.observacoes}", styles["Normal"]))
        return elems

    return pdf_response(f"os-{ordem.numero}.pdf", story)


def gerar_pdf_recibo(ordem) -> HttpResponse:
    """Recibo / cupom simples — não fiscal (sem NF-e)."""

    def story(styles):
        elems = [
            Paragraph(f"Recibo — OS #{ordem.numero}", styles["TituloDoc"]),
            Paragraph(ordem.oficina.nome, styles["SubDoc"]),
            Paragraph(
                "<b>Documento não fiscal.</b> Este recibo não substitui nota fiscal.",
                styles["SubDoc"],
            ),
            Paragraph(f"<b>Cliente:</b> {ordem.cliente.nome}", styles["Normal"]),
        ]
        if ordem.cliente.documento:
            elems.append(
                Paragraph(f"<b>Documento:</b> {ordem.cliente.documento}", styles["Normal"])
            )
        if ordem.veiculo:
            elems.append(Paragraph(f"<b>Veículo:</b> {ordem.veiculo}", styles["Normal"]))
        elems.append(Spacer(1, 14))
        elems.append(_tabela_itens(ordem.itens.all()))
        elems.append(Spacer(1, 12))
        elems.append(Paragraph(f"<b>Total recebido:</b> R$ {ordem.total:.2f}", styles["Heading2"]))
        elems.append(
            Paragraph(
                f"<b>Pagamento:</b> {ordem.get_pagamento_status_display()}",
                styles["Normal"],
            )
        )
        elems.append(Spacer(1, 24))
        elems.append(
            Paragraph(
                "_________________________________<br/>Assinatura / carimbo",
                styles["Normal"],
            )
        )
        return elems

    return pdf_response(f"recibo-os-{ordem.numero}.pdf", story)


def gerar_pdf_orcamento(orcamento) -> HttpResponse:
    def story(styles):
        elems = [
            Paragraph(f"Orçamento #{orcamento.numero}", styles["TituloDoc"]),
            Paragraph(orcamento.oficina.nome, styles["SubDoc"]),
            Paragraph(f"<b>Cliente:</b> {orcamento.cliente.nome}", styles["Normal"]),
        ]
        if orcamento.veiculo:
            elems.append(Paragraph(f"<b>Veículo:</b> {orcamento.veiculo}", styles["Normal"]))
        elems.append(
            Paragraph(f"<b>Status:</b> {orcamento.get_status_display()}", styles["Normal"])
        )
        if orcamento.validade:
            elems.append(
                Paragraph(
                    f"<b>Validade:</b> {orcamento.validade.strftime('%d/%m/%Y')}", styles["Normal"]
                )
            )
        elems.append(Spacer(1, 14))
        elems.append(_tabela_itens(orcamento.itens.all()))
        elems.append(Spacer(1, 12))
        elems.append(Paragraph(f"<b>Total:</b> R$ {orcamento.total:.2f}", styles["Heading2"]))
        if orcamento.observacoes:
            elems.append(Spacer(1, 8))
            elems.append(
                Paragraph(f"<b>Observações:</b> {orcamento.observacoes}", styles["Normal"])
            )
        return elems

    return pdf_response(f"orcamento-{orcamento.numero}.pdf", story)
