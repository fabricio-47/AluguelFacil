from psycopg2 import sql

PRECO_PLANO = {
    "basico": 97.0,
    "profissional": 297.0,
    "enterprise": 697.0,
}


def verificar_limite(cur, company_id, coluna_limite, tabela):
    """
    Verifica se a company já atingiu o limite do plano numa tabela contável
    (usuarios/equipment_items/branches). limite NULL = sem limite.
    """
    cur.execute(
        sql.SQL("SELECT {} AS limite FROM companies WHERE id=%s").format(sql.Identifier(coluna_limite)),
        (company_id,),
    )
    limite = cur.fetchone()["limite"]

    cur.execute(
        sql.SQL("SELECT COUNT(*) AS usado FROM {} WHERE company_id=%s").format(sql.Identifier(tabela)),
        (company_id,),
    )
    usado = cur.fetchone()["usado"]

    return {
        "usado": usado,
        "limite": limite,
        "dentro_do_limite": limite is None or usado < limite,
    }
