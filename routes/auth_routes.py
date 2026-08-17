import datetime as dt

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required
from werkzeug.security import check_password_hash

from database import get_db_connection
from models.user import User
from permissions import landing_url

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _empresa_bloqueada(company_id):
    """Confere se a empresa está bloqueada, ou se passou da data_bloqueio sem
    confirmação manual de pagamento — nesse segundo caso, o próprio login já
    vira o status pra 'bloqueado' na hora (sem depender de nenhum agendador)."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT status, data_bloqueio FROM companies WHERE id=%s", (company_id,))
        company = cur.fetchone()
        if not company:
            return False

        if company["status"] == "bloqueado":
            return True

        if company["data_bloqueio"] and company["data_bloqueio"] < dt.date.today():
            cur.execute(
                "UPDATE companies SET status='bloqueado', status_atualizado_em=CURRENT_TIMESTAMP WHERE id=%s",
                (company_id,),
            )
            conn.commit()
            return True

        return False
    finally:
        conn.close()


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")   # bate com login.html
        senha = request.form.get("senha")   # bate com login.html
        remember = bool(request.form.get("remember"))

        user = User.get_by_email(email) if email else None

        if user and check_password_hash(user.senha, senha or ""):
            if not user.eh_admin_plataforma and _empresa_bloqueada(user.company_id):
                flash("Acesso bloqueado. Entre em contato com o suporte.", "danger")
                return render_template("login.html")

            login_user(user, remember=remember)
            flash("Login efetuado!", "success")

            next_url = request.form.get("next") or request.args.get("next")
            return redirect(next_url or landing_url())

        flash("Usuário ou senha incorretos!", "danger")

    return render_template("login.html")

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logout realizado!", "success")
    return redirect(url_for("auth.login"))
