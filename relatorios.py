import datetime as dt

from multas import calcular_multa
from permissions import VER_RELATORIOS, VER_RELATORIOS_FINANCEIROS

STATUS_RECEBIDO = ("RECEIVED", "CONFIRMED")


def _num(v):
    return round(float(v or 0), 2)


def _mais_alugados(cur, company_id, inicio, fim):
    cur.execute("""
        SELECT ei.nome, ei.codigo_interno, COUNT(l.id) AS total
        FROM locacoes l
        JOIN equipment_items ei ON ei.id = l.equipment_item_id
        WHERE ei.company_id = %s AND l.data_inicio BETWEEN %s AND %s
        GROUP BY ei.id, ei.nome, ei.codigo_interno
        ORDER BY total DESC
    """, (company_id, inicio, fim))
    linhas = [[r["nome"], r["codigo_interno"] or "-", r["total"]] for r in cur.fetchall()]
    return ["Equipamento", "Código", "Total de Locações"], linhas


def _mais_rentaveis(cur, company_id, inicio, fim):
    cur.execute("""
        SELECT ei.nome, ei.codigo_interno, COALESCE(SUM(l.valor), 0) AS receita
        FROM locacoes l
        JOIN equipment_items ei ON ei.id = l.equipment_item_id
        WHERE ei.company_id = %s AND l.pagamento_status IN %s AND l.data_inicio BETWEEN %s AND %s
        GROUP BY ei.id, ei.nome, ei.codigo_interno
        ORDER BY receita DESC
    """, (company_id, STATUS_RECEBIDO, inicio, fim))
    linhas = [[r["nome"], r["codigo_interno"] or "-", _num(r["receita"])] for r in cur.fetchall()]
    return ["Equipamento", "Código", "Receita (R$)"], linhas


def _parados(cur, company_id, inicio, fim):
    cur.execute("""
        SELECT ei.nome, ei.codigo_interno, ei.status
        FROM equipment_items ei
        WHERE ei.company_id = %s AND NOT EXISTS (
            SELECT 1 FROM locacoes l
            WHERE l.equipment_item_id = ei.id AND l.data_inicio BETWEEN %s AND %s
        )
        ORDER BY ei.nome
    """, (company_id, inicio, fim))
    linhas = [[r["nome"], r["codigo_interno"] or "-", r["status"]] for r in cur.fetchall()]
    return ["Equipamento", "Código", "Status Atual"], linhas


def _receita_categoria(cur, company_id, inicio, fim):
    cur.execute("""
        SELECT COALESCE(ec.nome, 'Sem categoria') AS categoria, COALESCE(SUM(l.valor), 0) AS receita
        FROM locacoes l
        JOIN equipment_items ei ON ei.id = l.equipment_item_id
        LEFT JOIN equipment_categories ec ON ec.id = ei.categoria_id
        WHERE ei.company_id = %s AND l.pagamento_status IN %s AND l.data_inicio BETWEEN %s AND %s
        GROUP BY ec.id, ec.nome
        ORDER BY receita DESC
    """, (company_id, STATUS_RECEBIDO, inicio, fim))
    linhas = [[r["categoria"], _num(r["receita"])] for r in cur.fetchall()]
    return ["Categoria", "Receita (R$)"], linhas


def _receita_cliente(cur, company_id, inicio, fim):
    cur.execute("""
        SELECT c.nome, COALESCE(SUM(l.valor), 0) AS receita
        FROM locacoes l
        JOIN clientes c ON c.id = l.cliente_id
        WHERE l.company_id = %s AND l.pagamento_status IN %s AND l.data_inicio BETWEEN %s AND %s
        GROUP BY c.id, c.nome
        ORDER BY receita DESC
    """, (company_id, STATUS_RECEBIDO, inicio, fim))
    linhas = [[r["nome"], _num(r["receita"])] for r in cur.fetchall()]
    return ["Cliente", "Receita (R$)"], linhas


