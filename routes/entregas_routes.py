from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from database import get_db_connection
from permissions import requer_permissao, tem_permissao, tem_role, VER_ENTREGAS, GERENCIAR_ENTREGAS

entregas_bp = Blueprint("entregas", __name__, url_prefix="/entregas")

STATUS = ("aguardando", "em_separacao", "saiu_para_entrega", "entregue", "retirada_agendada", "finalizada")


# ======================
# Listar (filtrado pra entregador) e criar (só quem despacha)
# ======================
@entregas_bp.route("/", methods=["GET", "POST"])
@login_required
@requer_permissao(VER_ENTREGAS)
def listar_entregas():
    pode_gerenciar = tem_permissao(GERENCIAR_ENTREGAS)

    if request.method == "POST":
        if not pode_gerenciar:
            flash("Você não tem permissão para criar entregas.", "danger")
            return redirect(url_for("entregas.listar_entregas"))

        conn = get_db_connection()
        cur = conn.cursor()

        locacao_id = request.form.get("locacao_id", type=int)
        endereco = (request.form.get("endereco") or "").strip()
        entregador_id = request.form.get("entregador_id", type=int) or None
        veiculo = (request.form.get("veiculo") or "").strip() or None
        horario_previsto = request.form.get("horario_previsto") or None
        observacoes = (request.form.get("observacoes") or "").strip() or None

        if not locacao_id or not endereco:
            cur.close()
            conn.close()
            flash("Locação e endereço são obrigatórios.", "warning")
            return redirect(url_for("entregas.listar_entregas"))

        try:
            cur.execute("""
                INSERT INTO entregas (locacao_id, endereco, entregador_id, veiculo, horario_previsto, observacoes)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (locacao_id, endereco, entregador_id, veiculo, horario_previsto, observacoes))
            conn.commit()
            flash("Entrega registrada com sucesso!", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao registrar entrega: {e}", "danger")
        finally:
            cur.close()
            conn.close()

        return redirect(url_for("entregas.listar_entregas"))

    conn = get_db_connection()
    cur = conn.cursor()

    if pode_gerenciar:
        cur.execute("""
            SELECT e.id, e.endereco, e.veiculo, e.horario_previsto, e.status, e.observacoes,
                   l.id AS locacao_id, c.nome AS cliente_nome, u.username AS entregador_nome
            FROM entregas e
            JOIN locacoes l ON l.id = e.locacao_id
            JOIN clientes c ON c.id = l.cliente_id
            LEFT JOIN usuarios u ON u.id = e.entregador_id
            ORDER BY e.horario_previsto NULLS LAST, e.id DESC
        """)
    else:
        cur.execute("""
            SELECT e.id, e.endereco, e.veiculo, e.horario_previsto, e.status, e.observacoes,
                   l.id AS locacao_id, c.nome AS cliente_nome, u.username AS entregador_nome
            FROM entregas e
            JOIN locacoes l ON l.id = e.locacao_id
            JOIN clientes c ON c.id = l.cliente_id
            LEFT JOIN usuarios u ON u.id = e.entregador_id
            WHERE e.entregador_id = %s
            ORDER BY e.horario_previsto NULLS LAST, e.id DESC
        """, (int(current_user.id),))
    entregas = cur.fetchall()

    clientes_ou_locacoes = []
    entregadores = []
    if pode_gerenciar:
        cur.execute("""
            SELECT l.id, c.nome AS cliente_nome, ei.nome AS equipamento_nome
            FROM locacoes l
            JOIN clientes c ON c.id = l.cliente_id
            JOIN equipment_items ei ON ei.id = l.equipment_item_id
            WHERE l.cancelado = FALSE
            ORDER BY l.id DESC
        """)
        clientes_ou_locacoes = cur.fetchall()

        cur.execute("SELECT id, username FROM usuarios WHERE role='entregador' ORDER BY username")
        entregadores = cur.fetchall()

    cur.close()
    conn.close()
    return render_template(
        "entregas.html", entregas=entregas, pode_gerenciar=pode_gerenciar,
        locacoes=clientes_ou_locacoes, entregadores=entregadores, status_opcoes=STATUS,
    )


# ======================
# Atualizar status
# ======================
@entregas_bp.route("/<int:id>/status", methods=["POST"])
@login_required
@requer_permissao(VER_ENTREGAS)
def atualizar_status(id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT entregador_id FROM entregas WHERE id=%s", (id,))
    entrega = cur.fetchone()
    if not entrega:
        cur.close()
        conn.close()
        flash("Entrega não encontrada.", "warning")
        return redirect(url_for("entregas.listar_entregas"))

    pode_atualizar = tem_permissao(GERENCIAR_ENTREGAS) or (
        tem_role("entregador") and entrega["entregador_id"] == int(current_user.id)
    )
    if not pode_atualizar:
        cur.close()
        conn.close()
        flash("Você não tem permissão para atualizar esta entrega.", "danger")
        return redirect(url_for("entregas.listar_entregas"))

    status = request.form.get("status")
    if status not in STATUS:
        cur.close()
        conn.close()
        flash("Status inválido.", "warning")
        return redirect(url_for("entregas.listar_entregas"))

    try:
        cur.execute("UPDATE entregas SET status=%s WHERE id=%s", (status, id))
        conn.commit()
        flash("Status da entrega atualizado!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao atualizar status: {e}", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("entregas.listar_entregas"))
