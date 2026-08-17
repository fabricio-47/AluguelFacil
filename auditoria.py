import json


def registrar_auditoria(cur, company_id, usuario_id, acao, tabela_afetada, registro_id,
                         valores_antes=None, valores_depois=None):
    """
    Registra uma linha de auditoria. Não faz commit — quem chama controla a
    transação (mesmo padrão de registrar_movimentacao/salvar_assinatura).
    """
    cur.execute("""
        INSERT INTO auditoria (company_id, usuario_id, acao, tabela_afetada, registro_id, valores_antes, valores_depois)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        company_id, usuario_id, acao, tabela_afetada, registro_id,
        json.dumps(valores_antes) if valores_antes is not None else None,
        json.dumps(valores_depois) if valores_depois is not None else None,
    ))
