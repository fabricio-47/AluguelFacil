import csv
import io

from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, abort
from flask_login import login_required, current_user
from xhtml2pdf import pisa

from database import get_db_connection
from permissions import tem_permissao, landing_url
from periodos import intervalo_periodo
from relatorios import RELATORIOS

relatorios_bp = Blueprint("relatorios", __name__, url_prefix="/relatorios")


@relatorios_bp.route("/")
@login_required
def index():
    return render_template("relatorios.html", relatorios=RELATORIOS)


def _periodo_atual():
    periodo = request.args.get("periodo") or "mes"
    inicio, fim = intervalo_periodo(periodo, request.args.get("inicio"), request.args.get("fim"))
    return periodo, inicio, fim


@relatorios_bp.route("/<slug>")
@login_required
def ver_relatorio(slug):
    info = RELATORIOS.get(slug)
    if not info:
        abort(404)
    if not tem_permissao(info["permissao"]):
        flash("Você não tem permissão para acessar este relatório.", "danger")
        return redirect(landing_url())

    periodo, inicio, fim = _periodo_atual()

    conn = get_db_connection()
    cur = conn.cursor()
    colunas, linhas = info["funcao"](cur, current_user.company_id, inicio, fim)
    cur.close()
    conn.close()

    return render_template(
        "relatorio.html", slug=slug, titulo=info["titulo"], colunas=colunas, linhas=linhas,
        periodo=periodo, data_inicio=inicio, data_fim=fim,
    )


@relatorios_bp.route("/<slug>/exportar/<formato>")
@login_required
def exportar_relatorio(slug, formato):
    info = RELATORIOS.get(slug)
    if not info or formato not in ("pdf", "csv"):
        abort(404)
    if not tem_permissao(info["permissao"]):
        flash("Você não tem permissão para acessar este relatório.", "danger")
        return redirect(landing_url())

    _, inicio, fim = _periodo_atual()

    conn = get_db_connection()
    cur = conn.cursor()
    colunas, linhas = info["funcao"](cur, current_user.company_id, inicio, fim)
    cur.close()
    conn.close()

    nome_arquivo = f"{slug}_{inicio}_{fim}"

    if formato == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(colunas)
        writer.writerows(linhas)
        return Response(
            buffer.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={nome_arquivo}.csv"},
        )

    html = render_template(
        "relatorio_pdf.html", titulo=info["titulo"], colunas=colunas, linhas=linhas,
        data_inicio=inicio, data_fim=fim,
    )
    pdf_buffer = io.BytesIO()
    resultado = pisa.CreatePDF(html, dest=pdf_buffer)
    if resultado.err:
        flash("Erro ao gerar o PDF do relatório.", "danger")
        return redirect(url_for("relatorios.ver_relatorio", slug=slug))

    return Response(
        pdf_buffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}.pdf"},
    )
