import datetime as dt

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from psycopg2.extras import RealDictCursor

from database import get_db_connection
from permissions import requer_permissao, tem_permissao, tem_role, VER_ORCAMENTOS, GERENCIAR_ORCAMENTOS
from routes.locacoes_routes import criar_locacao_interna, AsaasError, ComprovanteDesatualizadoError

orcamentos_bp = Blueprint("orcamentos", __name__, url_prefix="/orcamentos")


def _pode_ver_todos():
    return not tem_role("atendente", "vendedor")


def _acessa_orcamento(orcamento):
    """Atendente/vendedor só acessam orçamentos que eles mesmos criaram."""
    if _pode_ver_todos():
        return True
    return orcamento["criado_por"] == int(current_user.id)


# ==== Listar + criar ====
@orcamentos_bp.route("/", methods=["GET", "POST"])
@login_required
@requer_permissao(VER_ORCAMENTOS)
def listar_orcamentos():
    if request.method == "POST":
        if not tem_permissao(GERENCIAR_ORCAMENTOS):
            flash("Você não tem permissão para criar orçamentos.", "danger")
            return redirect(url_for("orcamentos.listar_orcamentos"))

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cliente_id = request.form.get("cliente_id", type=int)
            frete = request.form.get("frete", type=float) or 0
            validade = request.form.get("validade") or None
            observacoes = (request.form.get("observacoes") or "").strip() or None

            equipamento_ids = request.form.getlist("item_equipamento_id")
            quantidades = request.form.getlist("item_quantidade")
            periodos = request.form.getlist("item_periodo_dias")
            frequencias = request.form.getlist("item_frequencia_pagamento")
            valores_unitarios = request.form.getlist("item_valor_unitario")
            descontos = request.form.getlist("item_desconto")

            if not cliente_id:
                flash("Selecione um cliente.", "warning")
                return redirect(url_for("orcamentos.listar_orcamentos"))
            if not equipamento_ids:
                flash("Adicione ao menos um item ao orçamento.", "warning")
                return redirect(url_for("orcamentos.listar_orcamentos"))

            itens = []
            valor_total = frete
            for i, equip_id in enumerate(equipamento_ids):
                if not equip_id:
                    continue
                quantidade = int(quantidades[i] or 1)
                periodo_dias = int(periodos[i]) if periodos[i] else None
                frequencia = (frequencias[i] or "").strip().upper() or None
                if frequencia not in (None, "WEEKLY", "MONTHLY"):
                    flash("Frequência de pagamento inválida em um dos itens.", "warning")
                    return redirect(url_for("orcamentos.listar_orcamentos"))
                valor_unitario = float(valores_unitarios[i] or 0)
                desconto = float(descontos[i] or 0)

                item_total = (valor_unitario * quantidade) - desconto
                valor_total += item_total
                itens.append((int(equip_id), quantidade, periodo_dias, frequencia, valor_unitario, desconto))

            if not itens:
                flash("Adicione ao menos um item ao orçamento.", "warning")
                return redirect(url_for("orcamentos.listar_orcamentos"))

            cur.execute("""
                INSERT INTO orcamentos (cliente_id, criado_por, frete, valor_total, validade, observacoes)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (cliente_id, int(current_user.id), frete, valor_total, validade, observacoes))
            orcamento_id = cur.fetchone()["id"]

            for equip_id, quantidade, periodo_dias, frequencia, valor_unitario, desconto in itens:
                cur.execute("""
                    INSERT INTO orcamento_itens (
                        orcamento_id, equipment_item_id, quantidade, periodo_dias,
                        frequencia_pagamento, valor_unitario, desconto
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (orcamento_id, equip_id, quantidade, periodo_dias, frequencia, valor_unitario, desconto))

            conn.commit()
            flash("Orçamento criado com sucesso.", "success")
            return redirect(url_for("orcamentos.detalhe_orcamento", id=orcamento_id))

        except Exception as e:
            conn.rollback()
            print("Erro ao criar orçamento:", e)
            flash(f"Erro ao criar orçamento: {e}", "danger")
            return redirect(url_for("orcamentos.listar_orcamentos"))
        finally:
            cur.close()
            conn.close()

    # GET
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        if _pode_ver_todos():
            cur.execute("""
                SELECT o.id, o.status, o.valor_total, o.validade, o.created_at,
                       c.nome AS cliente_nome, u.username AS criado_por_nome
                FROM orcamentos o
                JOIN clientes c ON c.id = o.cliente_id
                LEFT JOIN usuarios u ON u.id = o.criado_por
                ORDER BY o.id DESC
            """)
        else:
            cur.execute("""
                SELECT o.id, o.status, o.valor_total, o.validade, o.created_at,
                       c.nome AS cliente_nome, u.username AS criado_por_nome
                FROM orcamentos o
                JOIN clientes c ON c.id = o.cliente_id
                LEFT JOIN usuarios u ON u.id = o.criado_por
                WHERE o.criado_por = %s
                ORDER BY o.id DESC
            """, (int(current_user.id),))
        orcamentos = cur.fetchall()

        cur.execute("SELECT id, nome FROM clientes ORDER BY nome ASC")
        clientes = cur.fetchall()

        cur.execute("""
            SELECT id, nome, modelo, codigo_interno, valor_diaria, valor_semanal, valor_mensal
            FROM equipment_items WHERE status != 'inativo' ORDER BY nome ASC
        """)
        equipamentos = [{
            "id": r["id"], "nome": r["nome"], "modelo": r["modelo"], "codigo_interno": r["codigo_interno"],
            "valor_diaria": float(r["valor_diaria"]) if r["valor_diaria"] is not None else None,
            "valor_semanal": float(r["valor_semanal"]) if r["valor_semanal"] is not None else None,
            "valor_mensal": float(r["valor_mensal"]) if r["valor_mensal"] is not None else None,
        } for r in cur.fetchall()]

        return render_template(
            "orcamentos.html", orcamentos=orcamentos, clientes=clientes, equipamentos=equipamentos,
        )
    finally:
        cur.close()
        conn.close()


# ==== Detalhe ====
@orcamentos_bp.route("/<int:id>")
@login_required
@requer_permissao(VER_ORCAMENTOS)
def detalhe_orcamento(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT o.*, c.nome AS cliente_nome, u.username AS criado_por_nome
            FROM orcamentos o
            JOIN clientes c ON c.id = o.cliente_id
            LEFT JOIN usuarios u ON u.id = o.criado_por
            WHERE o.id = %s
        """, (id,))
        orcamento = cur.fetchone()
        if not orcamento:
            flash("Orçamento não encontrado.", "warning")
            return redirect(url_for("orcamentos.listar_orcamentos"))

        if not _acessa_orcamento(orcamento):
            flash("Você não tem acesso a este orçamento.", "danger")
            return redirect(url_for("orcamentos.listar_orcamentos"))

        cur.execute("""
            SELECT oi.*, ei.nome AS equipamento_nome, ei.modelo AS equipamento_modelo,
                   ei.codigo_interno AS equipamento_codigo
            FROM orcamento_itens oi
            JOIN equipment_items ei ON ei.id = oi.equipment_item_id
            WHERE oi.orcamento_id = %s
            ORDER BY oi.id ASC
        """, (id,))
        itens = cur.fetchall()

        return render_template(
            "orcamento_detalhe.html", orcamento=orcamento, itens=itens,
            pode_gerenciar=tem_permissao(GERENCIAR_ORCAMENTOS),
        )
    finally:
        cur.close()
        conn.close()


# ==== Mudar status (enviado/visualizado/recusado) ====
@orcamentos_bp.route("/<int:id>/status", methods=["POST"])
@login_required
@requer_permissao(GERENCIAR_ORCAMENTOS)
def mudar_status_orcamento(id):
    novo_status = (request.form.get("status") or "").strip()
    if novo_status not in ("enviado", "visualizado", "recusado"):
        flash("Status inválido.", "warning")
        return redirect(url_for("orcamentos.detalhe_orcamento", id=id))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT criado_por FROM orcamentos WHERE id=%s", (id,))
        orcamento = cur.fetchone()
        if not orcamento:
            flash("Orçamento não encontrado.", "warning")
            return redirect(url_for("orcamentos.listar_orcamentos"))
        if not _acessa_orcamento(orcamento):
            flash("Você não tem acesso a este orçamento.", "danger")
            return redirect(url_for("orcamentos.listar_orcamentos"))

        cur.execute("UPDATE orcamentos SET status=%s WHERE id=%s", (novo_status, id))
        conn.commit()
        flash("Status do orçamento atualizado.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao atualizar status: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("orcamentos.detalhe_orcamento", id=id))


# ==== Aprovar e converter em locação(ões) ====
@orcamentos_bp.route("/<int:id>/converter", methods=["POST"])
@login_required
@requer_permissao(GERENCIAR_ORCAMENTOS)
def converter_orcamento(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM orcamentos WHERE id=%s", (id,))
        orcamento = cur.fetchone()
        if not orcamento:
            flash("Orçamento não encontrado.", "warning")
            return redirect(url_for("orcamentos.listar_orcamentos"))
        if not _acessa_orcamento(orcamento):
            flash("Você não tem acesso a este orçamento.", "danger")
            return redirect(url_for("orcamentos.listar_orcamentos"))

        if orcamento["status"] != "aprovado":
            cur.execute("UPDATE orcamentos SET status='aprovado' WHERE id=%s", (id,))
            conn.commit()

        cur.execute("SELECT asaas_id, nome, cpf, endereco FROM clientes WHERE id=%s", (orcamento["cliente_id"],))
        cliente = cur.fetchone()
        if not cliente:
            flash("Cliente do orçamento não encontrado.", "danger")
            return redirect(url_for("orcamentos.detalhe_orcamento", id=id))

        cur.execute("SELECT * FROM orcamento_itens WHERE orcamento_id=%s AND locacao_id IS NULL", (id,))
        itens_pendentes = cur.fetchall()

        if not itens_pendentes:
            flash("Não há itens pendentes de conversão neste orçamento.", "info")
            return redirect(url_for("orcamentos.detalhe_orcamento", id=id))

        convertidos = 0
        falhas = []

        for item in itens_pendentes:
            try:
                cur.execute("""
                    SELECT nome, modelo, codigo_interno, status, valor_semanal, valor_mensal
                    FROM equipment_items WHERE id=%s
                """, (item["equipment_item_id"],))
                equipamento = cur.fetchone()
                if not equipamento:
                    raise ValueError("Equipamento não encontrado.")
                if equipamento["status"] != "disponivel":
                    raise ValueError(f"Equipamento {equipamento['modelo'] or equipamento['nome']} indisponível.")
                if item["frequencia_pagamento"] not in ("WEEKLY", "MONTHLY"):
                    raise ValueError("Item sem frequência de pagamento válida (semanal/mensal).")

                data_inicio = dt.date.today()
                data_fim = data_inicio + dt.timedelta(days=item["periodo_dias"]) if item["periodo_dias"] else None
                valor_item = (float(item["valor_unitario"]) * item["quantidade"]) - float(item["desconto"] or 0)
                observacoes = f"Convertido do orçamento #{id}."
                if orcamento["frete"]:
                    observacoes += f" Frete do orçamento: R$ {float(orcamento['frete']):.2f} (cobrança avulsa, fora do Asaas)."

                locacao_id = criar_locacao_interna(
                    cur, cliente, equipamento, orcamento["cliente_id"], item["equipment_item_id"],
                    data_inicio, data_fim, item["frequencia_pagamento"], valor_item, observacoes,
                )
                cur.execute("UPDATE orcamento_itens SET locacao_id=%s WHERE id=%s", (locacao_id, item["id"]))
                conn.commit()
                convertidos += 1

            except (ValueError, AsaasError, ComprovanteDesatualizadoError) as e:
                conn.rollback()
                falhas.append(f"item #{item['id']} ({item['equipment_item_id']}): {e}")
            except Exception as e:
                conn.rollback()
                falhas.append(f"item #{item['id']} ({item['equipment_item_id']}): erro inesperado — {e}")

        if convertidos:
            cur.execute("SELECT COUNT(*) AS total FROM locacoes WHERE cliente_id=%s", (orcamento["cliente_id"],))
            total_locacoes = cur.fetchone()["total"]
            etapa = "locacao" if total_locacoes <= 1 else "cliente_recorrente"
            cur.execute("""
                INSERT INTO pipeline_clientes (cliente_id, etapa, usuario_responsavel)
                VALUES (%s, %s, %s)
                ON CONFLICT (cliente_id) DO UPDATE SET etapa=EXCLUDED.etapa, atualizado_em=CURRENT_TIMESTAMP
            """, (orcamento["cliente_id"], etapa, int(current_user.id)))
            conn.commit()

        total_itens = convertidos + len(falhas)
        if not falhas:
            flash(f"{convertidos} de {total_itens} item(ns) convertido(s) em locação com sucesso.", "success")
        elif convertidos:
            flash(
                f"{convertidos} de {total_itens} item(ns) convertidos em locação. "
                f"Falharam: {' | '.join(falhas)}. Tente novamente só o(s) item(ns) que falhou(aram).",
                "warning",
            )
        else:
            flash(f"Nenhum item convertido. Falharam: {' | '.join(falhas)}", "danger")

    finally:
        cur.close()
        conn.close()

    return redirect(url_for("orcamentos.detalhe_orcamento", id=id))
