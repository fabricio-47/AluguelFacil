import os

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_from_directory, abort
from psycopg2.extras import RealDictCursor
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db_connection
from portal_auth import login_cliente, logout_cliente, cliente_atual, requer_login_cliente

portal_bp = Blueprint("portal", __name__, url_prefix="/portal")


# ==== Login do cliente ====
@portal_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        senha = request.form.get("senha") or ""

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("SELECT id, senha FROM clientes WHERE email=%s", (email,))
            cliente = cur.fetchone()
        finally:
            cur.close()
            conn.close()

        if not cliente or not cliente["senha"]:
            flash("Cliente não encontrado ou ainda sem senha definida. Faça seu primeiro acesso.", "info")
            return redirect(url_for("portal.primeiro_acesso"))

        if check_password_hash(cliente["senha"], senha):
            login_cliente(cliente["id"])
            flash("Login efetuado!", "success")
            return redirect(url_for("portal.dashboard"))

        flash("E-mail ou senha incorretos.", "danger")

    return render_template("portal_login.html")


@portal_bp.route("/logout", methods=["POST"])
def logout():
    logout_cliente()
    flash("Você saiu do portal.", "success")
    return redirect(url_for("portal.login"))


# ==== Primeiro acesso: confirma email + cpf/telefone, define senha ====
@portal_bp.route("/primeiro-acesso", methods=["GET", "POST"])
def primeiro_acesso():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        documento = (request.form.get("documento") or "").strip()
        senha = request.form.get("senha") or ""
        confirmar_senha = request.form.get("confirmar_senha") or ""

        if not email or not documento:
            flash("Informe e-mail e CPF ou telefone cadastrados.", "warning")
            return redirect(url_for("portal.primeiro_acesso"))
        if len(senha) < 6:
            flash("A senha precisa ter pelo menos 6 caracteres.", "warning")
            return redirect(url_for("portal.primeiro_acesso"))
        if senha != confirmar_senha:
            flash("As senhas não coincidem.", "warning")
            return redirect(url_for("portal.primeiro_acesso"))

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute(
                "SELECT id FROM clientes WHERE email=%s AND (cpf=%s OR telefone=%s)",
                (email, documento, documento),
            )
            cliente = cur.fetchone()
            if not cliente:
                flash("Não encontramos um cliente com esses dados. Confira e-mail e CPF/telefone.", "danger")
                return redirect(url_for("portal.primeiro_acesso"))

            cur.execute("UPDATE clientes SET senha=%s WHERE id=%s", (generate_password_hash(senha), cliente["id"]))
            conn.commit()
            flash("Senha definida! Faça login.", "success")
            return redirect(url_for("portal.login"))
        finally:
            cur.close()
            conn.close()

    return render_template("portal_primeiro_acesso.html")


# ==== Dashboard do cliente ====
@portal_bp.route("/")
@requer_login_cliente
def dashboard():
    cliente = cliente_atual()
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT l.id, l.data_inicio, l.data_fim, l.valor, l.frequencia_pagamento,
                   l.cancelado, l.pagamento_status, l.valor_pago, l.contrato_arquivo,
                   ei.nome AS equipamento_nome, ei.modelo AS equipamento_modelo
            FROM locacoes l
            JOIN equipment_items ei ON ei.id = l.equipment_item_id
            WHERE l.cliente_id = %s
            ORDER BY l.cancelado ASC, l.data_inicio DESC
        """, (cliente["id"],))
        locacoes = cur.fetchall()

        cur.execute("""
            SELECT id, status, valor_total, validade, created_at
            FROM orcamentos WHERE cliente_id = %s
            ORDER BY id DESC
        """, (cliente["id"],))
        orcamentos = cur.fetchall()

        return render_template(
            "portal_dashboard.html", cliente=cliente, locacoes=locacoes, orcamentos=orcamentos,
        )
    finally:
        cur.close()
        conn.close()


# ==== Download do contrato (só se a locação for do cliente logado) ====
@portal_bp.route("/contrato/<int:locacao_id>/pdf")
@requer_login_cliente
def contrato_pdf(locacao_id):
    cliente = cliente_atual()
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT cliente_id, contrato_arquivo FROM locacoes WHERE id=%s", (locacao_id,))
        locacao = cur.fetchone()
        if not locacao or locacao["cliente_id"] != cliente["id"]:
            abort(404)
        if not locacao["contrato_arquivo"]:
            flash("Contrato não encontrado.", "warning")
            return redirect(url_for("portal.dashboard"))

        uploads_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], "contratos")
        return send_from_directory(directory=uploads_dir, path=locacao["contrato_arquivo"])
    finally:
        cur.close()
        conn.close()
