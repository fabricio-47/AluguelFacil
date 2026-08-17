from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from database import get_db_connection

servicos_bp = Blueprint("servicos", __name__, url_prefix="/servicos")

# Listar e cadastrar serviços de uma locação
@servicos_bp.route("/<int:locacao_id>", methods=["GET", "POST"])
@login_required
def listar_servicos(locacao_id):
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        descricao = request.form["descricao"].strip()
        valor = request.form.get("valor") or 0

        try:
            cur.execute("""
                INSERT INTO servicos_locacao (locacao_id, descricao, valor)
                VALUES (%s, %s, %s)
            """, (locacao_id, descricao, valor))
            conn.commit()
            flash("Serviço adicionado à locação!", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao adicionar serviço: {e}", "danger")
        finally:
            cur.close()
            conn.close()

        return redirect(url_for("servicos.listar_servicos", locacao_id=locacao_id))

    # GET: listar serviços da locação
    cur.execute("""
        SELECT s.id, s.descricao, s.valor, s.data_servico
        FROM servicos_locacao s
        WHERE s.locacao_id = %s
        ORDER BY s.id DESC
    """, (locacao_id,))
    servicos = cur.fetchall()

    cur.execute("""
        SELECT l.id, c.nome, ei.modelo, ei.codigo_interno AS placa
        FROM locacoes l
        JOIN clientes c ON c.id = l.cliente_id
        JOIN equipment_items ei ON ei.id = l.equipment_item_id
        WHERE l.id = %s
    """, (locacao_id,))
    locacao = cur.fetchone()

    cur.close()
    conn.close()
    return render_template("servicos_locacao.html", servicos=servicos, locacao=locacao, locacao_id=locacao_id)

# Excluir um serviço
@servicos_bp.route("/<int:locacao_id>/<int:servico_id>/excluir", methods=["POST"])
@login_required
def excluir_servico(locacao_id, servico_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM servicos_locacao WHERE id=%s AND locacao_id=%s", (servico_id, locacao_id))
        conn.commit()
        flash("Serviço removido.", "info")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao remover serviço: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("servicos.listar_servicos", locacao_id=locacao_id))