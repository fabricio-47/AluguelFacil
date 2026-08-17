from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from database import get_db_connection
from permissions import requer_permissao, tem_permissao, VER_FILIAIS, GERENCIAR_FILIAIS
from estoque import registrar_movimentacao
from planos import verificar_limite

filiais_bp = Blueprint("filiais", __name__, url_prefix="/filiais")


# ======================
# Listar e cadastrar filiais
# ======================
@filiais_bp.route("/", methods=["GET", "POST"])
@login_required
@requer_permissao(VER_FILIAIS)
def listar_filiais():
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        if not tem_permissao(GERENCIAR_FILIAIS):
            cur.close()
            conn.close()
            flash("Você não tem permissão para cadastrar filiais.", "danger")
            return redirect(url_for("filiais.listar_filiais"))

        nome = (request.form.get("nome") or "").strip()
        endereco = (request.form.get("endereco") or "").strip() or None
        if not nome:
            cur.close()
            conn.close()
            flash("Nome da filial é obrigatório.", "warning")
            return redirect(url_for("filiais.listar_filiais"))

        limite = verificar_limite(cur, current_user.company_id, "limite_filiais", "branches")
        if not limite["dentro_do_limite"]:
            cur.close()
            conn.close()
            flash(
                f"Limite de filiais do plano atingido ({limite['usado']}/{limite['limite']}). "
                f"Fale com o suporte pra aumentar o limite.",
                "danger",
            )
            return redirect(url_for("filiais.listar_filiais"))

        try:
            cur.execute(
                "INSERT INTO branches (company_id, nome, endereco) VALUES (%s, %s, %s)",
                (current_user.company_id, nome, endereco),
            )
            conn.commit()
            flash("Filial cadastrada com sucesso!", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao cadastrar filial: {e}", "danger")
        finally:
            cur.close()
            conn.close()

        return redirect(url_for("filiais.listar_filiais"))

    cur.execute("""
        SELECT b.id, b.nome, b.endereco, COUNT(ei.id) AS total_equipamentos
        FROM branches b
        LEFT JOIN equipment_items ei ON ei.branch_id = b.id
        GROUP BY b.id, b.nome, b.endereco
        ORDER BY b.nome
    """)
    filiais = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("filiais.html", filiais=filiais)


# ======================
# Editar filial
# ======================
@filiais_bp.route("/<int:id>/editar", methods=["GET", "POST"])
@login_required
@requer_permissao(GERENCIAR_FILIAIS)
def editar_filial(id):
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        endereco = (request.form.get("endereco") or "").strip() or None
        if not nome:
            flash("Nome da filial é obrigatório.", "warning")
        else:
            try:
                cur.execute("UPDATE branches SET nome=%s, endereco=%s WHERE id=%s", (nome, endereco, id))
                conn.commit()
                flash("Filial atualizada com sucesso!", "success")
                return redirect(url_for("filiais.listar_filiais"))
            except Exception as e:
                conn.rollback()
                flash(f"Erro ao atualizar filial: {e}", "danger")

    cur.execute("SELECT id, nome, endereco FROM branches WHERE id=%s", (id,))
    filial = cur.fetchone()
    cur.close()
    conn.close()

    if not filial:
        flash("Filial não encontrada.", "warning")
        return redirect(url_for("filiais.listar_filiais"))

    return render_template("editar_filial.html", filial=filial)


# ======================
# Transferir equipamento entre filiais (ação separada, auditada)
# ======================
@filiais_bp.route("/transferir/<int:equipamento_id>", methods=["GET", "POST"])
@login_required
@requer_permissao(GERENCIAR_FILIAIS)
def transferir_equipamento(equipamento_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT ei.id, ei.nome, ei.codigo_interno, ei.branch_id, b.nome AS filial_atual_nome
        FROM equipment_items ei
        LEFT JOIN branches b ON b.id = ei.branch_id
        WHERE ei.id=%s
    """, (equipamento_id,))
    equipamento = cur.fetchone()
    if not equipamento:
        cur.close()
        conn.close()
        flash("Equipamento não encontrado.", "warning")
        return redirect(url_for("equipamentos.listar_equipamentos"))

    if request.method == "POST":
        nova_filial_id = request.form.get("branch_id", type=int)
        motivo = (request.form.get("motivo") or "").strip() or None

        cur.execute("SELECT nome FROM branches WHERE id=%s", (nova_filial_id,))
        nova_filial = cur.fetchone()
        if not nova_filial_id or not nova_filial:
            cur.close()
            conn.close()
            flash("Selecione uma filial de destino válida.", "warning")
            return redirect(url_for("filiais.transferir_equipamento", equipamento_id=equipamento_id))

        try:
            cur.execute("UPDATE equipment_items SET branch_id=%s WHERE id=%s", (nova_filial_id, equipamento_id))
            descricao = f"Transferido de '{equipamento['filial_atual_nome'] or 'sem filial'}' para '{nova_filial['nome']}'"
            if motivo:
                descricao += f" — {motivo}"
            registrar_movimentacao(cur, equipamento_id, "transferencia", descricao, int(current_user.id))
            conn.commit()
            flash("Equipamento transferido com sucesso!", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao transferir equipamento: {e}", "danger")
        finally:
            cur.close()
            conn.close()

        return redirect(url_for("equipamentos.editar_equipamento", id=equipamento_id))

    cur.execute("SELECT id, nome FROM branches WHERE id != %s ORDER BY nome", (equipamento["branch_id"] or 0,))
    outras_filiais = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("transferir_equipamento.html", equipamento=equipamento, outras_filiais=outras_filiais)
