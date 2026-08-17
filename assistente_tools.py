"""
Ferramentas (tool use) que o assistente de IA pode chamar. O modelo escolhe
o NOME da ferramenta e os PARÂMETROS (ex: período) — nunca escreve SQL e
nunca escolhe a empresa. company_id é sempre injetado pelo servidor a partir
do usuário logado, em executar_tool.
"""

from periodos import intervalo_periodo
from relatorios import (
    STATUS_RECEBIDO,
    _atrasadas,
    _inadimplentes,
    _mais_alugados,
    _mais_rentaveis,
    _parados,
    _receita_categoria,
    _receita_cliente,
    _receita_filial,
)

PERIODO_ENUM = ["hoje", "semana", "mes", "ano"]
PERIODO_PARAM = {
    "type": "object",
    "properties": {
        "periodo": {
            "type": "string",
            "enum": PERIODO_ENUM,
            "description": "Período do relatório: hoje, semana (semana atual), mes (mês atual) ou ano (ano atual).",
        },
    },
    "required": ["periodo"],
}


def _colunas_linhas_para_dict(colunas, linhas):
    return {"colunas": colunas, "linhas": [dict(zip(colunas, linha)) for linha in linhas]}


def _tool_receita_total(cur, company_id, periodo):
    inicio, fim = intervalo_periodo(periodo, None, None)
    cur.execute("""
        SELECT COALESCE(SUM(l.valor), 0) AS receita_total, COUNT(*) AS total_locacoes
        FROM locacoes l
        WHERE l.company_id = %s AND l.pagamento_status IN %s AND l.data_inicio BETWEEN %s AND %s
    """, (company_id, STATUS_RECEBIDO, inicio, fim))
    row = cur.fetchone()
    return {
        "periodo": periodo, "data_inicio": str(inicio), "data_fim": str(fim),
        "receita_total": round(float(row["receita_total"] or 0), 2),
        "total_locacoes_pagas": row["total_locacoes"],
    }


def _tool_equipamentos_manutencao_pendente(cur, company_id):
    cur.execute("""
        SELECT ei.nome, ei.codigo_interno, m.tipo, m.problema, m.status, m.data_conclusao_prevista
        FROM manutencoes m
        JOIN equipment_items ei ON ei.id = m.equipment_item_id
        WHERE m.company_id = %s AND m.status IN ('aberta', 'em_andamento')
        ORDER BY m.data_conclusao_prevista ASC NULLS LAST
    """, (company_id,))
    linhas = [
        {
            "equipamento": r["nome"], "codigo": r["codigo_interno"] or "-", "tipo_manutencao": r["tipo"],
            "problema": r["problema"], "status": r["status"],
            "conclusao_prevista": str(r["data_conclusao_prevista"]) if r["data_conclusao_prevista"] else None,
        }
        for r in cur.fetchall()
    ]
    return {"equipamentos_pendentes": linhas}


# Cada entrada: schema de tool-use da Anthropic + a função Python que executa.
TOOLS = [
    {
        "name": "equipamentos_mais_alugados",
        "description": "Lista os equipamentos com mais locações num período, do mais alugado pro menos.",
        "input_schema": PERIODO_PARAM,
        "_run": lambda cur, cid, args: _colunas_linhas_para_dict(*_mais_alugados(cur, cid, *intervalo_periodo(args["periodo"], None, None))),
    },
    {
        "name": "equipamentos_mais_rentaveis",
        "description": "Lista os equipamentos que mais faturaram (receita paga) num período, do que mais faturou pro que menos faturou.",
        "input_schema": PERIODO_PARAM,
        "_run": lambda cur, cid, args: _colunas_linhas_para_dict(*_mais_rentaveis(cur, cid, *intervalo_periodo(args["periodo"], None, None))),
    },
    {
        "name": "equipamentos_parados",
        "description": "Lista equipamentos que não tiveram nenhuma locação iniciada num período.",
        "input_schema": PERIODO_PARAM,
        "_run": lambda cur, cid, args: _colunas_linhas_para_dict(*_parados(cur, cid, *intervalo_periodo(args["periodo"], None, None))),
    },
    {
        "name": "receita_por_categoria",
        "description": "Receita paga (recebida) num período, somada por categoria de equipamento.",
        "input_schema": PERIODO_PARAM,
        "_run": lambda cur, cid, args: _colunas_linhas_para_dict(*_receita_categoria(cur, cid, *intervalo_periodo(args["periodo"], None, None))),
    },
    {
        "name": "receita_por_cliente",
        "description": "Receita paga (recebida) num período, somada por cliente.",
        "input_schema": PERIODO_PARAM,
        "_run": lambda cur, cid, args: _colunas_linhas_para_dict(*_receita_cliente(cur, cid, *intervalo_periodo(args["periodo"], None, None))),
    },
    {
        "name": "receita_por_filial",
        "description": "Receita paga (recebida) num período, somada por filial.",
        "input_schema": PERIODO_PARAM,
        "_run": lambda cur, cid, args: _colunas_linhas_para_dict(*_receita_filial(cur, cid, *intervalo_periodo(args["periodo"], None, None))),
    },
    {
        "name": "receita_total",
        "description": "Faturamento TOTAL (soma única, não quebrada por categoria/cliente/filial) recebido num período. Use pra perguntas como 'quanto faturei essa semana/mês'.",
        "input_schema": PERIODO_PARAM,
        "_run": lambda cur, cid, args: _tool_receita_total(cur, cid, args["periodo"]),
    },
    {
        "name": "clientes_inadimplentes",
        "description": "Lista clientes com locações em atraso de pagamento (pagamento_status OVERDUE) num período, com valor em atraso.",
        "input_schema": PERIODO_PARAM,
        "_run": lambda cur, cid, args: _colunas_linhas_para_dict(*_inadimplentes(cur, cid, *intervalo_periodo(args["periodo"], None, None))),
    },
    {
        "name": "locacoes_atrasadas",
        "description": "Lista locações cujo equipamento não foi devolvido depois da data de fim planejada (atraso de devolução, não de pagamento), com multa calculada.",
        "input_schema": PERIODO_PARAM,
        "_run": lambda cur, cid, args: _colunas_linhas_para_dict(*_atrasadas(cur, cid, *intervalo_periodo(args["periodo"], None, None))),
    },
    {
        "name": "equipamentos_precisam_manutencao",
        "description": "Lista equipamentos com manutenção aberta ou em andamento agora (não concluída), com a data prevista de conclusão quando houver.",
        "input_schema": {"type": "object", "properties": {}},
        "_run": lambda cur, cid, args: _tool_equipamentos_manutencao_pendente(cur, cid),
    },
]

TOOLS_BY_NAME = {t["name"]: t for t in TOOLS}


def tools_schema_para_cohere():
    """Formato que a API v2 da Cohere espera (estilo function-calling), sem o _run interno."""
    return [
        {
            "type": "function",
            "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]},
        }
        for t in TOOLS
    ]


def executar_tool(cur, company_id, nome, args):
    """
    Executa a ferramenta pelo nome. company_id vem sempre do servidor
    (current_user.company_id) — nunca do modelo/args. Levanta ValueError se
    o nome não corresponder a nenhuma ferramenta conhecida.
    """
    tool = TOOLS_BY_NAME.get(nome)
    if not tool:
        raise ValueError(f"Ferramenta desconhecida: {nome}")
    return tool["_run"](cur, company_id, args or {})
