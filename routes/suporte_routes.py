import datetime as dt

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from database import get_db_connection
from permissions import requer_permissao, VER_SUPORTE, GERENCIAR_SUPORTE

suporte_bp = Blueprint("suporte", __name__, url_prefix="/suporte")


@suporte_bp.route("/")
@login_required
@requer_permissao(VER_SUPORTE)
def listar_tickets():
    status_filtro = request.args.get("status", "aberto")

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        query = """
            SELECT t.id, t.assunto, t.status, t.created_at, t.updated_at,
                   c.nome AS cliente_nome
            FROM suporte_tickets t
            JOIN clientes c ON c.id = t.cliente_id
            WHERE t.company_id = %s
        """
        params = [current_user.company_id]
        if status_filtro in ("aberto", "respondido", "fechado"):
            query += " AND t.status = %s"
            params.append(status_filtro)
        query += " ORDER BY t.updated_at DESC"

        cur.execute(query, tuple(params))
        tickets = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return render_template("suporte_lista.html", tickets=tickets, status_filtro=status_filtro)


def _ticket_da_empresa(cur, ticket_id):
    cur.execute(
        "SELECT id, cliente_id, assunto, status FROM suporte_tickets WHERE id=%s AND company_id=%s",
        (ticket_id, current_user.company_id),
    )
    return cur.fetchone()


@suporte_bp.route("/<int:ticket_id>", methods=["GET", "POST"])
@login_required
@requer_permissao(VER_SUPORTE)
def ver_ticket(ticket_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        ticket = _ticket_da_empresa(cur, ticket_id)
        if not ticket:
            flash("Ticket não encontrado.", "warning")
            return redirect(url_for("suporte.listar_tickets"))

        if request.method == "POST":
            from permissions import tem_permissao
            if not tem_permissao(GERENCIAR_SUPORTE):
                flash("Você não tem permissão para responder tickets de suporte.", "danger")
                return redirect(url_for("suporte.ver_ticket", ticket_id=ticket_id))

            acao = request.form.get("acao")

            if acao == "responder":
                mensagem = (request.form.get("mensagem") or "").strip()
                if mensagem:
                    cur.execute(
                        "INSERT INTO suporte_mensagens (ticket_id, autor_tipo, autor_usuario_id, mensagem) "
                        "VALUES (%s, 'funcionario', %s, %s)",
                        (ticket_id, current_user.id, mensagem),
                    )
                    cur.execute(
                        "UPDATE suporte_tickets SET status='respondido', updated_at=NOW() WHERE id=%s",
                        (ticket_id,),
                    )
                    conn.commit()
                    flash("Resposta enviada.", "success")
            elif acao == "fechar":
                cur.execute(
                    "UPDATE suporte_tickets SET status='fechado', updated_at=NOW() WHERE id=%s",
                    (ticket_id,),
                )
                conn.commit()
                flash("Ticket fechado.", "success")
            elif acao == "reabrir":
                cur.execute(
                    "UPDATE suporte_tickets SET status='aberto', updated_at=NOW() WHERE id=%s",
                    (ticket_id,),
                )
                conn.commit()
                flash("Ticket reaberto.", "success")

            return redirect(url_for("suporte.ver_ticket", ticket_id=ticket_id))

        cur.execute(
            "SELECT id, cliente_id, assunto, status, created_at FROM suporte_tickets WHERE id=%s",
            (ticket_id,),
        )
        ticket_completo = cur.fetchone()

        cur.execute("SELECT nome, email FROM clientes WHERE id=%s", (ticket_completo["cliente_id"],))
        cliente = cur.fetchone()

        cur.execute(
            """
            SELECT m.autor_tipo, m.mensagem, m.created_at,
                   COALESCE(u.username, c.nome) AS autor_nome
            FROM suporte_mensagens m
            LEFT JOIN usuarios u ON u.id = m.autor_usuario_id
            LEFT JOIN clientes c ON c.id = m.autor_cliente_id
            WHERE m.ticket_id = %s
            ORDER BY m.created_at ASC
            """,
            (ticket_id,),
        )
        mensagens = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return render_template(
        "suporte_detalhe.html", ticket=ticket_completo, cliente=cliente, mensagens=mensagens,
    )
