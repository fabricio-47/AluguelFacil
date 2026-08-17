from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from database import get_db_connection
from permissions import requer_role
from asaas_config import cifrar

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
    cur.close()
    conn.close()
    return render_template("configuracoes.html", config=config, ambientes=AMBIENTES_ASAAS)
