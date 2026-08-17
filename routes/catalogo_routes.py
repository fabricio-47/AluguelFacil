import datetime as dt
import os

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, send_from_directory, current_app
from psycopg2.extras import RealDictCursor

from database import get_db_connection

catalogo_bp = Blueprint("catalogo", __name__, url_prefix="/catalogo")


def _buscar_company_por_slug(cur, slug):
    cur.execute("SELECT id, nome, slug FROM companies WHERE slug=%s AND status != 'bloqueado'", (slug,))
    return cur.fetchone()


# ==== Catálogo público de uma company ====
@catalogo_bp.route("/<slug>")
def ver_catalogo(slug):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        company = _buscar_company_por_slug(cur, slug)
        if not company:
            abort(404)

        categoria_id = request.args.get("categoria", type=int)

        query = """
            SELECT ei.id, ei.nome, ei.marca, ei.modelo, ei.descricao, ei.foto,
                   ei.valor_diaria, ei.valor_semanal, ei.valor_mensal, ei.caucao,
                   ec.id AS categoria_id, ec.nome AS categoria_nome
            FROM equipment_items ei
            LEFT JOIN equipment_categories ec ON ec.id = ei.categoria_id
            WHERE ei.company_id = %s AND ei.status = 'disponivel'
        """
        params = [company["id"]]
        if categoria_id:
            query += " AND ei.categoria_id = %s"
            params.append(categoria_id)
        query += " ORDER BY ei.nome ASC"

        cur.execute(query, tuple(params))
        equipamentos = cur.fetchall()

        cur.execute("""
            SELECT DISTINCT ec.id, ec.nome
            FROM equipment_categories ec
            JOIN equipment_items ei ON ei.categoria_id = ec.id
            WHERE ei.company_id = %s AND ei.status = 'disponivel'
            ORDER BY ec.nome ASC
        """, (company["id"],))
        categorias = cur.fetchall()

        return render_template(
            "catalogo.html", company=company, equipamentos=equipamentos,
            categorias=categorias, categoria_selecionada=categoria_id,
        )
    finally:
        cur.close()
        conn.close()


# ==== Solicitar locação (cria cliente se necessário + orçamento) ====
@catalogo_bp.route("/<slug>/solicitar", methods=["POST"])
def solicitar_locacao(slug):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        company = _buscar_company_por_slug(cur, slug)
        if not company:
            abort(404)

        equipamento_id = request.form.get("equipamento_id", type=int)
        nome = (request.form.get("nome") or "").strip()
        telefone = (request.form.get("telefone") or "").strip()
        email = (request.form.get("email") or "").strip()
        data_desejada = (request.form.get("data_desejada") or "").strip()
        periodo_dias = request.form.get("periodo_dias", type=int)
        frequencia = (request.form.get("frequencia_pagamento") or "").strip().upper()

        if not equipamento_id or not nome or not telefone or not email:
            flash("Nome, telefone, e-mail e equipamento são obrigatórios.", "warning")
            return redirect(url_for("catalogo.ver_catalogo", slug=slug))
        if frequencia not in ("WEEKLY", "MONTHLY"):
            flash("Selecione a frequência de pagamento desejada.", "warning")
            return redirect(url_for("catalogo.ver_catalogo", slug=slug))

        cur.execute("""
            SELECT id, nome, status, valor_semanal, valor_mensal
            FROM equipment_items WHERE id=%s AND company_id=%s AND status='disponivel'
        """, (equipamento_id, company["id"]))
        equipamento = cur.fetchone()
        if not equipamento:
            flash("Equipamento não encontrado ou indisponível.", "warning")
            return redirect(url_for("catalogo.ver_catalogo", slug=slug))

        coluna_preco = "valor_semanal" if frequencia == "WEEKLY" else "valor_mensal"
        valor_unitario = equipamento[coluna_preco]
        if valor_unitario is None:
            flash("Este equipamento não tem preço cadastrado para essa frequência.", "warning")
            return redirect(url_for("catalogo.ver_catalogo", slug=slug))

        # Cliente é buscado/criado sem integração com o Asaas — esta é uma rota
        # pública e anônima; a equipe associa o Asaas depois, na tela interna,
        # antes de aprovar a conversão em locação (mesma trava já existente
        # em criar_locacao_interna).
        cur.execute(
            "SELECT id FROM clientes WHERE company_id=%s AND (email=%s OR telefone=%s)",
            (company["id"], email, telefone),
        )
        cliente_row = cur.fetchone()
        if cliente_row:
            cliente_id = cliente_row["id"]
        else:
            cur.execute("""
                INSERT INTO clientes (nome, email, telefone, company_id)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (nome, email, telefone, company["id"]))
            cliente_id = cur.fetchone()["id"]

            cur.execute("""
                INSERT INTO pipeline_clientes (cliente_id, etapa)
                VALUES (%s, 'novo_cliente')
            """, (cliente_id,))

        observacoes = f"Solicitação via catálogo online. Data desejada: {data_desejada or 'não informada'}."
        cur.execute("""
            INSERT INTO orcamentos (cliente_id, criado_por, status, observacoes)
            VALUES (%s, NULL, 'criado', %s)
            RETURNING id
        """, (cliente_id, observacoes))
        orcamento_id = cur.fetchone()["id"]

        cur.execute("""
            INSERT INTO orcamento_itens (
                orcamento_id, equipment_item_id, quantidade, periodo_dias,
                frequencia_pagamento, valor_unitario, desconto
            ) VALUES (%s, %s, 1, %s, %s, %s, 0)
        """, (orcamento_id, equipamento_id, periodo_dias, frequencia, valor_unitario))

        conn.commit()
        flash("Solicitação enviada! Nossa equipe vai entrar em contato em breve.", "success")
        return redirect(url_for("catalogo.ver_catalogo", slug=slug))

    except Exception as e:
        conn.rollback()
        print("Erro ao solicitar locação pelo catálogo:", e)
        flash("Erro ao enviar solicitação. Tente novamente.", "danger")
        return redirect(url_for("catalogo.ver_catalogo", slug=slug))
    finally:
        cur.close()
        conn.close()


# ==== Imagens de equipamento (públicas, mesma pasta usada pela área interna) ====
@catalogo_bp.route("/imagens/<filename>")
def imagem_equipamento(filename):
    pasta = os.path.join(current_app.config["UPLOAD_FOLDER"], "motos")
    return send_from_directory(pasta, filename)
