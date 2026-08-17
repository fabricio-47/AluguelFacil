import datetime as dt
import time
import requests
import psycopg2
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_from_directory, abort
from flask_login import login_required, current_user
from database import get_db_connection
from config import Config
import os

from permissions import requer_permissao, tem_permissao, VER_LOCACOES, CRIAR_LOCACAO, GERENCIAR_LOCACOES
from contrato import gerar_contrato_pdf
from multas import calcular_multa
from estoque import registrar_movimentacao
from assinaturas_core import salvar_assinatura, buscar_assinatura_recente

locacoes_bp = Blueprint("locacoes", __name__, url_prefix="/locacoes")

# ==== Listar locações ativas + Criar nova ====
@locacoes_bp.route("/", methods=["GET", "POST"])
@login_required
@requer_permissao(VER_LOCACOES)
def listar_locacoes():
    if request.method == "POST" and not tem_permissao(CRIAR_LOCACAO):
        flash("Você não tem permissão para criar locações.", "danger")
        return redirect(url_for("locacoes.listar_locacoes"))

    import traceback
    from psycopg2.extras import RealDictCursor

    breadcrumb = "inicio"

    if request.method == "GET":
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            # Locações ativas
            cur.execute("""
                SELECT l.id, c.nome AS cliente_nome, ei.modelo AS equipamento_modelo,
                ei.codigo_interno AS equipamento_codigo,
                l.data_inicio, l.data_fim, l.frequencia_pagamento,
                l.contrato_arquivo, l.boleto_url, l.pagamento_status, l.valor_pago
                FROM locacoes l
                JOIN clientes c ON c.id = l.cliente_id
                JOIN equipment_items ei ON ei.id = l.equipment_item_id
                WHERE l.cancelado = FALSE
                ORDER BY l.id DESC
            """)
            locacoes_rows = cur.fetchall()
            locacoes = [{
                "id": r["id"],
                "cliente_nome": r["cliente_nome"],
                "equipamento_modelo": r["equipamento_modelo"],
                "equipamento_codigo": r["equipamento_codigo"],
                "data_inicio": r["data_inicio"],
                "data_fim": r["data_fim"],
                "frequencia_pagamento": r["frequencia_pagamento"],
                "contrato_arquivo": r["contrato_arquivo"],
                "boleto_url": r["boleto_url"],
                "pagamento_status": r["pagamento_status"],
                "valor_pago": r["valor_pago"],
            } for r in locacoes_rows]

            # Clientes para o select
            cur.execute("SELECT id, nome FROM clientes ORDER BY nome ASC")
            clientes = [{"id": r["id"], "nome": r["nome"]} for r in cur.fetchall()]

            # Equipamentos disponíveis, com os preços por frequência pro cálculo automático no front-end
            cur.execute("""
                SELECT id, modelo, codigo_interno AS codigo, valor_semanal, valor_mensal
                FROM equipment_items
                WHERE status = 'disponivel' ORDER BY modelo ASC
            """)
            equipamentos = [{
                "id": r["id"], "modelo": r["modelo"], "codigo": r["codigo"],
                "valor_semanal": float(r["valor_semanal"]) if r["valor_semanal"] is not None else None,
                "valor_mensal": float(r["valor_mensal"]) if r["valor_mensal"] is not None else None,
            } for r in cur.fetchall()]

            return render_template("locacoes.html", locacoes=locacoes, clientes=clientes, equipamentos=equipamentos)
        finally:
            cur.close()
            conn.close()

    # POST: cria locação
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        breadcrumb = "validando_campos"
        cliente_id = request.form.get("cliente_id", type=int)
        equipamento_id = request.form.get("equipamento_id", type=int)
        data_inicio_str = (request.form.get("data_inicio") or "").strip()
        data_fim_str = (request.form.get("data_fim") or "").strip() or None
        observacoes = (request.form.get("observacoes") or "").strip() or None

        freq_in = (request.form.get("frequencia_pagamento") or "").strip().upper()
        mapping = {"SEMANAL": "WEEKLY", "MENSAL": "MONTHLY"}
        frequencia = mapping.get(freq_in, freq_in)

        if frequencia not in ("WEEKLY", "MONTHLY"):
            flash("Frequência inválida. Selecione semanal ou mensal.", "warning")
            return redirect(url_for("locacoes.listar_locacoes"))
        if not cliente_id or not equipamento_id:
            flash("Cliente e equipamento são obrigatórios.", "warning")
            return redirect(url_for("locacoes.listar_locacoes"))
        if not data_inicio_str:
            flash("Data de início é obrigatória.", "warning")
            return redirect(url_for("locacoes.listar_locacoes"))

        breadcrumb = "parse_datas"
        def parse_date_flexible(s):
            if s is None or s == "":
                return None
            s = s.strip()
            if "/" in s:  # dd/mm/aaaa
                return dt.datetime.strptime(s, "%d/%m/%Y").date()
            return dt.datetime.strptime(s, "%Y-%m-%d").date()  # yyyy-mm-dd

        data_inicio = parse_date_flexible(data_inicio_str)
        data_fim = parse_date_flexible(data_fim_str) if data_fim_str else None
        if data_fim and data_fim < data_inicio:
            flash("Data fim não pode ser anterior à data de início.", "warning")
            return redirect(url_for("locacoes.listar_locacoes"))

        breadcrumb = "buscar_cliente_equipamento"
        cur.execute("SELECT asaas_id, nome, cpf, endereco FROM clientes WHERE id=%s", (cliente_id,))
        cliente = cur.fetchone()
        if not cliente:
            flash("Cliente não encontrado.", "danger")
            return redirect(url_for("locacoes.listar_locacoes"))
        asaas_customer_id = cliente["asaas_id"]
        if not asaas_customer_id:
            flash("Cliente sem integração Asaas (asaas_id ausente).", "danger")
            return redirect(url_for("locacoes.listar_locacoes"))

        cur.execute("""
            SELECT nome, modelo, codigo_interno, status, valor_semanal, valor_mensal
            FROM equipment_items WHERE id=%s
        """, (equipamento_id,))
        equipamento = cur.fetchone()
        if not equipamento:
            flash("Equipamento não encontrado.", "danger")
            return redirect(url_for("locacoes.listar_locacoes"))
        if equipamento["status"] != "disponivel":
            flash("Equipamento indisponível para locação.", "warning")
            return redirect(url_for("locacoes.listar_locacoes"))

        breadcrumb = "calcular_valor"
        coluna_preco = "valor_semanal" if frequencia == "WEEKLY" else "valor_mensal"
        valor = equipamento[coluna_preco]
        if valor is None:
            freq_label = "semanal" if frequencia == "WEEKLY" else "mensal"
            flash(
                f"Este equipamento não tem preço cadastrado para locação {freq_label}. "
                f"Cadastre o preço no cadastro do equipamento antes de criar a locação.",
                "warning",
            )
            return redirect(url_for("locacoes.listar_locacoes"))
        valor = float(valor)

        breadcrumb = "validar_assinatura"
        assinatura_imagem = request.form.get("assinatura_imagem_contrato")
        nome_assinante = (request.form.get("nome_assinante_contrato") or "").strip()
        if not assinatura_imagem or not nome_assinante:
            flash("A assinatura do contrato é obrigatória para criar a locação.", "warning")
            return redirect(url_for("locacoes.listar_locacoes"))

        breadcrumb = "criar_locacao"
        try:
            locacao_id = criar_locacao_interna(
                cur, cliente, equipamento, cliente_id, equipamento_id,
                data_inicio, data_fim, frequencia, valor, observacoes,
                assinatura_dados={
                    "imagem_base64": assinatura_imagem,
                    "nome_assinante": nome_assinante,
                    "request": request,
                    "usuario_id": int(current_user.id),
                    "cliente_id": cliente_id,
                },
            )
        except AsaasError as e:
            flash(str(e), "danger")
            return redirect(url_for("locacoes.listar_locacoes"))

        conn.commit()
        flash("Locação criada, contrato gerado em PDF e assinatura recorrente configurada no Asaas! "
              "Preencha o checklist de entrega antes de liberar o equipamento.", "success")
        return redirect(url_for("checklists.novo", locacao_id=locacao_id, tipo="entrega"))

    except psycopg2.Error as e:
        conn.rollback()
        print("ERRO psycopg2 em", breadcrumb, "=>", e)
        traceback.print_exc()
        detalhe = getattr(e.diag, "message_detail", "")
        msg = detalhe or (e.pgerror or str(e))
        flash(f"Erro ao criar locação ({breadcrumb}): {msg}", "danger")
    except ValueError as e:
        conn.rollback()
        print("ERRO ValueError em", breadcrumb, "=>", e)
        traceback.print_exc()
        flash(f"Data/valor inválido ({breadcrumb}): {str(e)}", "danger")
    except Exception as e:
        conn.rollback()
        print("ERRO inesperado em", breadcrumb, "=>", e)
        traceback.print_exc()
        flash(f"Erro inesperado ao criar locação ({breadcrumb}): {repr(e)}", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("locacoes.listar_locacoes"))


