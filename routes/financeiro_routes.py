import datetime as dt

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from database import get_db_connection
from permissions import requer_permissao, requer_role, tem_permissao, VER_DESPESAS, GERENCIAR_DESPESAS
from periodos import parse_date, limites_mes, intervalo_periodo

TIPOS_MULTA = ("fixa", "percentual", "nova_diaria")

financeiro_bp = Blueprint("financeiro", __name__, url_prefix="/financeiro")

CATEGORIAS = {
    "manutencao", "fornecedor", "funcionario", "energia",
    "aluguel", "marketing", "imposto", "outra",
}

# Status calculado (nunca gravado): pendente + vencida vira "atrasado" só na exibição.
STATUS_EXIBIDO_SQL = (
    "CASE WHEN status = 'pendente' AND data_vencimento < CURRENT_DATE "
    "THEN 'atrasado' ELSE status END"
)


def _campos_despesa(form):
    categoria = form.get("categoria") or "outra"
    if categoria not in CATEGORIAS:
        categoria = "outra"

    paga = bool(form.get("paga"))
    data_pagamento = parse_date(form.get("data_pagamento"))
    if paga and not data_pagamento:
        data_pagamento = dt.date.today()
    if not paga:
        data_pagamento = None

    return {
        "categoria": categoria,
        "descricao": (form.get("descricao") or "").strip(),
        "valor": form.get("valor") or None,
        "data_vencimento": form.get("data_vencimento") or None,
        "data_pagamento": data_pagamento,
        "status": "pago" if paga else "pendente",
        "fornecedor": (form.get("fornecedor") or "").strip() or None,
        "forma_pagamento": (form.get("forma_pagamento") or "").strip() or None,
        "observacoes": (form.get("observacoes") or "").strip() or None,
    }


