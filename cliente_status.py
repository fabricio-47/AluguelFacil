"""Regra de atualização cadastral obrigatória (comprovante de residência).

Ver docs/superpowers/specs/2026-08-18-atualizacao-cadastral-comprovante-design.md
Usado tanto pelo aviso no front-end (rota de status) quanto pelo bloqueio
no back-end (criar_locacao_interna) — uma única fonte de verdade.
"""
import datetime as dt

DIAS_LIMITE_COMPROVANTE = 90


def cliente_precisa_atualizar_comprovante(cur, cliente_id):
    """Retorna True se o cliente precisa reenviar o comprovante de
    residência antes de criar uma nova locação."""
    cur.execute(
        "SELECT comprovante_residencia_atualizado_em FROM clientes WHERE id=%s",
        (cliente_id,),
    )
    row = cur.fetchone()
    if not row:
        return False  # cliente inexistente — quem chama trata esse caso separadamente
    atualizado_em = row["comprovante_residencia_atualizado_em"] if isinstance(row, dict) else row[0]

    cur.execute(
        "SELECT MAX(data_inicio) AS ultima FROM locacoes WHERE cliente_id=%s AND cancelado=FALSE",
        (cliente_id,),
    )
    ultima_row = cur.fetchone()
    ultima_locacao = ultima_row["ultima"] if isinstance(ultima_row, dict) else ultima_row[0]

    hoje = dt.date.today()
    limite = dt.timedelta(days=DIAS_LIMITE_COMPROVANTE)

    if ultima_locacao is None:
        # Cliente de primeira locação: comprovante não pode ter mais de 90 dias.
        if atualizado_em is None:
            return True
        return (hoje - atualizado_em.date()) > limite

    # Cliente que já alugou antes: só reavalia se ficou mais de 90 dias parado.
    if (hoje - ultima_locacao) <= limite:
        return False

    if atualizado_em is None:
        return True
    return atualizado_em.date() <= ultima_locacao
