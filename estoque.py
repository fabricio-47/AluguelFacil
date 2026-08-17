def registrar_movimentacao(cur, equipment_item_id, tipo, motivo, usuario_id):
    """
    Registra uma linha de auditoria em movimentacoes_estoque. Não faz commit —
    quem chama controla a transação (mesmo padrão de executar_cancelamento_locacao).

    quantidade é sempre 1: cada linha de equipment_items já representa uma
    unidade serializada, não um estoque agregado (mesmo modelo desde a Fase 1/2).
    """
    cur.execute("""
        INSERT INTO movimentacoes_estoque (equipment_item_id, tipo, quantidade, motivo, usuario_id)
        VALUES (%s, %s, 1, %s, %s)
    """, (equipment_item_id, tipo, motivo, usuario_id))