# ======================
# Despesas — listar/cadastrar
# ======================
@financeiro_bp.route("/despesas", methods=["GET", "POST"])
@login_required
@requer_permissao(VER_DESPESAS)
def listar_despesas():
    if request.method == "POST" and not tem_permissao(GERENCIAR_DESPESAS):
        flash("Você não tem permissão para cadastrar despesas.", "danger")
        return redirect(url_for("financeiro.listar_despesas"))

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        campos = _campos_despesa(request.form)
        if not campos["descricao"] or not campos["valor"] or not campos["data_vencimento"]:
            cur.close()
            conn.close()
            flash("Descrição, valor e data de vencimento são obrigatórios.", "warning")
            return redirect(url_for("financeiro.listar_despesas"))

        try:
            cur.execute("""
                INSERT INTO despesas (
                    categoria, descricao, valor, data_vencimento, data_pagamento,
                    status, fornecedor, forma_pagamento, observacoes
                ) VALUES (%(categoria)s,%(descricao)s,%(valor)s,%(data_vencimento)s,%(data_pagamento)s,
                    %(status)s,%(fornecedor)s,%(forma_pagamento)s,%(observacoes)s)
            """, campos)
            conn.commit()
            flash("Despesa cadastrada com sucesso!", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao cadastrar despesa: {e}", "danger")
        finally:
            cur.close()
            conn.close()

        return redirect(url_for("financeiro.listar_despesas"))

    cur.execute(f"""
        SELECT id, categoria, descricao, valor, data_vencimento, data_pagamento,
               fornecedor, forma_pagamento, {STATUS_EXIBIDO_SQL} AS status_exibido
        FROM despesas
        ORDER BY data_vencimento DESC, id DESC
    """)
    despesas = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("despesas.html", despesas=despesas, categorias=sorted(CATEGORIAS))


# ======================
# Despesas — editar / marcar como paga
# ======================
@financeiro_bp.route("/despesas/<int:id>/editar", methods=["GET", "POST"])
@login_required
@requer_permissao(GERENCIAR_DESPESAS)
def editar_despesa(id):
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        campos = _campos_despesa(request.form)
        if not campos["descricao"] or not campos["valor"] or not campos["data_vencimento"]:
            flash("Descrição, valor e data de vencimento são obrigatórios.", "warning")
        else:
            try:
                cur.execute("""
                    UPDATE despesas SET
                        categoria=%(categoria)s, descricao=%(descricao)s, valor=%(valor)s,
                        data_vencimento=%(data_vencimento)s, data_pagamento=%(data_pagamento)s,
                        status=%(status)s, fornecedor=%(fornecedor)s,
                        forma_pagamento=%(forma_pagamento)s, observacoes=%(observacoes)s
                    WHERE id=%(id)s
                """, {**campos, "id": id})
                conn.commit()
                flash("Despesa atualizada com sucesso!", "success")
                return redirect(url_for("financeiro.listar_despesas"))
            except Exception as e:
                conn.rollback()
                flash(f"Erro ao atualizar despesa: {e}", "danger")

    cur.execute("""
        SELECT id, categoria, descricao, valor, data_vencimento, data_pagamento,
               status, fornecedor, forma_pagamento, observacoes
        FROM despesas WHERE id=%s
    """, (id,))
    despesa = cur.fetchone()
    cur.close()
    conn.close()

    if not despesa:
        flash("Despesa não encontrada.", "warning")
        return redirect(url_for("financeiro.listar_despesas"))

    return render_template("editar_despesa.html", despesa=despesa, categorias=sorted(CATEGORIAS))


# ======================
# Despesas — excluir
# ======================
@financeiro_bp.route("/despesas/<int:id>/excluir", methods=["POST"])
@login_required
@requer_permissao(GERENCIAR_DESPESAS)
def excluir_despesa(id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM despesas WHERE id=%s", (id,))
        conn.commit()
        flash("Despesa excluída com sucesso!", "info")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao excluir despesa: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("financeiro.listar_despesas"))


# ======================
# Fluxo de caixa
# ======================
@financeiro_bp.route("/fluxo-caixa")
@login_required
@requer_permissao(VER_DESPESAS)
def fluxo_caixa():
    periodo = request.args.get("periodo") or "mes"
    data_inicio, data_fim = intervalo_periodo(periodo, request.args.get("inicio"), request.args.get("fim"))

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT b.data_pagamento AS data, b.valor_pago AS valor,
               COALESCE(b.descricao, 'Boleto locação #' || b.locacao_id) AS descricao
        FROM boletos b
        WHERE b.status IN ('RECEIVED', 'CONFIRMED', 'RECEIVED_IN_CASH')
          AND b.data_pagamento BETWEEN %s AND %s
    """, (data_inicio, data_fim))
    entradas = [{"data": r["data"], "valor": float(r["valor"] or 0), "descricao": r["descricao"], "tipo": "entrada"}
                for r in cur.fetchall()]

    cur.execute("""
        SELECT data_pagamento AS data, valor, descricao
        FROM despesas
        WHERE status = 'pago' AND data_pagamento BETWEEN %s AND %s
    """, (data_inicio, data_fim))
    saidas = [{"data": r["data"], "valor": float(r["valor"] or 0), "descricao": r["descricao"], "tipo": "saida"}
              for r in cur.fetchall()]

    cur.close()
    conn.close()

    movimentos = sorted(entradas + saidas, key=lambda m: m["data"] or dt.date.min)
    total_entradas = sum(m["valor"] for m in entradas)
    total_saidas = sum(m["valor"] for m in saidas)

    return render_template(
        "fluxo_caixa.html",
        movimentos=movimentos,
        total_entradas=total_entradas,
        total_saidas=total_saidas,
        saldo=total_entradas - total_saidas,
        periodo=periodo,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )


# ======================
# Dashboard financeiro
# ======================
@financeiro_bp.route("/")
@login_required
@requer_permissao(VER_DESPESAS)
def home():
    hoje = dt.date.today()
    primeiro_dia_mes, primeiro_dia_prox_mes = limites_mes(hoje)

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT COALESCE(SUM(COALESCE(valor_pago, 0)), 0) AS total
        FROM boletos
        WHERE status IN ('RECEIVED', 'CONFIRMED', 'RECEIVED_IN_CASH')
          AND data_pagamento >= %s AND data_pagamento < %s
    """, (primeiro_dia_mes, primeiro_dia_prox_mes))
    faturamento_mes = float(cur.fetchone()["total"])

    cur.execute("""
        SELECT COALESCE(SUM(valor), 0) AS total FROM boletos WHERE status IN ('PENDING', 'OVERDUE')
    """)
    valor_a_receber = float(cur.fetchone()["total"])

    cur.execute("""
        SELECT COALESCE(SUM(valor), 0) AS total FROM boletos
        WHERE status IN ('PENDING', 'OVERDUE')
          AND data_vencimento >= %s AND data_vencimento < %s
    """, (primeiro_dia_mes, primeiro_dia_prox_mes))
    a_receber_no_mes = float(cur.fetchone()["total"])

    cur.execute("""
        SELECT COALESCE(SUM(valor), 0) AS total FROM despesas
        WHERE data_vencimento >= %s AND data_vencimento < %s
    """, (primeiro_dia_mes, primeiro_dia_prox_mes))
    despesas_mes = float(cur.fetchone()["total"])

    cur.close()
    conn.close()

    saldo_projetado = faturamento_mes + a_receber_no_mes - despesas_mes

    return render_template(
        "financeiro.html",
        faturamento_mes=faturamento_mes,
        valor_a_receber=valor_a_receber,
        despesas_mes=despesas_mes,
        saldo_projetado=saldo_projetado,
    )


# ======================
# Configuração de multas por atraso — só super_admin/admin_locadora
# ======================
@financeiro_bp.route("/config-multas", methods=["GET", "POST"])
@login_required
@requer_role("super_admin", "admin_locadora")
def config_multas():
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        tipo = request.form.get("tipo")
        if tipo not in TIPOS_MULTA:
            cur.close()
            conn.close()
            flash("Tipo de multa inválido.", "warning")
            return redirect(url_for("financeiro.config_multas"))

        valor_fixo = request.form.get("valor_fixo") or None
        percentual = request.form.get("percentual") or None
        juros_dia_percentual = request.form.get("juros_dia_percentual") or None
        ativo = bool(request.form.get("ativo"))

        try:
            cur.execute("""
                INSERT INTO config_multas (company_id, tipo, valor_fixo, percentual, juros_dia_percentual, ativo)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (company_id) DO UPDATE SET
                    tipo = EXCLUDED.tipo,
                    valor_fixo = EXCLUDED.valor_fixo,
                    percentual = EXCLUDED.percentual,
                    juros_dia_percentual = EXCLUDED.juros_dia_percentual,
                    ativo = EXCLUDED.ativo
            """, (current_user.company_id, tipo, valor_fixo, percentual, juros_dia_percentual, ativo))
            conn.commit()
            flash("Configuração de multas salva com sucesso!", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao salvar configuração: {e}", "danger")
        finally:
            cur.close()
            conn.close()

        return redirect(url_for("financeiro.config_multas"))

    cur.execute("SELECT * FROM config_multas WHERE company_id=%s", (current_user.company_id,))
    config = cur.fetchone()
    cur.close()
    conn.close()
    return render_template("config_multas.html", config=config, tipos=TIPOS_MULTA)
