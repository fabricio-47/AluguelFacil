from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user

from database import get_db_connection
from permissions import requer_permissao, VER_ASSISTENTE
from ia_assistente import perguntar, AssistenteError

assistente_bp = Blueprint("assistente", __name__, url_prefix="/assistente")

SESSION_KEY = "assistente_historico"
MAX_TROCAS = 3  # 3 perguntas + 3 respostas = 6 entradas — a sessão Flask é um cookie assinado, precisa caber


@assistente_bp.route("/")
@login_required
@requer_permissao(VER_ASSISTENTE)
def chat():
    return render_template("assistente.html", historico=session.get(SESSION_KEY, []))


@assistente_bp.route("/perguntar", methods=["POST"])
@login_required
@requer_permissao(VER_ASSISTENTE)
def fazer_pergunta():
    pergunta = (request.form.get("pergunta") or "").strip()
    if not pergunta:
        flash("Digite uma pergunta.", "warning")
        return redirect(url_for("assistente.chat"))

    historico = session.get(SESSION_KEY, [])

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        resposta = perguntar(pergunta, current_user.company_id, cur, historico=historico)
    except AssistenteError as e:
        resposta = f"⚠️ {e}"
    finally:
        cur.close()
        conn.close()

    historico.append({"role": "user", "texto": pergunta})
    historico.append({"role": "assistant", "texto": resposta})
    session[SESSION_KEY] = historico[-(MAX_TROCAS * 2):]

    return redirect(url_for("assistente.chat"))


@assistente_bp.route("/limpar", methods=["POST"])
@login_required
@requer_permissao(VER_ASSISTENTE)
def limpar_historico():
    session.pop(SESSION_KEY, None)
    return redirect(url_for("assistente.chat"))
