from flask import Blueprint, render_template
from flask_login import login_required

from database import get_db_connection
from permissions import requer_permissao, VER_MAPA_OPERACIONAL

operacional_bp = Blueprint("operacional", __name__, url_prefix="/operacional")


@operacional_bp.route("/")
@login_required
@requer_permissao(VER_MAPA_OPERACIONAL)
def mapa():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS total FROM locacoes WHERE cancelado=FALSE AND data_inicio = CURRENT_DATE")
    retiradas_hoje = cur.fetchone()["total"]

    cur.execute("""
        SELECT COUNT(*) AS total FROM checklists
        WHERE tipo='devolucao' AND criado_em::date = CURRENT_DATE
    """)
    devolucoes_hoje = cur.fetchone()["total"]

    cur.execute("SELECT COUNT(*) AS total FROM entregas WHERE horario_previsto::date = CURRENT_DATE")
    entregas_hoje = cur.fetchone()["total"]

    cur.execute("""
        SELECT COUNT(*) AS total FROM locacoes
        WHERE cancelado=FALSE AND data_fim IS NOT NULL AND data_fim < CURRENT_DATE
    """)
    atrasados = cur.fetchone()["total"]

    cur.close()
    conn.close()

    return render_template(
        "operacional.html",
        retiradas_hoje=retiradas_hoje,
        devolucoes_hoje=devolucoes_hoje,
        entregas_hoje=entregas_hoje,
        atrasados=atrasados,
    )
