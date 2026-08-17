import requests
from flask import Blueprint, render_template, flash, redirect, url_for, request
from flask_login import login_required, current_user
from psycopg2.extras import RealDictCursor
from database import get_db_connection
from config import Config
from permissions import requer_permissao, tem_permissao, VER_CLIENTES, GERENCIAR_CLIENTES

clientes_bp = Blueprint("clientes", __name__, url_prefix="/clientes")

@clientes_bp.route("/", methods=["GET", "POST"])
@login_required
@requer_permissao(VER_CLIENTES)
def listar_clientes():
    if request.method == "POST":
        if not tem_permissao(GERENCIAR_CLIENTES):
            flash("Você não tem permissão para cadastrar clientes.", "danger")
            return redirect(url_for("clientes.listar_clientes"))

        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip()
        telefone = request.form.get("telefone", "").strip()
        cpf = request.form.get("cpf", "").strip()
        endereco = request.form.get("endereco", "").strip()
        data_nascimento = request.form.get("data_nascimento", "").strip()
        observacoes = request.form.get("observacoes", "").strip()

        if not nome or not email or not telefone:
            flash("Nome, email e telefone são obrigatórios.", "warning")
            return redirect(url_for("clientes.listar_clientes"))

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Verifica se cliente já existe localmente pelo CPF ou email
            cur.execute("SELECT id, asaas_id FROM clientes WHERE cpf=%s OR email=%s", (cpf, email))
            cliente_existente = cur.fetchone()

            if cliente_existente:
                flash("Cliente já cadastrado localmente.", "info")
                return redirect(url_for("clientes.listar_clientes"))

            # Busca cliente no Asaas pelo CPF (document) ou email
            headers = {"access_token": Config.ASAAS_API_KEY}
            params = {}
            if cpf:
                params["cpfCnpj"] = cpf
            else:
                params["email"] = email

            resp = requests.get(f"{Config.ASAAS_BASE_URL}/customers", headers=headers, params=params, timeout=30)
            if resp.status_code != 200:
                flash(f"Erro ao consultar Asaas: {resp.status_code}", "danger")
                return redirect(url_for("clientes.listar_clientes"))

            data = resp.json()
            asaas_id = None
            if data.get("data"):
                # Cliente encontrado no Asaas
                asaas_id = data["data"][0]["id"]

            # Se não encontrou no Asaas, cria novo cliente
            if not asaas_id:
                cliente_payload = {
                    "name": nome,
                    "email": email,
                    "phone": telefone,
                    "cpfCnpj": cpf,
                    "externalReference": None,
                    "postalCode": None,
                    "address": endereco,
                    "notificationDisabled": False,
                }
                resp_create = requests.post(f"{Config.ASAAS_BASE_URL}/customers", headers=headers, json=cliente_payload, timeout=30)
                if resp_create.status_code not in (200, 201):
                    flash(f"Erro ao criar cliente no Asaas: {resp_create.status_code}", "danger")
                    return redirect(url_for("clientes.listar_clientes"))
                asaas_id = resp_create.json().get("id")

            # Salva cliente local com o asaas_id
            cur.execute("""
                INSERT INTO clientes (nome, email, telefone, cpf, endereco, data_nascimento, observacoes, asaas_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
            """, (nome, email, telefone, cpf, endereco, data_nascimento or None, observacoes or None, asaas_id))
            novo_cliente_id = cur.fetchone()["id"]

            # Todo cliente novo entra no pipeline de vendas na etapa inicial.
            cur.execute("""
                INSERT INTO pipeline_clientes (cliente_id, etapa, usuario_responsavel)
                VALUES (%s, 'novo_cliente', %s)
            """, (novo_cliente_id, int(current_user.id)))

            conn.commit()

            flash("Cliente cadastrado com sucesso e integrado ao Asaas.", "success")
            return redirect(url_for("clientes.listar_clientes"))

        except Exception as e:
            conn.rollback()
            print("Erro ao criar cliente:", e)
            flash("Erro inesperado ao criar cliente.", "danger")
            return redirect(url_for("clientes.listar_clientes"))
        finally:
            cur.close()
            conn.close()

    # GET: lista clientes e renderiza o template clientes.html
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM clientes ORDER BY nome ASC")
        clientes = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return render_template("clientes.html", clientes=clientes)


@clientes_bp.route("/editar/<int:id>", methods=["GET", "POST"])
@login_required
@requer_permissao(GERENCIAR_CLIENTES)
def editar_cliente(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip()
        telefone = request.form.get("telefone", "").strip()
        cpf = request.form.get("cpf", "").strip()
        endereco = request.form.get("endereco", "").strip()
        data_nascimento = request.form.get("data_nascimento", "").strip()
        observacoes = request.form.get("observacoes", "").strip()

        try:
            cur.execute("""
                UPDATE clientes SET nome=%s, email=%s, telefone=%s, cpf=%s, endereco=%s,
                data_nascimento=%s, observacoes=%s WHERE id=%s
            """, (nome, email, telefone, cpf, endereco, data_nascimento or None, observacoes or None, id))
            conn.commit()
            flash("Cliente atualizado com sucesso.", "success")
            return redirect(url_for("clientes.listar_clientes"))
        except Exception as e:
            conn.rollback()
            print("Erro ao atualizar cliente:", e)
            flash("Erro ao atualizar cliente.", "danger")
            return redirect(url_for("clientes.editar_cliente", id=id))
        finally:
            cur.close()
            conn.close()

    # GET: busca cliente para preencher formulário
    try:
        cur.execute("SELECT * FROM clientes WHERE id=%s", (id,))
        cliente = cur.fetchone()
        if not cliente:
            flash("Cliente não encontrado.", "warning")
            return redirect(url_for("clientes.listar_clientes"))
    finally:
        cur.close()
        conn.close()

    return render_template("editar_cliente.html", cliente=cliente)