from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from psycopg2.extras import RealDictCursor

from database import get_db_connection
from permissions import requer_permissao, tem_permissao, tem_role, VER_PIPELINE, GERENCIAR_PIPELINE

crm_bp = Blueprint("crm", __name__, url_prefix="/crm")

ETAPAS_PIPELINE = (
    "novo_cliente", "contato_realizado", "orcamento_enviado",
    "negociacao", "reserva", "locacao", "cliente_recorrente",
)
ETAPAS_LABEL = {
    "novo_cliente": "Novo cliente",
    "contato_realizado": "Contato realizado",
    "orcamento_enviado": "Orçamento enviado",
    "negociacao": "Negociação",
    "reserva": "Reserva",
    "locacao": "Locação",
    "cliente_recorrente": "Cliente recorrente",
}
TIPOS_TAREFA = ("ligar", "whatsapp", "enviar_orcamento", "follow_up")


def _pode_ver_todos():
    return not tem_role("atendente", "vendedor")


# ==== Pipeline (kanban por etapa, com tarefas pendentes de cada cliente) ====
@crm_bp.route("/pipeline")
@login_required
@requer_permissao(VER_PIPELINE)
def pipeline():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        if _pode_ver_todos():
            cur.execute("""
                SELECT p.cliente_id, p.etapa, p.atualizado_em, p.usuario_responsavel,
                       c.nome AS cliente_nome, c.telefone AS cliente_telefone,
                       u.username AS responsavel_nome
                FROM pipeline_clientes p
                JOIN clientes c ON c.id = p.cliente_id
                LEFT JOIN usuarios u ON u.id = p.usuario_responsavel
                ORDER BY c.nome ASC
            """)
        else:
            cur.execute("""
                SELECT p.cliente_id, p.etapa, p.atualizado_em, p.usuario_responsavel,
                       c.nome AS cliente_nome, c.telefone AS cliente_telefone,
                       u.username AS responsavel_nome
                FROM pipeline_clientes p
                JOIN clientes c ON c.id = p.cliente_id
                LEFT JOIN usuarios u ON u.id = p.usuario_responsavel
                WHERE p.usuario_responsavel = %s
                ORDER BY c.nome ASC
            """, (int(current_user.id),))
        pipeline_rows = cur.fetchall()

        if _pode_ver_todos():
            cur.execute("SELECT * FROM tarefas_crm WHERE concluida = FALSE ORDER BY data_prevista NULLS LAST, id ASC")
        else:
            cur.execute(
                "SELECT * FROM tarefas_crm WHERE concluida = FALSE AND usuario_responsavel = %s "
                "ORDER BY data_prevista NULLS LAST, id ASC",
                (int(current_user.id),),
            )
        tarefas_pendentes = cur.fetchall()

        tarefas_por_cliente = {}
        for t in tarefas_pendentes:
            tarefas_por_cliente.setdefault(t["cliente_id"], []).append(t)

        colunas = {etapa: [] for etapa in ETAPAS_PIPELINE}
        for row in pipeline_rows:
            row_dict = dict(row)
            row_dict["tarefas"] = tarefas_por_cliente.get(row["cliente_id"], [])
            colunas.setdefault(row["etapa"], []).append(row_dict)

        return render_template(
            "crm_pipeline.html", colunas=colunas, etapas=ETAPAS_PIPELINE, etapas_label=ETAPAS_LABEL,
            pode_gerenciar=tem_permissao(GERENCIAR_PIPELINE),
        )
    finally:
        cur.close()
        conn.close()


