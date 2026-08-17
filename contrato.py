from io import BytesIO

from flask import render_template
from xhtml2pdf import pisa

FREQUENCIA_LABEL = {"WEEKLY": "semanal", "MONTHLY": "mensal"}


def gerar_contrato_pdf(locacao, cliente, equipamento, company, assinatura=None):
    """
    Renderiza templates/contrato_pdf.html com os dados da locação e converte
    para bytes de PDF. `assinatura`, se informada, é um dict com
    caminho_imagem (path absoluto no disco), nome_assinante, data_hora e
    ip_address — embutidos no rodapé como prova da assinatura eletrônica.
    """
    valor = locacao["valor"] or 0
    data_inicio = locacao["data_inicio"]

    html = render_template(
        "contrato_pdf.html",
        locacao=locacao,
        cliente=cliente,
        equipamento=equipamento,
        company=company,
        assinatura=assinatura,
        frequencia_label=FREQUENCIA_LABEL.get(locacao["frequencia_pagamento"], locacao["frequencia_pagamento"]),
        valor_formatado=f"R$ {valor:.2f}".replace(".", ","),
        data_inicio_formatada=data_inicio.strftime("%d/%m/%Y") if hasattr(data_inicio, "strftime") else data_inicio,
    )

    buffer = BytesIO()
    resultado = pisa.CreatePDF(html, dest=buffer)
    if resultado.err:
        raise RuntimeError("Falha ao gerar o PDF do contrato.")

    return buffer.getvalue()
