import datetime as dt

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash

from database import get_db_connection
from permissions import requer_admin_plataforma
from planos import PRECO_PLANO
from text_utils import slugify

admin_plataforma_bp = Blueprint("admin_plataforma", __name__, url_prefix="/admin-plataforma")

PLANOS_DISPONIVEIS = ("basico", "profissional", "enterprise")
STATUS_DISPONIVEIS = ("ativo", "bloqueado", "trial")


def _gerar_slug_unico(cur, nome):
    cur.execute("SELECT slug FROM companies WHERE slug IS NOT NULL")
    usados = {r["slug"] for r in cur.fetchall()}
    base = slugify(nome)
    slug = base
    contador = 2
    while slug in usados:
        slug = f"{base}-{contador}"
        contador += 1
    return slug


# ==== Dashboard: único lugar do sistema que lê todas as companies sem filtro ====
@admin_plataforma_bp.route("/")
@login_required
@requer_admin_plataforma
def dashboard():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT c.id, c.nome, c.slug, c.plano, c.status, c.created_at,
                   c.limite_usuarios, c.limite_equipamentos, c.limite_filiais,
                   c.data_inicio_trial, c.data_bloqueio,
                   (SELECT COUNT(*) FROM usuarios u WHERE u.company_id = c.id) AS usuarios_usados,
                   (SELECT COUNT(*) FROM equipment_items ei WHERE ei.company_id = c.id) AS equipamentos_usados,
                   (SELECT COUNT(*) FROM branches b WHERE b.company_id = c.id) AS filiais_usadas
            FROM companies c
            ORDER BY c.created_at DESC
        """)
        empresas = cur.fetchall()

        total_ativas = sum(1 for e in empresas if e["status"] == "ativo")
        total_bloqueadas = sum(1 for e in empresas if e["status"] == "bloqueado")
        mrr = sum(PRECO_PLANO.get(e["plano"], 0) for e in empresas if e["status"] == "ativo")

        hoje = dt.date.today()
        inicio_mes = hoje.replace(day=1)

        cur.execute("SELECT COUNT(*) AS n FROM companies WHERE created_at >= %s", (inicio_mes,))
        novas_no_mes = cur.fetchone()["n"]

        cur.execute("""
            SELECT COUNT(*) AS n FROM companies
            WHERE status = 'bloqueado' AND status_atualizado_em >= %s
        """, (inicio_mes,))
        churn_no_mes = cur.fetchone()["n"]

        indicadores = {
            "total_ativas": total_ativas,
            "total_bloqueadas": total_bloqueadas,
            "mrr": mrr,
            "novas_no_mes": novas_no_mes,
            "churn_no_mes": churn_no_mes,
        }

        return render_template(
            "admin_plataforma_dashboard.html", empresas=empresas, indicadores=indicadores,
            planos=PLANOS_DISPONIVEIS, status_opcoes=STATUS_DISPONIVEIS,
        )
    finally:
        cur.close()
        conn.close()


# ==== Criar empresa nova (+ filial inicial + primeiro usuário) ====
@admin_plataforma_bp.route("/empresas/nova", methods=["GET", "POST"])
@login_required
@requer_admin_plataforma
def nova_empresa():
    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        plano = (request.form.get("plano") or "").strip()
        limite_usuarios = request.form.get("limite_usuarios", type=int)
        limite_equipamentos = request.form.get("limite_equipamentos", type=int)
        limite_filiais = request.form.get("limite_filiais", type=int)

        admin_username = (request.form.get("admin_username") or "").strip()
        admin_email = (request.form.get("admin_email") or "").strip()
        admin_senha = request.form.get("admin_senha") or ""

        if not nome or plano not in PLANOS_DISPONIVEIS:
            flash("Nome da empresa e plano são obrigatórios.", "warning")
            return redirect(url_for("admin_plataforma.nova_empresa"))
        if not admin_username or not admin_email or len(admin_senha) < 6:
            flash("Informe usuário, e-mail e senha (mín. 6 caracteres) do administrador inicial.", "warning")
            return redirect(url_for("admin_plataforma.nova_empresa"))

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            slug = _gerar_slug_unico(cur, nome)
            cur.execute("""
                INSERT INTO companies (nome, slug, plano, status, limite_usuarios, limite_equipamentos, limite_filiais)
                VALUES (%s, %s, %s, 'ativo', %s, %s, %s)
                RETURNING id
            """, (nome, slug, plano, limite_usuarios, limite_equipamentos, limite_filiais))
            company_id = cur.fetchone()["id"]

            cur.execute("INSERT INTO branches (company_id, nome) VALUES (%s, 'Matriz')", (company_id,))

            cur.execute("SELECT id FROM usuarios WHERE username=%s OR email=%s", (admin_username, admin_email))
            if cur.fetchone():
                conn.rollback()
                flash("Já existe um usuário com esse username ou e-mail.", "warning")
                return redirect(url_for("admin_plataforma.nova_empresa"))

            cur.execute("""
                INSERT INTO usuarios (username, email, senha, role, company_id, is_admin)
                VALUES (%s, %s, %s, 'admin_locadora', %s, FALSE)
            """, (admin_username, admin_email, generate_password_hash(admin_senha), company_id))

            conn.commit()
            flash(f"Empresa '{nome}' criada! Catálogo público em /catalogo/{slug}", "success")
            return redirect(url_for("admin_plataforma.dashboard"))
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao criar empresa: {e}", "danger")
            return redirect(url_for("admin_plataforma.nova_empresa"))
        finally:
            cur.close()
            conn.close()

    return render_template("admin_plataforma_empresa_nova.html", planos=PLANOS_DISPONIVEIS)


# ==== Mudar status (ativo/bloqueado/trial) ====
@admin_plataforma_bp.route("/empresas/<int:id>/status", methods=["POST"])
@login_required
@requer_admin_plataforma
def mudar_status_empresa(id):
    novo_status = (request.form.get("status") or "").strip()
    if novo_status not in STATUS_DISPONIVEIS:
        flash("Status inválido.", "warning")
        return redirect(url_for("admin_plataforma.dashboard"))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE companies SET status=%s, status_atualizado_em=CURRENT_TIMESTAMP WHERE id=%s",
            (novo_status, id),
        )
        conn.commit()
        flash("Status da empresa atualizado.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao atualizar status: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("admin_plataforma.dashboard"))


# ==== Mudar plano + limites ====
@admin_plataforma_bp.route("/empresas/<int:id>/plano", methods=["POST"])
@login_required
@requer_admin_plataforma
def mudar_plano_empresa(id):
    plano = (request.form.get("plano") or "").strip()
    limite_usuarios = request.form.get("limite_usuarios", type=int)
    limite_equipamentos = request.form.get("limite_equipamentos", type=int)
    limite_filiais = request.form.get("limite_filiais", type=int)

    if plano not in PLANOS_DISPONIVEIS:
        flash("Plano inválido.", "warning")
        return redirect(url_for("admin_plataforma.dashboard"))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE companies SET plano=%s, limite_usuarios=%s, limite_equipamentos=%s, limite_filiais=%s
            WHERE id=%s
        """, (plano, limite_usuarios, limite_equipamentos, limite_filiais, id))
        conn.commit()
        flash("Plano da empresa atualizado.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao atualizar plano: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("admin_plataforma.dashboard"))


# ==== Período grátis (trial com data de bloqueio futura) ====
@admin_plataforma_bp.route("/empresas/<int:id>/periodo-gratis", methods=["POST"])
@login_required
@requer_admin_plataforma
def periodo_gratis_empresa(id):
    dias = request.form.get("dias", type=int) or 30
    data_bloqueio = dt.date.today() + dt.timedelta(days=dias)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE companies
            SET status='trial', status_atualizado_em=CURRENT_TIMESTAMP,
                data_inicio_trial=COALESCE(data_inicio_trial, CURRENT_DATE), data_bloqueio=%s
            WHERE id=%s
        """, (data_bloqueio, id))
        conn.commit()
        flash(f"Período grátis concedido até {data_bloqueio}.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao conceder período grátis: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("admin_plataforma.dashboard"))


# ==== Confirmar pagamento manual (cobrança ainda não é automática) ====
@admin_plataforma_bp.route("/empresas/<int:id>/confirmar-pagamento", methods=["POST"])
@login_required
@requer_admin_plataforma
def confirmar_pagamento_empresa(id):
    proxima_data_bloqueio = dt.date.today() + dt.timedelta(days=30)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE companies
            SET status='ativo', status_atualizado_em=CURRENT_TIMESTAMP, data_bloqueio=%s
            WHERE id=%s
        """, (proxima_data_bloqueio, id))
        conn.commit()
        flash(f"Pagamento confirmado. Empresa ativa até {proxima_data_bloqueio} (renovar antes disso).", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao confirmar pagamento: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("admin_plataforma.dashboard"))