class AsaasError(Exception):
    """Falha ao criar/consultar a assinatura no Asaas (ver mensagem para o motivo)."""
    pass


# ==== Criação de locação (reaproveitada pelo formulário manual acima e pela conversão de orçamento) ====
def criar_locacao_interna(cur, cliente, equipamento, cliente_id, equipamento_id,
                           data_inicio, data_fim, frequencia, valor, observacoes,
                           assinatura_dados=None):
    """
    Cria a assinatura no Asaas, grava a locação, atualiza o estoque do equipamento
    e gera o contrato em PDF. Não faz commit — quem chama controla a transação.
    Levanta AsaasError em vez de flash/redirect, para o chamador decidir o que fazer
    (ex.: seguir convertendo os próximos itens de um orçamento mesmo se este falhar).

    assinatura_dados, se informado, é um dict com imagem_base64/nome_assinante/request
    (mais usuario_id/cliente_id/motivo_substituicao/substitui_assinatura_id opcionais)
    — usado só pelo formulário manual (que já coleta a assinatura no canvas); a
    conversão de orçamento (bloco 6) não passa isso, e o contrato sai sem
    assinatura embutida nesse caso, como já era antes deste bloco.

    Retorna o id da locação criada.
    """
    if not getattr(Config, "ASAAS_API_KEY", None) or not getattr(Config, "ASAAS_BASE_URL", None):
        raise AsaasError("Configuração do Asaas ausente. Verifique ASAAS_API_KEY/ASAAS_BASE_URL.")

    asaas_customer_id = cliente["asaas_id"]
    if not asaas_customer_id:
        raise AsaasError("Cliente sem integração Asaas (asaas_id ausente).")

    modelo, placa = equipamento["modelo"], equipamento["codigo_interno"]

    subscription_data = {
        "customer": asaas_customer_id,
        "billingType": "BOLETO",
        "value": valor,
        "cycle": frequencia,  # 'WEEKLY' ou 'MONTHLY'
        "description": f"Locação moto {modelo} - {placa} ({cliente['nome']})",
        "nextDueDate": data_inicio.strftime("%Y-%m-%d"),
    }
    if data_fim:
        subscription_data["endDate"] = data_fim.strftime("%Y-%m-%d")

    try:
        resp = requests.post(
            f"{Config.ASAAS_BASE_URL}/subscriptions",
            headers={"access_token": Config.ASAAS_API_KEY},
            json=subscription_data,
            timeout=30,
        )
    except requests.RequestException as rexc:
        raise AsaasError(f"Falha de conexão com Asaas: {str(rexc)}") from rexc

    if resp.status_code not in (200, 201):
        body = resp.text if resp is not None else "<sem corpo>"
        raise AsaasError(f"Erro do Asaas ({resp.status_code}): {body}")

    asaas_subscription_id = resp.json().get("id")
    if not asaas_subscription_id:
        raise AsaasError("Resposta do Asaas não retornou id da assinatura.")

    cur.execute("""
        INSERT INTO locacoes (
            cliente_id, equipment_item_id, data_inicio, data_fim,
            valor, frequencia_pagamento, observacoes,
            asaas_subscription_id
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id, company_id, data_inicio, valor, frequencia_pagamento
    """, (
        cliente_id, equipamento_id, data_inicio, data_fim,
        valor, frequencia, observacoes,
        asaas_subscription_id,
    ))
    locacao_row = cur.fetchone()
    locacao_id = locacao_row["id"]

    cur.execute(
        "UPDATE equipment_items SET status='alugado', quantidade_disponivel=0 WHERE id=%s",
        (equipamento_id,),
    )
    registrar_movimentacao(cur, equipamento_id, "saida", f"Locação #{locacao_id} criada", int(current_user.id))

    cur.execute("SELECT nome, cnpj FROM companies WHERE id=%s", (locacao_row["company_id"],))
    company = cur.fetchone()

    assinatura_pdf = None
    if assinatura_dados:
        assinatura_id = salvar_assinatura(
            cur,
            upload_folder=current_app.config["UPLOAD_FOLDER"],
            company_id=locacao_row["company_id"],
            tipo_documento="contrato",
            documento_id=locacao_id,
            imagem_base64=assinatura_dados["imagem_base64"],
            nome_assinante=assinatura_dados["nome_assinante"],
            request=assinatura_dados["request"],
            usuario_id=assinatura_dados.get("usuario_id"),
            cliente_id=assinatura_dados.get("cliente_id"),
            motivo_substituicao=assinatura_dados.get("motivo_substituicao"),
            substitui_assinatura_id=assinatura_dados.get("substitui_assinatura_id"),
        )
        cur.execute("SELECT * FROM assinaturas WHERE id=%s", (assinatura_id,))
        assinatura_row = cur.fetchone()
        # imagem_base64 já vem como data-URL completa (canvas.toDataURL()),
        # reaproveitada direto no <img src="..."> do PDF.
        assinatura_pdf = {
            "imagem_data_uri": assinatura_dados["imagem_base64"],
            "nome_assinante": assinatura_row["nome_assinante"],
            "data_hora": assinatura_row["data_hora"].strftime("%d/%m/%Y %H:%M"),
            "ip_address": assinatura_row["ip_address"],
        }

    pdf_bytes = gerar_contrato_pdf(locacao_row, cliente, equipamento, company, assinatura=assinatura_pdf)
    pasta_contratos = os.path.join(current_app.config["UPLOAD_FOLDER"], "contratos")
    os.makedirs(pasta_contratos, exist_ok=True)
    contrato_filename = f"contrato_{locacao_id}_{int(time.time() * 1000)}.pdf"
    with open(os.path.join(pasta_contratos, contrato_filename), "wb") as f:
        f.write(pdf_bytes)

    cur.execute("UPDATE locacoes SET contrato_arquivo=%s WHERE id=%s", (contrato_filename, locacao_id))

    return locacao_id


