"""
Licenciamento por modulo (Fase 4). Cada modulo pago tem uma linha em
company_modulos por empresa (status trial/ativo/bloqueado/cancelado).
Ausencia de linha = nunca contratou = bloqueado.

Uso: registrar em cada blueprint gateado, uma vez, no fim do arquivo de
rotas:

    from modulos import gate_modulo
    meu_bp.before_request(gate_modulo("meu_slug"))

Equipamentos/veiculos/imoveis (mesma tela/tabela) ainda NAO estao aqui --
o filtro por categoria dentro da tela ainda nao foi implementado.
"""

import datetime as dt

from flask import flash, redirect, url_for
from flask_login import current_user

from database import get_db_connection

MODULOS = {
    "equipamentos": {"nome": "Equipamentos", "preco": 39.90},
    "veiculos": {"nome": "Veículos", "preco": 39.90},
    "imoveis": {"nome": "Imóveis", "preco": 39.90},
    "locacoes": {"nome": "Locações", "preco": 39.90},
    "financeiro": {"nome": "Financeiro", "preco": 39.90},
    "crm": {"nome": "CRM / Pipeline", "preco": 39.90},
    "manutencoes": {"nome": "Manutenções", "preco": 39.90},
    "entregas": {"nome": "Entregas", "preco": 39.90},
    "orcamentos": {"nome": "Orçamentos", "preco": 39.90},
    "relatorios": {"nome": "Relatórios", "preco": 39.90},
    "assistente": {"nome": "Assistente de IA", "preco": 39.90},
}

TRIAL_DIAS = 7


def tem_modulo_ativo(cur, company_id, modulo):
    """True se a empresa pode usar o modulo agora (ativo, ou trial dentro do prazo)."""
    cur.execute(
        "SELECT status, trial_termina_em FROM company_modulos WHERE company_id=%s AND modulo=%s",
        (company_id, modulo),
    )
    row = cur.fetchone()
    if not row:
        return False
    if row["status"] == "ativo":
        return True
    if row["status"] == "trial":
        return row["trial_termina_em"] is None or row["trial_termina_em"] >= dt.datetime.utcnow()
    return False  # bloqueado, cancelado


def gate_modulo(slug):
    """Fabrica uma funcao pronta pra registrar via blueprint.before_request(...).

    Deixa passar direto usuarios nao autenticados (quem cuida disso e o
    @login_required de cada view) e admins da plataforma (eh_admin_plataforma
    -- gerenciam o SaaS inteiro, nao sao clientes de uma empresa).
    """
    def _gate():
        if not current_user.is_authenticated:
            return None
        if getattr(current_user, "eh_admin_plataforma", False):
            return None

        conn = get_db_connection()
        cur = conn.cursor()
        try:
            liberado = tem_modulo_ativo(cur, current_user.company_id, slug)
        finally:
            cur.close()
            conn.close()

        if not liberado:
            nome = MODULOS.get(slug, {}).get("nome", slug)
            flash(
                f"O módulo \"{nome}\" não está ativo para sua empresa. "
                f"Fale com o administrador da conta para contratar.",
                "warning",
            )
            return redirect(url_for("dashboard.home"))
        return None

    return _gate
