import secrets

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash

from database import get_db_connection
from permissions import requer_permissao, tem_permissao, VER_USUARIOS, GERENCIAR_USUARIOS
from planos import verificar_limite
from validators import validar_forca_senha

usuarios_bp = Blueprint("usuarios", __name__, url_prefix="/usuarios")

ROLES_DISPONIVEIS = (
    "super_admin", "admin_locadora", "gerente", "financeiro", "atendente",
    "vendedor", "tecnico", "estoquista", "entregador",
)


# ==== Listar + criar (sempre restrito à própria empresa) ====
@usuarios_bp.route("/", methods=["GET", "POST"])
@login_required
@requer_permissao(VER_USUARIOS)
def listar_usuarios():
    if request.method == "POST":
        if not tem_permissao(GERENCIAR_USUARIOS):
            flash("Você não tem permissão para cadastrar usuários.", "danger")
            return redirect(url_for("usuarios.listar_usuarios"))

        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip()
        senha = request.form.get("senha") or ""
        role = (request.form.get("role") or "").strip()

        if not username or not email or not senha or role not in ROLES_DISPONIVEIS:
            flash("Preencha usuário, e-mail, senha e um cargo válido.", "warning")
            return redirect(url_for("usuarios.listar_usuarios"))
        senha_valida, erro_senha = validar_forca_senha(senha, [username, email])
        if not senha_valida:
            flash(erro_senha, "warning")
            return redirect(url_for("usuarios.listar_usuarios"))

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            limite = verificar_limite(cur, current_user.company_id, "limite_usuarios", "usuarios")
            if not limite["dentro_do_limite"]:
                flash(
                    f"Limite de usuários do plano atingido ({limite['usado']}/{limite['limite']}). "
                    f"Fale com o suporte pra aumentar o limite.",
                    "danger",
                )
                return redirect(url_for("usuarios.listar_usuarios"))

            cur.execute("SELECT id FROM usuarios WHERE username=%s OR email=%s", (username, email))
            if cur.fetchone():
                flash("Já existe um usuário com esse username ou e-mail.", "warning")
                return redirect(url_for("usuarios.listar_usuarios"))

            # eh_admin_plataforma nunca é setado por aqui — só o painel de plataforma concede isso.
            cur.execute("""
                INSERT INTO usuarios (username, email, senha, role, company_id, is_admin)
                VALUES (%s, %s, %s, %s, %s, FALSE)
            """, (username, email, generate_password_hash(senha), role, current_user.company_id))
            conn.commit()
            flash("Usuário cadastrado com sucesso!", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao cadastrar usuário: {e}", "danger")
        finally:
            cur.close()
            conn.close()

        return redirect(url_for("usuarios.listar_usuarios"))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT id, username, email, role, created_at
            FROM usuarios WHERE company_id=%s ORDER BY username ASC
        """, (current_user.company_id,))
        usuarios = cur.fetchall()
        return render_template("usuarios.html", usuarios=usuarios, roles=ROLES_DISPONIVEIS)
    finally:
        cur.close()
        conn.close()


# ==== Editar (cargo + opcionalmente resetar senha) ====
@usuarios_bp.route("/<int:id>/editar", methods=["GET", "POST"])
@login_required
@requer_permissao(GERENCIAR_USUARIOS)
def editar_usuario(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT id, username, email, role, company_id FROM usuarios WHERE id=%s", (id,))
        usuario = cur.fetchone()
        if not usuario or usuario["company_id"] != current_user.company_id:
            flash("Usuário não encontrado.", "warning")
            return redirect(url_for("usuarios.listar_usuarios"))

        if request.method == "POST":
            role = (request.form.get("role") or "").strip()

            if role not in ROLES_DISPONIVEIS:
                flash("Selecione um cargo válido.", "warning")
                return redirect(url_for("usuarios.editar_usuario", id=id))

            try:
                cur.execute("UPDATE usuarios SET role=%s WHERE id=%s", (role, id))
                conn.commit()
                flash("Usuário atualizado com sucesso!", "success")
                return redirect(url_for("usuarios.listar_usuarios"))
            except Exception as e:
                conn.rollback()
                flash(f"Erro ao atualizar usuário: {e}", "danger")

        return render_template("editar_usuario.html", usuario=usuario, roles=ROLES_DISPONIVEIS)
    finally:
        cur.close()
        conn.close()


# ==== Gera uma senha temporária aleatória e mostra ela uma única vez ====
@usuarios_bp.route("/<int:id>/resetar-senha", methods=["POST"])
@login_required
@requer_permissao(GERENCIAR_USUARIOS)
def resetar_senha_usuario(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT id, username, company_id FROM usuarios WHERE id=%s", (id,))
        usuario = cur.fetchone()
        if not usuario or usuario["company_id"] != current_user.company_id:
            flash("Usuário não encontrado.", "warning")
            return redirect(url_for("usuarios.listar_usuarios"))

        senha_temporaria = secrets.token_urlsafe(6)[:8]
        cur.execute("UPDATE usuarios SET senha=%s WHERE id=%s", (generate_password_hash(senha_temporaria), id))
        conn.commit()

        session["senha_resetada"] = {"usuario": usuario["username"], "senha": senha_temporaria}
        return redirect(url_for("usuarios.senha_resetada"))
    finally:
        cur.close()
        conn.close()


@usuarios_bp.route("/senha-resetada")
@login_required
@requer_permissao(GERENCIAR_USUARIOS)
def senha_resetada():
    dados = session.pop("senha_resetada", None)
    if not dados:
        return redirect(url_for("usuarios.listar_usuarios"))
    return render_template("senha_resetada.html", dados=dados)
