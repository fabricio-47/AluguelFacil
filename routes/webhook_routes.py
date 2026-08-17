import json
from flask import Blueprint, request, abort, Request
from database import get_db_connection
from asaas_config import todos_webhook_secrets_validos

webhook_bp = Blueprint("webhook", __name__, url_prefix="/webhook")

def _authorized(req: Request, cur):
    """Retorna (autorizado: bool, company_id: int|None). company_id é o dono
    do secret que autorizou (None se autorizado pelo secret global, sem
    escopo de empresa, ou se não autorizado)."""
    secrets_validos = todos_webhook_secrets_validos(cur)
    if not secrets_validos:
        return True, None
    hdrs = {k.lower(): v for k, v in req.headers.items()}
    token = hdrs.get("x-webhook-token") or hdrs.get("asaas-webhook-token") or hdrs.get("authorization")
    if token not in secrets_validos:
        return False, None
    return True, secrets_validos[token]

@webhook_bp.route("/asaas", methods=["POST"])
def asaas_webhook():
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        autorizado, webhook_company_id = _authorized(request, cur)
        if not autorizado:
            abort(401)

        try:
            data = request.get_json(force=True, silent=True) or {}
        except Exception:
            abort(400)

        event = data.get("event")
        payment = data.get("payment") or {}

        try:
            if event in ("PAYMENT_CREATED", "PAYMENT_UPDATED"):
                _upsert_boleto(cur, payment, webhook_company_id)

            elif event in ("PAYMENT_CONFIRMED", "PAYMENT_RECEIVED", "PAYMENT_RECEIVED_IN_CASH"):
                _upsert_boleto(cur, payment, webhook_company_id)
                _atualizar_agregado_locacao(cur, payment, webhook_company_id)

            elif event in ("PAYMENT_OVERDUE", "PAYMENT_DELETED", "PAYMENT_CANCELED"):
                _upsert_boleto(cur, payment, webhook_company_id)
                _atualizar_agregado_locacao(cur, payment, webhook_company_id)

            conn.commit()
        except Exception as e:
            conn.rollback()
            # Retornar 200 para Asaas não reenfileirar eternamente, mas logue em produção:
            return {"ok": False, "error": str(e)}, 200
    finally:
        cur.close()
        conn.close()

    return {"ok": True}, 200

def _upsert_boleto(cur, p, company_id=None):
    asaas_payment_id = p.get("id")
    status = p.get("status")
    valor = p.get("value")
    net_value = p.get("netValue")
    boleto_url = p.get("bankSlipUrl")
    descricao = p.get("description")
    due_date = p.get("dueDate")
    payment_date = p.get("paymentDate")
    subscription_id = p.get("subscription")

    # Relacionar com locação pela assinatura — escopado por empresa quando o
    # secret que autorizou o webhook pertence a uma empresa específica (evita
    # que a empresa A escreva num payment de assinatura da empresa B).
    query = "SELECT id FROM locacoes WHERE asaas_subscription_id=%s"
    params = [subscription_id]
    if company_id is not None:
        query += " AND company_id=%s"
        params.append(company_id)
    cur.execute(query, tuple(params))
    row = cur.fetchone()
    locacao_id = row["id"] if row else None

    # Upsert
    cur.execute("SELECT id FROM boletos WHERE asaas_payment_id=%s", (asaas_payment_id,))
    exists = cur.fetchone()
    if exists:
        cur.execute("""
            UPDATE boletos
               SET status=%s, valor=%s, valor_pago=%s, boleto_url=%s, descricao=%s,
                   data_vencimento=%s, data_pagamento=%s
             WHERE asaas_payment_id=%s
        """, (status, valor, net_value, boleto_url, descricao, due_date, payment_date, asaas_payment_id))
    else:
        cur.execute("""
            INSERT INTO boletos (locacao_id, asaas_payment_id, status, valor, valor_pago,
                                 boleto_url, descricao, data_vencimento, data_pagamento)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (locacao_id, asaas_payment_id, status, valor, net_value, boleto_url, descricao, due_date, payment_date))

def _atualizar_agregado_locacao(cur, p, company_id=None):
    # Recalcula status agregado da locação com base nos boletos
    subscription_id = p.get("subscription")
    if not subscription_id:
        return
    query = "SELECT id FROM locacoes WHERE asaas_subscription_id=%s"
    params = [subscription_id]
    if company_id is not None:
        query += " AND company_id=%s"
        params.append(company_id)
    cur.execute(query, tuple(params))
    row = cur.fetchone()
    if not row:
        return
    locacao_id = row["id"]

    # Somatório valor pago e status mais recente
    cur.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN status IN ('RECEIVED','CONFIRMED','RECEIVED_IN_CASH') THEN COALESCE(valor_pago,0) ELSE 0 END),0) AS total_pago,
            MAX(data_pagamento) AS ultima_data_pagto
        FROM boletos
        WHERE locacao_id=%s
    """, (locacao_id,))
    agg = cur.fetchone()
    total_pago = agg["total_pago"] if agg else 0

    # Atualiza campos agregados (se você tiver colunas pagamento_status/valor_pago na locações)
    try:
        cur.execute("""
            UPDATE locacoes
               SET valor_pago=%s
             WHERE id=%s
        """, (total_pago, locacao_id))
    except Exception:
        # Se a coluna não existir, ignore silenciosamente
        pass