# ==== Editar locação + listar boletos ====
@locacoes_bp.route("/<int:id>/editar", methods=["GET", "POST"])
@login_required
@requer_permissao(GERENCIAR_LOCACOES)
def editar_locacao(id):
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        data_inicio = request.form["data_inicio"]
        data_fim = request.form.get("data_fim") or None
        valor = request.form["valor"]
        frequencia = request.form["frequencia_pagamento"]
        observacoes = request.form.get("observacoes")

        try:
            cur.execute("""
                UPDATE locacoes SET data_inicio=%s, data_fim=%s, valor=%s,
                frequencia_pagamento=%s, observacoes=%s WHERE id=%s
            """, (data_inicio, data_fim, valor, frequencia, observacoes, id))

            cur.execute("SELECT asaas_subscription_id FROM locacoes WHERE id=%s", (id,))
            row = cur.fetchone()
            asaas_subscription_id = row[0] if row else None

            if asaas_subscription_id:
                patch_data = {"value": float(valor), "cycle": frequencia}
                if data_inicio:
                    patch_data["nextDueDate"] = data_inicio
                if data_fim:
                    patch_data["endDate"] = data_fim

                resp = requests.post(
                    f"{Config.ASAAS_BASE_URL}/subscriptions/{asaas_subscription_id}",
                    headers={"access_token": Config.ASAAS_API_KEY},
                    json=patch_data,
                    timeout=30
                )
                if resp.status_code not in (200, 201):
                    resp = requests.put(
                        f"{Config.ASAAS_BASE_URL}/subscriptions/{asaas_subscription_id}",
                        headers={"access_token": Config.ASAAS_API_KEY},
                        json=patch_data,
                        timeout=30
                    )
                if resp.status_code not in (200, 201):
                    flash(f"Locação atualizada, mas falhou no Asaas: {resp.text}", "warning")
                else:
                    flash("Locação e assinatura atualizadas!", "success")
            else:
                flash("Locação e assinatura atualizadas!", "success")
        except Exception as e:
            flash(f"Erro ao atualizar locação: {e}", "danger")

        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for("locacoes.editar_locacao", id=id))

    # Método GET: buscar dados para exibir no formulário
    cur.execute("""
        SELECT id, cliente_id, moto_id, equipment_item_id, company_id, cancelado,
        data_inicio, data_fim, valor, frequencia_pagamento, observacoes, asaas_subscription_id
        FROM locacoes WHERE id=%s
    """, (id,))
    locacao = cur.fetchone()

    cur.execute("""
        SELECT id, asaas_payment_id, status, valor, valor_pago, boleto_url,
        descricao, data_vencimento, data_pagamento
        FROM boletos WHERE locacao_id=%s
        ORDER BY data_vencimento DESC NULLS LAST, id DESC
    """, (id,))
    boletos = cur.fetchall()

    multa = None
    if locacao:
        if locacao["cancelado"]:
            cur.execute(
                "SELECT dias_atraso_final, valor_multa_final FROM checklists WHERE locacao_id=%s AND tipo='devolucao'",
                (id,),
            )
            checklist_devolucao = cur.fetchone()
            if checklist_devolucao and checklist_devolucao["dias_atraso_final"]:
                multa = {
                    "dias_atraso": checklist_devolucao["dias_atraso_final"],
                    "valor_multa_total": float(checklist_devolucao["valor_multa_final"] or 0),
                    "final": True,
                }
        else:
            cur.execute("SELECT valor_diaria FROM equipment_items WHERE id=%s", (locacao["equipment_item_id"],))
            equipamento = cur.fetchone()
            cur.execute("SELECT * FROM config_multas WHERE company_id=%s", (locacao["company_id"],))
            config = cur.fetchone()
            calculo = calcular_multa(
                locacao["data_fim"], dt.date.today(), locacao["valor"],
                equipamento["valor_diaria"] if equipamento else None, config,
            )
            if calculo["dias_atraso"] > 0:
                calculo["final"] = False
                multa = calculo

    assinatura_contrato = None
    if locacao:
        assinatura_contrato = buscar_assinatura_recente(cur, "contrato", id)

    cur.close()
    conn.close()
    return render_template(
        "editar_locacao.html", locacao=locacao, boletos=boletos, multa=multa,
        assinatura_contrato=assinatura_contrato,
    )

