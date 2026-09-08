import datetime as dt

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required
from werkzeug.security import check_password_hash

from database import get_db_connection
from models.user import User
from permissions import landing_url
from text_utils import slugify
from validators import validar_forca_senha
from modulos import MODULOS, TRIAL_DIAS
from werkzeug.security import generate_password_hash

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

import secrets
import datetime as dt
from werkzeug.security import generate_password_hash
from email_utils import enviar_email


@auth_bp.route("/recuperar-senha", methods=["GET", "POST"])
def recuperar_senha():
    if request.method == "POST":
        email = request.form.get("email")
        user = User.get_by_email(email)
        if user:
            conn = get_db_connection()
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT COUNT(*) AS total FROM password_resets WHERE usuario_id = %s AND criado_em > NOW() - INTERVAL '15 minutes'",
                    (user.id,),
                )
                total_recente = cur.fetchone()["total"]
            finally:
                conn.close()

            if total_recente < 3:
                token = secrets.token_urlsafe(32)
                expira_em = dt.datetime.utcnow() + dt.timedelta(hours=1)
                conn = get_db_connection()
                try:
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO password_resets (usuario_id, token, expira_em) VALUES (%s, %s, %s)",
                        (user.id, token, expira_em),
                    )
                    conn.commit()
                finally:
                    conn.close()

                link = url_for("auth.resetar_senha", token=token, _external=True)
                corpo = f"""
                    <p>Ola,</p>
                    <p>Recebemos um pedido para redefinir sua senha no AluguelFacil.</p>
                    <p><a href="{link}">Clique aqui para criar uma nova senha</a></p>
                    <p>Esse link expira em 1 hora. Se voce nao pediu isso, ignore este e-mail.</p>
                """
                try:
                    enviar_email(email, "Recuperacao de senha - AluguelFacil", corpo)
                except Exception as e:
                    flash(f"Nao foi possivel enviar o e-mail: {e}", "danger")
                    return render_template("recuperar_senha.html")

        flash("Se esse e-mail estiver cadastrado, enviamos um link de recuperacao.", "info")
        return redirect(url_for("auth.login"))

    return render_template("recuperar_senha.html")


@auth_bp.route("/resetar-senha/<token>", methods=["GET", "POST"])
def resetar_senha(token):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM password_resets WHERE token = %s AND usado = FALSE AND expira_em > CURRENT_TIMESTAMP",
            (token,),
        )
        reset = cur.fetchone()
    finally:
        conn.close()

    if not reset:
        flash("Link de recuperacao invalido ou expirado. Peca um novo.", "danger")
        return redirect(url_for("auth.recuperar_senha"))

    if request.method == "POST":
        nova_senha = request.form.get("nova_senha")
        confirmacao = request.form.get("confirmacao_senha")

        if not nova_senha or len(nova_senha) < 8:
            flash("A senha precisa ter no minimo 8 caracteres.", "danger")
            return render_template("resetar_senha_form.html", token=token)

        if nova_senha != confirmacao:
            flash("As senhas nao coincidem.", "danger")
            return render_template("resetar_senha_form.html", token=token)

        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE usuarios SET senha = %s WHERE id = %s",
                (generate_password_hash(nova_senha), reset["usuario_id"]),
            )
            cur.execute(
                "UPDATE password_resets SET usado = TRUE WHERE token = %s",
                (token,),
            )
            conn.commit()
        finally:
            conn.close()

        flash("Senha alterada com sucesso! Faca login com a nova senha.", "success")
        return redirect(url_for("auth.login"))

    return render_template("resetar_senha_form.html", token=token)


# ======================
# Cadastro publico de empresa (self-signup) -- qualquer visitante pode criar
# a propria empresa + usuario admin, sem aprovacao manual. Rate limit por IP
# pra segurar spam/abuso (3 tentativas por hora, mesma logica do rate limit
# de recuperar_senha).
# ======================
def _ip_do_cliente():
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "desconhecido"


def _gerar_slug_unico_empresa(cur, nome):
    cur.execute("SELECT slug FROM companies WHERE slug IS NOT NULL")
    usados = {r["slug"] for r in cur.fetchall()}
    base = slugify(nome)
    slug = base
    contador = 2
    while slug in usados:
        slug = f"{base}-{contador}"
        contador += 1
    return slug


@auth_bp.route("/cadastro", methods=["GET", "POST"])
def cadastro_publico():
    if request.method == "POST":
        ip = _ip_do_cliente()

        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT COUNT(*) AS total FROM signup_attempts WHERE ip=%s AND criado_em > NOW() - INTERVAL '1 hour'",
                (ip,),
            )
            tentativas = cur.fetchone()["total"]
            if tentativas >= 3:
                cur.close()
                conn.close()
                flash("Muitas tentativas de cadastro. Tente novamente daqui a 1 hora.", "danger")
                return render_template("cadastro.html")

            cur.execute("INSERT INTO signup_attempts (ip) VALUES (%s)", (ip,))
            conn.commit()

            nome_empresa = (request.form.get("nome_empresa") or "").strip()
            username = (request.form.get("username") or "").strip()
            email = (request.form.get("email") or "").strip()
            senha = request.form.get("senha") or ""

            if not nome_empresa or not username or not email or not senha:
                cur.close()
                conn.close()
                flash("Preencha nome da empresa, usuário, e-mail e senha.", "warning")
                return render_template("cadastro.html")

            senha_valida, erro_senha = validar_forca_senha(senha, [username, email])
            if not senha_valida:
                cur.close()
                conn.close()
                flash(erro_senha, "warning")
                return render_template("cadastro.html")

            cur.execute("SELECT id FROM usuarios WHERE username=%s OR email=%s", (username, email))
            if cur.fetchone():
                cur.close()
                conn.close()
                flash("Já existe um usuário com esse username ou e-mail.", "warning")
                return render_template("cadastro.html")

            slug = _gerar_slug_unico_empresa(cur, nome_empresa)
            cur.execute("""
                INSERT INTO companies (nome, slug, plano, status)
                VALUES (%s, %s, 'basico', 'ativo')
                RETURNING id
            """, (nome_empresa, slug))
            company_id = cur.fetchone()["id"]

            cur.execute("INSERT INTO branches (company_id, nome) VALUES (%s, 'Matriz')", (company_id,))

            cur.execute("""
                INSERT INTO usuarios (username, email, senha, role, company_id, is_admin)
                VALUES (%s, %s, %s, 'admin_locadora', %s, FALSE)
            """, (username, email, generate_password_hash(senha), company_id))

            trial_termina_em = dt.datetime.utcnow() + dt.timedelta(days=TRIAL_DIAS)
            for slug_modulo in MODULOS.keys():
                cur.execute("""
                    INSERT INTO company_modulos (company_id, modulo, status, trial_termina_em)
                    VALUES (%s, %s, 'trial', %s)
                    ON CONFLICT (company_id, modulo) DO NOTHING
                """, (company_id, slug_modulo, trial_termina_em))

            conn.commit()
            flash("Conta criada com sucesso! Faça login para começar.", "success")
            return redirect(url_for("auth.login"))
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao criar conta: {e}", "danger")
            return render_template("cadastro.html")
        finally:
            cur.close()
            conn.close()

    return render_template("cadastro.html")
