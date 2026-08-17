import datetime as dt

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from database import get_db_connection
from permissions import requer_permissao, tem_permissao, VER_MANUTENCOES, GERENCIAR_MANUTENCOES
from estoque import registrar_movimentacao

manutencoes_bp = Blueprint("manutencoes", __name__, url_prefix="/manutencoes")

TIPOS = ("preventiva", "corretiva", "emergencial")
STATUS = ("aberta", "em_andamento", "concluida")


def _status_equipamento_para(status_manutencao, equipment_item_id, cur):
    """Deriva o status do equipamento a partir do status atual da manutenção."""
    if status_manutencao != "concluida":
        return "manutencao"

    cur.execute("""
        SELECT c.estado_geral
        FROM checklists c
        JOIN locacoes l ON l.id = c.locacao_id
        WHERE l.equipment_item_id = %s AND c.tipo = 'devolucao'
        ORDER BY c.criado_em DESC
        LIMIT 1
    """, (equipment_item_id,))
    ultimo_checklist = cur.fetchone()
    if ultimo_checklist and ultimo_checklist["estado_geral"] == "danificado":
        return "danificado"
    return "disponivel"


# ======================
# Listar e abrir manutenção
# ======================
@manutencoes_bp.route("/", methods=["GET", "POST"])
@login_required
@requer_permissao(VER_MANUTENCOES)
def listar_manutencoes():
    if request.method == "POST" and not tem_permissao(GERENCIAR_MANUTENCOES):
        flash("Você não tem permissão para abrir manutenções.", "danger")
        return redirect(url_for("manutencoes.listar_manutencoes"))

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        equipment_item_id = request.form.get("equipment_item_id", type=int)
        tipo = request.form.get("tipo")
        problema = (request.form.get("problema") or "").strip()
        tecnico_id = request.form.get("tecnico_id", type=int) or None
        data_conclusao_prevista = request.form.get("data_conclusao_prevista") or None
        fornecedor = (request.form.get("fornecedor") or "").strip() or None

        if tipo not in TIPOS or not equipment_item_id or not problema:
            cur.close()
            conn.close()
            flash("Equipamento, tipo e descrição do problema são obrigatórios.", "warning")
            return redirect(url_for("manutencoes.listar_manutencoes"))

        try:
            cur.execute("""
                INSERT INTO manutencoes (
                    equipment_item_id, tipo, problema, tecnico_id, data_conclusao_prevista, fornecedor
                ) VALUES (%s,%s,%s,%s,%s,%s)
            """, (equipment_item_id, tipo, problema, tecnico_id, data_conclusao_prevista, fornecedor))

            cur.execute(
                "UPDATE equipment_items SET status='manutencao', quantidade_disponivel=0 WHERE id=%s",
                (equipment_item_id,),
            )
            registrar_movimentacao(cur, equipment_item_id, "manutencao", f"Manutenção aberta: {problema}", int(current_user.id))

            conn.commit()
            flash("Manutenção aberta! Equipamento marcado como em manutenção.", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao abrir manutenção: {e}", "danger")
        finally:
            cur.close()
            conn.close()

        return redirect(url_for("manutencoes.listar_manutencoes"))

    cur.execute("""
        SELECT m.id, m.tipo, m.problema, m.status, m.data_abertura, m.data_conclusao_prevista,
               ei.nome AS equipamento_nome, ei.codigo_interno,
               u.username AS tecnico_nome
        FROM manutencoes m
        JOIN equipment_items ei ON ei.id = m.equipment_item_id
        LEFT JOIN usuarios u ON u.id = m.tecnico_id
        ORDER BY (m.status != 'concluida') DESC, m.data_abertura DESC
    """)
    manutencoes = cur.fetchall()

    cur.execute("SELECT id, nome, codigo_interno FROM equipment_items ORDER BY nome")
    equipamentos = cur.fetchall()

    cur.execute("SELECT id, username FROM usuarios WHERE role IN ('tecnico', 'estoquista') ORDER BY username")
    tecnicos = cur.fetchall()

    cur.close()
    conn.close()
    return render_template(
        "manutencoes.html", manutencoes=manutencoes, equipamentos=equipamentos, tecnicos=tecnicos, tipos=TIPOS,
    )


# ======================
# Editar / concluir manutenção
# ======================
@manutencoes_bp.route("/<int:id>/editar", methods=["GET", "POST"])
@login_required
@requer_permissao(GERENCIAR_MANUTENCOES)
def editar_manutencao(id):
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        tipo = request.form.get("tipo")
        problema = (request.form.get("problema") or "").strip()
        status = request.form.get("status")
        tecnico_id = request.form.get("tecnico_id", type=int) or None
        data_conclusao_prevista = request.form.get("data_conclusao_prevista") or None
        data_conclusao_real = request.form.get("data_conclusao_real") or None
        pecas_utilizadas = (request.form.get("pecas_utilizadas") or "").strip() or None
        valor = request.form.get("valor") or None
        fornecedor = (request.form.get("fornecedor") or "").strip() or None

        if tipo not in TIPOS or status not in STATUS or not problema:
            flash("Tipo, status e descrição do problema são obrigatórios.", "warning")
        else:
            if status == "concluida" and not data_conclusao_real:
                data_conclusao_real = dt.date.today().isoformat()

            try:
                cur.execute("SELECT equipment_item_id FROM manutencoes WHERE id=%s", (id,))
                manutencao_atual = cur.fetchone()
                if not manutencao_atual:
                    flash("Manutenção não encontrada.", "warning")
                    return redirect(url_for("manutencoes.listar_manutencoes"))
                equipment_item_id = manutencao_atual["equipment_item_id"]

                cur.execute("""
                    UPDATE manutencoes SET
                        tipo=%s, problema=%s, status=%s, tecnico_id=%s,
                        data_conclusao_prevista=%s, data_conclusao_real=%s,
                        pecas_utilizadas=%s, valor=%s, fornecedor=%s
                    WHERE id=%s
                """, (
                    tipo, problema, status, tecnico_id, data_conclusao_prevista, data_conclusao_real,
                    pecas_utilizadas, valor, fornecedor, id,
                ))

                cur.execute("SELECT status FROM equipment_items WHERE id=%s", (equipment_item_id,))
                status_equipamento_anterior = cur.fetchone()["status"]

                novo_status_equipamento = _status_equipamento_para(status, equipment_item_id, cur)
                nova_quantidade = 1 if novo_status_equipamento == "disponivel" else 0
                cur.execute(
                    "UPDATE equipment_items SET status=%s, quantidade_disponivel=%s WHERE id=%s",
                    (novo_status_equipamento, nova_quantidade, equipment_item_id),
                )

                if novo_status_equipamento != status_equipamento_anterior:
                    registrar_movimentacao(
                        cur, equipment_item_id, "manutencao",
                        f"Manutenção #{id} — status da manutenção: {status}, equipamento: "
                        f"'{status_equipamento_anterior}' → '{novo_status_equipamento}'",
                        int(current_user.id),
                    )

                conn.commit()
                flash("Manutenção atualizada com sucesso!", "success")
                return redirect(url_for("manutencoes.listar_manutencoes"))
            except Exception as e:
                conn.rollback()
                flash(f"Erro ao atualizar manutenção: {e}", "danger")

    cur.execute("""
        SELECT m.id, m.equipment_item_id, m.tipo, m.problema, m.status, m.tecnico_id,
               m.data_abertura, m.data_conclusao_prevista, m.data_conclusao_real,
               m.pecas_utilizadas, m.valor, m.fornecedor,
               ei.nome AS equipamento_nome, ei.codigo_interno
        FROM manutencoes m
        JOIN equipment_items ei ON ei.id = m.equipment_item_id
        WHERE m.id=%s
    """, (id,))
    manutencao = cur.fetchone()

    cur.execute("SELECT id, username FROM usuarios WHERE role IN ('tecnico', 'estoquista') ORDER BY username")
    tecnicos = cur.fetchall()

    cur.close()
    conn.close()

    if not manutencao:
        flash("Manutenção não encontrada.", "warning")
        return redirect(url_for("manutencoes.listar_manutencoes"))

    return render_template("editar_manutencao.html", manutencao=manutencao, tecnicos=tecnicos, tipos=TIPOS, status_opcoes=STATUS)