# ==== Listar locações canceladas ====
@locacoes_bp.route("/canceladas")
@login_required
@requer_permissao(GERENCIAR_LOCACOES)
def canceladas():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT l.id, l.data_inicio, l.data_fim, l.valor, l.frequencia_pagamento,
        l.pagamento_status, l.valor_pago, l.asaas_subscription_id, l.boleto_url,
        c.nome AS cliente_nome, ei.modelo AS moto_modelo, ei.codigo_interno AS moto_placa
        FROM locacoes l
        JOIN clientes c ON l.cliente_id = c.id
        JOIN equipment_items ei ON l.equipment_item_id = ei.id
        WHERE l.cancelado = TRUE
        ORDER BY l.data_inicio DESC
    """)
    locacoes = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("locacoes_canceladas.html", locacoes=locacoes)

# ==== Lógica de cancelamento (reaproveitada por cancelar_locacao e pelo checklist de devolução) ====
def executar_cancelamento_locacao(cur, locacao_id, equipamento_id, asaas_subscription_id):
    """Cancela a assinatura no Asaas (se existir) e libera o equipamento. Não faz commit — quem chama controla a transação."""
    if asaas_subscription_id:
        resp = requests.post(
            f"{Config.ASAAS_BASE_URL}/subscriptions/{asaas_subscription_id}/cancel",
            headers={"access_token": Config.ASAAS_API_KEY},
            timeout=30
        )
        if resp.status_code not in (200, 201):
            flash(f"Falha ao cancelar assinatura no Asaas: {resp.text}", "warning")

    hoje = dt.date.today().strftime("%Y-%m-%d")
    cur.execute("UPDATE locacoes SET cancelado=TRUE, data_fim=%s WHERE id=%s", (hoje, locacao_id))
    registrar_movimentacao(cur, equipamento_id, "entrada", f"Locação #{locacao_id} finalizada", int(current_user.id))
    cur.execute(
        "UPDATE equipment_items SET status='disponivel', quantidade_disponivel=1 WHERE id=%s",
        (equipamento_id,),
    )


# ==== Cancelar locação específica ====
@locacoes_bp.route("/<int:id>/cancelar", methods=["POST"])
@login_required
@requer_permissao(GERENCIAR_LOCACOES)
def cancelar_locacao(id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM checklists WHERE locacao_id=%s AND tipo='devolucao'", (id,))
        if not cur.fetchone():
            flash("Preencha o checklist de devolução antes de finalizar esta locação.", "warning")
            return redirect(url_for("checklists.novo", locacao_id=id, tipo="devolucao"))

        cur.execute("SELECT asaas_subscription_id, equipment_item_id FROM locacoes WHERE id=%s", (id,))
        row = cur.fetchone()
        if not row:
            flash("Locação não encontrada.", "danger")
            return redirect(url_for("locacoes.listar_locacoes"))

        if isinstance(row, dict):
            asaas_subscription_id = row.get("asaas_subscription_id")
            equipamento_id = row.get("equipment_item_id")
        else:
            asaas_subscription_id = row[0]
            equipamento_id = row[1]

        executar_cancelamento_locacao(cur, id, equipamento_id, asaas_subscription_id)
        conn.commit()
        flash("Locação cancelada!", "info")

    except psycopg2.Error as e:
        conn.rollback()
        motivo = e.pgerror or str(e)
        detalhe = getattr(e.diag, "message_detail", "")
        if detalhe:
            flash(f"Erro ao cancelar locação: {detalhe}", "danger")
        else:
            flash(f"Erro ao cancelar locação: {motivo}", "danger")

    except Exception as e:
        conn.rollback()
        print(f"Erro inesperado ao cancelar locação: {repr(e)} (tipo: {type(e)})")
        flash(f"Erro inesperado ao cancelar locação: {repr(e)}", "danger")

    finally:
        cur.close()
        conn.close()
    return redirect(url_for("locacoes.listar_locacoes"))

# ==== Sincronizar boletos manualmente ====
@locacoes_bp.route("/<int:id>/sincronizar_boletos", methods=["GET"])
@login_required
@requer_permissao(GERENCIAR_LOCACOES)
def sincronizar_boletos_manual(id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT asaas_subscription_id FROM locacoes WHERE id=%s", (id,))
        row = cur.fetchone()
        if not row or not row[0]:
            flash("Assinatura Asaas não vinculada à locação.", "warning")
            return redirect(url_for("locacoes.editar_locacao", id=id))

        sub_id = row[0]
        url = f"{Config.ASAAS_BASE_URL}/payments?subscription={sub_id}&limit=100"
        resp = requests.get(url, headers={"access_token": Config.ASAAS_API_KEY}, timeout=30)
        if resp.status_code not in (200, 201):
            flash(f"Erro ao consultar boletos no Asaas: {resp.text}", "danger")
            return redirect(url_for("locacoes.editar_locacao", id=id))

        data = resp.json()
        items = data.get("data", []) if isinstance(data, dict) else []

        inseridos, atualizados = 0, 0
        for p in items:
            asaas_payment_id = p.get("id")
            status = p.get("status")
            valor = p.get("value")
            net_value = p.get("netValue")
            boleto_url = p.get("bankSlipUrl")
            descricao = p.get("description")
            due_date = p.get("dueDate")
            payment_date = p.get("paymentDate")

            cur.execute("SELECT id FROM boletos WHERE asaas_payment_id=%s", (asaas_payment_id,))
            existe = cur.fetchone()
            if existe:
                cur.execute("""
                    UPDATE boletos
                    SET status=%s, valor=%s, valor_pago=%s, boleto_url=%s,
                    descricao=%s, data_vencimento=%s, data_pagamento=%s
                    WHERE asaas_payment_id=%s
                """, (status, valor, net_value, boleto_url,
                      descricao, due_date, payment_date, asaas_payment_id))
                atualizados += 1
            else:
                cur.execute("""
                    INSERT INTO boletos (locacao_id, asaas_payment_id, status, valor,
                    valor_pago, boleto_url, descricao,
                    data_vencimento, data_pagamento)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (id, asaas_payment_id, status, valor, net_value,
                      boleto_url, descricao, due_date, payment_date))
                inseridos += 1

        conn.commit()
        flash(f"Boletos sincronizados! Inseridos: {inseridos}, Atualizados: {atualizados}.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao sincronizar boletos: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("locacoes.editar_locacao", id=id))


# ==== Servir PDF de contratos ====
@locacoes_bp.route("/contrato/<int:locacao_id>/pdf")
@login_required
@requer_permissao(VER_LOCACOES)
def contrato_pdf(locacao_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT contrato_arquivo FROM locacoes WHERE id = %s", (locacao_id,))
        result = cur.fetchone()
        if not result or not result["contrato_arquivo"]:
            flash("Contrato não encontrado.", "warning")
            return redirect(url_for("locacoes.listar_locacoes"))
        contrato_arquivo = result["contrato_arquivo"]

        uploads_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], "contratos")
        return send_from_directory(directory=uploads_dir, path=contrato_arquivo)
    finally:
        cur.close()
        conn.close()