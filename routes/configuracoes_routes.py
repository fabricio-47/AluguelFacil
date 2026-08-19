import json

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db_connection
from permissions import requer_role, CARGOS_CUSTOMIZAVEIS, GRUPOS_PERMISSOES, LABEL_PERMISSAO, PERMISSOES_POR_ROLE
from asaas_config import cifrar
from validators import validar_forca_senha

configuracoes_bp = Blueprint("configuracoes", __name__, url_prefix="/configuracoes")

AMBIENTES_ASAAS = ("sandbox", "producao")


@configuracoes_bp.route("/", methods=["GET", "POST"])
@login_required
@requer_role("super_admin", "admin_locadora")
def pagina_configuracoes():
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        ambiente = request.form.get("ambiente")
        if ambiente not in AMBIENTES_ASAAS:
            cur.close()
            conn.close()
            flash("Ambiente inválido.", "warning")
            return redirect(url_for("configuracoes.pagina_configuracoes"))

        api_key_nova = (request.form.get("api_key") or "").strip()
        webhook_secret_novo = (request.form.get("webhook_secret") or "").strip()

        try:
            cur.execute("SELECT api_key_cifrada, webhook_secret_cifrado FROM config_asaas WHERE company_id=%s", (current_user.company_id,))
            atual = cur.fetchone()

            # Campo em branco = mantém o valor já salvo (nunca apaga sem querer).
            api_key_cifrada = cifrar(api_key_nova) if api_key_nova else (atual["api_key_cifrada"] if atual else None)
            webhook_secret_cifrado = cifrar(webhook_secret_novo) if webhook_secret_novo else (atual["webhook_secret_cifrado"] if atual else None)

            cur.execute("""
                INSERT INTO config_asaas (company_id, api_key_cifrada, webhook_secret_cifrado, ambiente, ativo)
                VALUES (%s, %s, %s, %s, TRUE)
                ON CONFLICT (company_id) DO UPDATE SET
                    api_key_cifrada = EXCLUDED.api_key_cifrada,
                    webhook_secret_cifrado = EXCLUDED.webhook_secret_cifrado,
                    ambiente = EXCLUDED.ambiente,
                    ativo = TRUE
            """, (current_user.company_id, api_key_cifrada, webhook_secret_cifrado, ambiente))
            conn.commit()
            flash("Configuração do Asaas salva com sucesso!", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao salvar configuração: {e}", "danger")
        finally:
            cur.close()
            conn.close()

        return redirect(url_for("configuracoes.pagina_configuracoes"))

    cur.execute("SELECT * FROM config_asaas WHERE company_id=%s", (current_user.company_id,))
    config = cur.fetchone()

    cur.execute(
        "SELECT role, permissoes FROM permissoes_customizadas WHERE company_id=%s",
        (current_user.company_id,),
    )
    customizadas_por_cargo = {row["role"]: set(row["permissoes"]) for row in cur.fetchall()}

    permissoes_efetivas = {
        cargo: customizadas_por_cargo.get(cargo, set(PERMISSOES_POR_ROLE.get(cargo, ())))
        for cargo in CARGOS_CUSTOMIZAVEIS
    }

    cur.close()
    conn.close()
    return render_template(
        "configuracoes.html",
        config=config,
        ambientes=AMBIENTES_ASAAS,
        cargos=CARGOS_CUSTOMIZAVEIS,
        grupos_permissoes=GRUPOS_PERMISSOES,
        label_permissao=LABEL_PERMISSAO,
        permissoes_efetivas=permissoes_efetivas,
    )


@configuracoes_bp.route("/permissoes", methods=["POST"])
@login_required
@requer_role("super_admin", "admin_locadora")
def salvar_permissoes():
    todas_permissoes = {perm for _, perms in GRUPOS_PERMISSOES for perm in perms}

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        for cargo in CARGOS_CUSTOMIZAVEIS:
            marcadas = request.form.getlist(f"perm__{cargo}")
            marcadas_validas = [p for p in marcadas if p in todas_permissoes]
            cur.execute("""
                INSERT INTO permissoes_customizadas (company_id, role, permissoes)
                VALUES (%s, %s, %s)
                ON CONFLICT (company_id, role) DO UPDATE SET
                    permissoes = EXCLUDED.permissoes
            """, (current_user.company_id, cargo, json.dumps(marcadas_validas)))
        conn.commit()
        flash("Permissões salvas com sucesso!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao salvar permissões: {e}", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("configuracoes.pagina_configuracoes"))


# ==== Trocar a própria senha (qualquer cargo logado) ====
@configuracoes_bp.route("/senha", methods=["GET", "POST"])
@login_required
def trocar_senha():
    if request.method == "POST":
        senha_atual = request.form.get("senha_atual") or ""
        nova_senha = request.form.get("nova_senha") or ""
        confirmacao_senha = request.form.get("confirmacao_senha") or ""

        if not check_password_hash(current_user.senha, senha_atual):
            flash("Senha atual incorreta.", "danger")
            return redirect(url_for("configuracoes.trocar_senha"))

        if nova_senha != confirmacao_senha:
            flash("A nova senha e a confirmação não coincidem.", "warning")
            return redirect(url_for("configuracoes.trocar_senha"))

        senha_valida, erro_senha = validar_forca_senha(nova_senha, [current_user.username, current_user.email])
        if not senha_valida:
            flash(erro_senha, "warning")
            return redirect(url_for("configuracoes.trocar_senha"))

        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("UPDATE usuarios SET senha=%s WHERE id=%s", (generate_password_hash(nova_senha), current_user.id))
            conn.commit()
            flash("Senha alterada com sucesso!", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao alterar senha: {e}", "danger")
        finally:
            cur.close()
            conn.close()

        return redirect(url_for("configuracoes.trocar_senha"))

    return render_template("trocar_senha.html")