def _receita_filial(cur, company_id, inicio, fim):
    cur.execute("""
        SELECT COALESCE(b.nome, 'Sem filial') AS filial, COALESCE(SUM(l.valor), 0) AS receita
        FROM locacoes l
        JOIN equipment_items ei ON ei.id = l.equipment_item_id
        LEFT JOIN branches b ON b.id = ei.branch_id
        WHERE ei.company_id = %s AND l.pagamento_status IN %s AND l.data_inicio BETWEEN %s AND %s
        GROUP BY b.id, b.nome
        ORDER BY receita DESC
    """, (company_id, STATUS_RECEBIDO, inicio, fim))
    linhas = [[r["filial"], _num(r["receita"])] for r in cur.fetchall()]
    return ["Filial", "Receita (R$)"], linhas


def _inadimplentes(cur, company_id, inicio, fim):
    cur.execute("""
        SELECT c.nome, c.telefone, COUNT(l.id) AS total_locacoes, COALESCE(SUM(l.valor), 0) AS valor_atraso
        FROM locacoes l
        JOIN clientes c ON c.id = l.cliente_id
        WHERE l.company_id = %s AND l.pagamento_status = 'OVERDUE' AND l.data_inicio BETWEEN %s AND %s
        GROUP BY c.id, c.nome, c.telefone
        ORDER BY valor_atraso DESC
    """, (company_id, inicio, fim))
    linhas = [[r["nome"], r["telefone"] or "-", r["total_locacoes"], _num(r["valor_atraso"])] for r in cur.fetchall()]
    return ["Cliente", "Telefone", "Locações em Atraso", "Valor em Atraso (R$)"], linhas


def _atrasadas(cur, company_id, inicio, fim):
    cur.execute("""
        SELECT l.id, c.nome AS cliente_nome, ei.nome AS equipamento_nome, ei.valor_diaria,
               l.data_fim, l.valor, l.company_id
        FROM locacoes l
        JOIN clientes c ON c.id = l.cliente_id
        JOIN equipment_items ei ON ei.id = l.equipment_item_id
        WHERE l.company_id = %s AND l.cancelado = FALSE AND l.data_fim IS NOT NULL AND l.data_fim < CURRENT_DATE
          AND l.data_inicio BETWEEN %s AND %s
        ORDER BY l.data_fim ASC
    """, (company_id, inicio, fim))
    rows = cur.fetchall()

    cur.execute("SELECT * FROM config_multas WHERE company_id=%s", (company_id,))
    config = cur.fetchone()

    linhas = []
    hoje = dt.date.today()
    for r in rows:
        calculo = calcular_multa(r["data_fim"], hoje, r["valor"], r["valor_diaria"], config)
        linhas.append([
            f"#{r['id']}", r["cliente_nome"], r["equipamento_nome"],
            calculo["dias_atraso"], _num(calculo["valor_multa_total"]),
        ])
    return ["Locação", "Cliente", "Equipamento", "Dias de Atraso", "Multa (R$)"], linhas


RELATORIOS = {
    "mais-alugados": {"titulo": "Equipamentos Mais Alugados", "permissao": VER_RELATORIOS, "funcao": _mais_alugados},
    "mais-rentaveis": {"titulo": "Equipamentos Mais Rentáveis", "permissao": VER_RELATORIOS_FINANCEIROS, "funcao": _mais_rentaveis},
    "parados": {"titulo": "Equipamentos Parados", "permissao": VER_RELATORIOS, "funcao": _parados},
    "receita-categoria": {"titulo": "Receita por Categoria", "permissao": VER_RELATORIOS_FINANCEIROS, "funcao": _receita_categoria},
    "receita-cliente": {"titulo": "Receita por Cliente", "permissao": VER_RELATORIOS_FINANCEIROS, "funcao": _receita_cliente},
    "receita-filial": {"titulo": "Receita por Filial", "permissao": VER_RELATORIOS_FINANCEIROS, "funcao": _receita_filial},
    "inadimplentes": {"titulo": "Clientes Inadimplentes", "permissao": VER_RELATORIOS_FINANCEIROS, "funcao": _inadimplentes},
    "atrasadas": {"titulo": "Locações Atrasadas", "permissao": VER_RELATORIOS_FINANCEIROS, "funcao": _atrasadas},
}