# ==== Mover cliente de etapa manualmente ====
@crm_bp.route("/pipeline/<int:cliente_id>/mover", methods=["POST"])
@login_required
@requer_permissao(GERENCIAR_PIPELINE)
def mover_etapa(cliente_id):
    nova_etapa = (request.form.get("etapa") or "").strip()
    if nova_etapa not in ETAPAS_PIPELINE:
        flash("Etapa inválida.", "warning")
        return redirect(url_for("crm.pipeline"))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT usuario_responsavel FROM pipeline_clientes WHERE cliente_id=%s", (cliente_id,))
        row = cur.fetchone()
        if not row:
            flash("Cliente não encontrado no pipeline.", "warning")
            return redirect(url_for("crm.pipeline"))

        if not _pode_ver_todos() and row["usuario_responsavel"] != int(current_user.id):
            flash("Você só pode mover clientes atribuídos a você.", "danger")
            return redirect(url_for("crm.pipeline"))

        cur.execute("""
            UPDATE pipeline_clientes SET etapa=%s, atualizado_em=CURRENT_TIMESTAMP WHERE cliente_id=%s
        """, (nova_etapa, cliente_id))
        conn.commit()
        flash("Cliente movido de etapa.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao mover cliente: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("crm.pipeline"))


# ==== Tarefas de CRM ====
@crm_bp.route("/tarefas", methods=["GET", "POST"])
@login_required
@requer_permissao(VER_PIPELINE)
def tarefas():
    if request.method == "POST":
        if not tem_permissao(GERENCIAR_PIPELINE):
            flash("Você não tem permissão para criar tarefas.", "danger")
            return redirect(url_for("crm.tarefas"))

        cliente_id = request.form.get("cliente_id", type=int)
        tipo = (request.form.get("tipo") or "").strip()
        descricao = (request.form.get("descricao") or "").strip() or None
        data_prevista = request.form.get("data_prevista") or None
        usuario_responsavel = request.form.get("usuario_responsavel", type=int) or int(current_user.id)

        if not cliente_id or tipo not in TIPOS_TAREFA:
            flash("Cliente e tipo de tarefa são obrigatórios.", "warning")
            return redirect(url_for("crm.tarefas"))

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("""
                INSERT INTO tarefas_crm (cliente_id, tipo, descricao, data_prevista, usuario_responsavel)
                VALUES (%s, %s, %s, %s, %s)
            """, (cliente_id, tipo, descricao, data_prevista, usuario_responsavel))
            conn.commit()
            flash("Tarefa criada.", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao criar tarefa: {e}", "danger")
        finally:
            cur.close()
            conn.close()
        return redirect(url_for("crm.tarefas"))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        if _pode_ver_todos():
            cur.execute("""
                SELECT t.*, c.nome AS cliente_nome, u.username AS responsavel_nome
                FROM tarefas_crm t
                JOIN clientes c ON c.id = t.cliente_id
                LEFT JOIN usuarios u ON u.id = t.usuario_responsavel
                ORDER BY t.concluida ASC, t.data_prevista NULLS LAST, t.id DESC
            """)
        else:
            cur.execute("""
                SELECT t.*, c.nome AS cliente_nome, u.username AS responsavel_nome
                FROM tarefas_crm t
                JOIN clientes c ON c.id = t.cliente_id
                LEFT JOIN usuarios u ON u.id = t.usuario_responsavel
                WHERE t.usuario_responsavel = %s
                ORDER BY t.concluida ASC, t.data_prevista NULLS LAST, t.id DESC
            """, (int(current_user.id),))
        tarefas_rows = cur.fetchall()

        cur.execute("SELECT id, nome FROM clientes ORDER BY nome ASC")
        clientes = cur.fetchall()

        return render_template(
            "crm_tarefas.html", tarefas=tarefas_rows, clientes=clientes, tipos=TIPOS_TAREFA,
            pode_gerenciar=tem_permissao(GERENCIAR_PIPELINE),
        )
    finally:
        cur.close()
        conn.close()


@crm_bp.route("/tarefas/<int:id>/concluir", methods=["POST"])
@login_required
@requer_permissao(GERENCIAR_PIPELINE)
def concluir_tarefa(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT usuario_responsavel FROM tarefas_crm WHERE id=%s", (id,))
        row = cur.fetchone()
        if not row:
            flash("Tarefa não encontrada.", "warning")
            return redirect(url_for("crm.tarefas"))

        if not _pode_ver_todos() and row["usuario_responsavel"] != int(current_user.id):
            flash("Você só pode concluir tarefas atribuídas a você.", "danger")
            return redirect(url_for("crm.tarefas"))

        cur.execute("UPDATE tarefas_crm SET concluida=TRUE WHERE id=%s", (id,))
        conn.commit()
        flash("Tarefa concluída.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao concluir tarefa: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("crm.tarefas"))
