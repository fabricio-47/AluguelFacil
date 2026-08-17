import datetime as dt
from flask import Blueprint, render_template
from flask_login import login_required, current_user
from database import get_db_connection
from permissions import requer_permissao, VER_DASHBOARD_FINANCEIRO

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/")
@login_required
@requer_permissao(VER_DASHBOARD_FINANCEIRO)
def home():
    hoje = dt.date.today()
    primeiro_dia_mes = hoje.replace(day=1)
    company_id = current_user.company_id

    conn = get_db_connection()
    cur = conn.cursor()

    # Função auxiliar para extrair valor do cursor (dict ou tupla)
    def get_count(cursor_result):
        if cursor_result is None:
            return 0
        if isinstance(cursor_result, dict):
            return cursor_result.get('count', 0) or 0
        return cursor_result[0] if cursor_result else 0

    # Contagens básicas (tudo escopado pra company_id do usuário logado)
    cur.execute("SELECT COUNT(*) AS count FROM clientes WHERE company_id=%s", (company_id,))
    total_clientes = get_count(cur.fetchone())

    cur.execute("SELECT COUNT(*) AS count FROM equipment_items WHERE company_id=%s", (company_id,))
    total_motos = get_count(cur.fetchone())

    cur.execute("SELECT COUNT(*) AS count FROM locacoes WHERE company_id=%s AND cancelado=FALSE", (company_id,))
    locacoes_ativas = get_count(cur.fetchone())

    cur.execute("SELECT COUNT(*) AS count FROM locacoes WHERE company_id=%s AND cancelado=TRUE", (company_id,))
    locacoes_canceladas = get_count(cur.fetchone())

    # Boletos pendentes e pagos (boletos não tem company_id direto — via locacoes)
    cur.execute("""
        SELECT COUNT(*) AS count FROM boletos b
        JOIN locacoes l ON l.id = b.locacao_id
        WHERE l.company_id=%s AND b.status IN ('PENDING','OVERDUE')
    """, (company_id,))
    boletos_pendentes = get_count(cur.fetchone())

    cur.execute("""
        SELECT COUNT(*) AS count FROM boletos b
        JOIN locacoes l ON l.id = b.locacao_id
        WHERE l.company_id=%s AND b.status IN ('RECEIVED','CONFIRMED','RECEIVED_IN_CASH')
    """, (company_id,))
    boletos_pagados = get_count(cur.fetchone())

    # Receita do mês (somatório dos pagos no mês atual)
    cur.execute("""
        SELECT COALESCE(SUM(COALESCE(b.valor_pago,0)),0) AS receita
        FROM boletos b
        JOIN locacoes l ON l.id = b.locacao_id
        WHERE l.company_id=%s AND b.status IN ('RECEIVED','CONFIRMED','RECEIVED_IN_CASH')
          AND b.data_pagamento >= %s
          AND b.data_pagamento < %s
    """, (company_id, primeiro_dia_mes, (primeiro_dia_mes.replace(day=28) + dt.timedelta(days=4)).replace(day=1)))

    result = cur.fetchone()
    if isinstance(result, dict):
        receita_mes = result.get('receita', 0) or 0
    else:
        receita_mes = result[0] if result else 0

    # Inadimplentes (boletos vencidos sem pagamento)
    cur.execute("""
        SELECT COUNT(*) AS count FROM boletos b
        JOIN locacoes l ON l.id = b.locacao_id
        WHERE l.company_id=%s AND b.status='OVERDUE'
    """, (company_id,))
    inadimplentes = get_count(cur.fetchone())

    # Locações atrasadas (equipamento não devolvido depois da data_fim planejada)
    cur.execute("""
        SELECT COUNT(*) AS count FROM locacoes
        WHERE company_id=%s AND cancelado=FALSE AND data_fim IS NOT NULL AND data_fim < CURRENT_DATE
    """, (company_id,))
    locacoes_atrasadas = get_count(cur.fetchone())

    cur.close()
    conn.close()

    metrics = {
        "total_clientes": total_clientes,
        "total_motos": total_motos,
        "locacoes_ativas": locacoes_ativas,
        "locacoes_canceladas": locacoes_canceladas,
        "boletos_pendentes": boletos_pendentes,
        "boletos_pagados": boletos_pagados,
        "receita_mes": receita_mes,
        "inadimplentes": inadimplentes,
        "locacoes_atrasadas": locacoes_atrasadas,
        "hoje": hoje.strftime("%Y-%m-%d"),
    }

    return render_template("dashboard.html", **metrics)