import os
import time

import requests
from flask import Blueprint, render_template, flash, redirect, url_for, request, current_app, send_from_directory, jsonify, abort
from flask_login import login_required, current_user
from psycopg2.extras import RealDictCursor
from werkzeug.utils import secure_filename
from database import get_db_connection
from config import Config
from permissions import requer_permissao, tem_permissao, VER_CLIENTES, GERENCIAR_CLIENTES
from asaas_config import obter_config_asaas
from cliente_status import cliente_precisa_atualizar_comprovante

clientes_bp = Blueprint("clientes", __name__, url_prefix="/clientes")

# Os 4 slots de imagem do cadastro do cliente: nome do campo no form -> coluna no banco.
DOCUMENTO_CAMPOS = {
    "doc_frente": "doc_frente_arquivo",
    "doc_verso": "doc_verso_arquivo",
    "comprovante_residencia": "comprovante_residencia_arquivo",
    "foto_cliente": "foto_cliente_arquivo",
}
ALLOWED_IMG_EXT = {"png", "jpg", "jpeg"}
# Só "foto_cliente" aceita PDF além de imagem (ex: retrato digitalizado).
EXTENSOES_POR_CAMPO = {
    "doc_frente": ALLOWED_IMG_EXT,
    "doc_verso": ALLOWED_IMG_EXT,
    "comprovante_residencia": ALLOWED_IMG_EXT,
    "foto_cliente": ALLOWED_IMG_EXT | {"pdf"},
}

# Tipos fixos para os anexos extras (tabela cliente_documentos) — lista
# fechada + "outro" com descrição livre, separado dos 4 slots fixos acima.
TIPOS_DOCUMENTO_EXTRA = {
    "rg": "RG",
    "cpf": "CPF",
    "comprovante_residencia": "Comprovante de Residência",
    "comprovante_renda": "Comprovante de Renda",
    "contrato": "Contrato",
    "outro": "Outro",
}
ALLOWED_DOC_EXTRA_EXT = ALLOWED_IMG_EXT | {"pdf"}


def _allowed_img(filename, campo):
    permitidas = EXTENSOES_POR_CAMPO.get(campo, ALLOWED_IMG_EXT)
    return "." in filename and filename.rsplit(".", 1)[1].lower() in permitidas


def _allowed_doc_extra(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_DOC_EXTRA_EXT


def _unique_filename(cliente_id, filename):
    _, ext = os.path.splitext(filename)
    ts = int(time.time() * 1000)
    return f"{cliente_id}_{ts}{ext.lower()}"


def _pasta_documentos():
    pasta = os.path.join(current_app.config["UPLOAD_FOLDER"], "clientes")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def _remover_arquivo(filename):
    if not filename:
        return
    caminho = os.path.join(_pasta_documentos(), filename)
    if os.path.exists(caminho):
        try:
            os.remove(caminho)
        except OSError:
            pass

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
            # Verifica se cliente já existe localmente pelo CPF ou email, dentro da MESMA empresa.
            # (Escopado por company_id: duas empresas diferentes podem ter o mesmo cliente
            # cadastrado independentemente, sem uma bloquear a outra.)
            cur.execute(
                "SELECT id, asaas_id FROM clientes WHERE (cpf=%s OR email=%s) AND company_id=%s",
                (cpf, email, current_user.company_id),
            )
            cliente_existente = cur.fetchone()

            if cliente_existente:
                flash("Cliente já cadastrado localmente.", "info")
                return redirect(url_for("clientes.listar_clientes"))

            # Busca cliente no Asaas pelo CPF (document) ou email
            asaas = obter_config_asaas(cur, current_user.company_id)
            headers = {"access_token": asaas["api_key"]}
            params = {}
            if cpf:
                params["cpfCnpj"] = cpf
            else:
                params["email"] = email

            resp = requests.get(f"{asaas['base_url']}/customers", headers=headers, params=params, timeout=30)
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
                resp_create = requests.post(f"{asaas['base_url']}/customers", headers=headers, json=cliente_payload, timeout=30)
                if resp_create.status_code not in (200, 201):
                    flash(f"Erro ao criar cliente no Asaas: {resp_create.status_code}", "danger")
                    return redirect(url_for("clientes.listar_clientes"))
                asaas_id = resp_create.json().get("id")

            # Salva cliente local com o asaas_id, vinculado à empresa do usuário logado.
            cur.execute("""
                INSERT INTO clientes (nome, email, telefone, cpf, endereco, data_nascimento, observacoes, asaas_id, company_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
            """, (nome, email, telefone, cpf, endereco, data_nascimento or None, observacoes or None, asaas_id, current_user.company_id))
            novo_cliente_id = cur.fetchone()["id"]

            # Todo cliente novo entra no pipeline de vendas na etapa inicial.
            cur.execute("""
                INSERT INTO pipeline_clientes (cliente_id, etapa, usuario_responsavel)
                VALUES (%s, 'novo_cliente', %s)
            """, (novo_cliente_id, int(current_user.id)))

            for campo_form, coluna in DOCUMENTO_CAMPOS.items():
                f = request.files.get(campo_form)
                if f and f.filename and _allowed_img(f.filename, campo_form):
                    filename = _unique_filename(novo_cliente_id, secure_filename(f.filename))
                    f.save(os.path.join(_pasta_documentos(), filename))
                    if campo_form == "comprovante_residencia":
                        cur.execute(
                            f"UPDATE clientes SET {coluna}=%s, comprovante_residencia_atualizado_em=NOW() WHERE id=%s",
                            (filename, novo_cliente_id),
                        )
                    else:
                        cur.execute(f"UPDATE clientes SET {coluna}=%s WHERE id=%s", (filename, novo_cliente_id))

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

    # GET: lista clientes da empresa logada e renderiza o template clientes.html
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM clientes WHERE company_id=%s ORDER BY nome ASC", (current_user.company_id,))
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
            cur.execute(
                f"SELECT {', '.join(DOCUMENTO_CAMPOS.values())} FROM clientes WHERE id=%s AND company_id=%s",
                (id, current_user.company_id),
            )
            atuais = cur.fetchone()
            if not atuais:
                flash("Cliente não encontrado.", "danger")
                return redirect(url_for("clientes.listar_clientes"))

            cur.execute("""
                UPDATE clientes SET nome=%s, email=%s, telefone=%s, cpf=%s, endereco=%s,
                data_nascimento=%s, observacoes=%s WHERE id=%s AND company_id=%s
            """, (nome, email, telefone, cpf, endereco, data_nascimento or None, observacoes or None, id, current_user.company_id))

            for campo_form, coluna in DOCUMENTO_CAMPOS.items():
                f = request.files.get(campo_form)
                if f and f.filename and _allowed_img(f.filename, campo_form):
                    _remover_arquivo(atuais[coluna])
                    filename = _unique_filename(id, secure_filename(f.filename))
                    f.save(os.path.join(_pasta_documentos(), filename))
                    if campo_form == "comprovante_residencia":
                        cur.execute(
                            f"UPDATE clientes SET {coluna}=%s, comprovante_residencia_atualizado_em=NOW() WHERE id=%s AND company_id=%s",
                            (filename, id, current_user.company_id),
                        )
                    else:
                        cur.execute(
                            f"UPDATE clientes SET {coluna}=%s WHERE id=%s AND company_id=%s",
                            (filename, id, current_user.company_id),
                        )

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
        cur.execute("SELECT * FROM clientes WHERE id=%s AND company_id=%s", (id, current_user.company_id))
        cliente = cur.fetchone()
        if not cliente:
            flash("Cliente não encontrado.", "warning")
            return redirect(url_for("clientes.listar_clientes"))
    finally:
        cur.close()
        conn.close()

    return render_template("editar_cliente.html", cliente=cliente)


@clientes_bp.route("/<int:id>/status-cadastral")
@login_required
@requer_permissao(VER_CLIENTES)
def status_cadastral(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT id FROM clientes WHERE id=%s AND company_id=%s", (id, current_user.company_id))
        if not cur.fetchone():
            return jsonify({"erro": "Cliente não encontrado."}), 404
        precisa = cliente_precisa_atualizar_comprovante(cur, id)
    finally:
        cur.close()
        conn.close()
    return jsonify({"precisa_atualizar_comprovante": precisa})


@clientes_bp.route("/<int:cliente_id>/documentos/<filename>")
@login_required
@requer_permissao(VER_CLIENTES)
def uploaded_documento(cliente_id, filename):
    """Serve um documento de cliente. Exige cliente_id na URL (não só o
    filename) para validar que o cliente pertence à empresa do usuário logado
    antes de servir qualquer arquivo — sem isso, o nome do arquivo sozinho
    (previsível: {cliente_id}_{timestamp}.ext) permitia acesso cruzado entre
    empresas."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            "SELECT id FROM clientes WHERE id=%s AND company_id=%s",
            (cliente_id, current_user.company_id),
        )
        if not cur.fetchone():
            abort(404)
    finally:
        cur.close()
        conn.close()
    return send_from_directory(_pasta_documentos(), filename)


@clientes_bp.route("/<int:id>/documentos/<campo>/excluir", methods=["POST"])
@login_required
@requer_permissao(GERENCIAR_CLIENTES)
def excluir_documento(id, campo):
    coluna = DOCUMENTO_CAMPOS.get(campo)
    if not coluna:
        flash("Documento inválido.", "warning")
        return redirect(url_for("clientes.editar_cliente", id=id))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(f"SELECT {coluna} FROM clientes WHERE id=%s AND company_id=%s", (id, current_user.company_id))
        atual = cur.fetchone()
        if not atual:
            flash("Cliente não encontrado.", "danger")
            return redirect(url_for("clientes.listar_clientes"))
        if atual[coluna]:
            _remover_arquivo(atual[coluna])
            cur.execute(f"UPDATE clientes SET {coluna}=NULL WHERE id=%s AND company_id=%s", (id, current_user.company_id))
            conn.commit()
            flash("Documento removido.", "info")
        else:
            flash("Não há documento nesse campo.", "warning")
    except Exception as e:
        conn.rollback()
        print("Erro ao remover documento do cliente:", e)
        flash("Erro ao remover documento.", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("clientes.editar_cliente", id=id))


# ======================
# Documentos extras do cliente (upload múltiplo/lista/excluir)
# ======================
@clientes_bp.route("/<int:cliente_id>/documentos-extras", methods=["GET", "POST"])
@login_required
@requer_permissao(VER_CLIENTES)
def cliente_documentos_extras(cliente_id):
    if request.method == "POST" and not tem_permissao(GERENCIAR_CLIENTES):
        flash("Você não tem permissão para anexar documentos de clientes.", "danger")
        return redirect(url_for("clientes.cliente_documentos_extras", cliente_id=cliente_id))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Valida a posse do cliente pela empresa ANTES de qualquer leitura ou
    # escrita, tanto no GET quanto no POST — sem isso, qualquer empresa
    # conseguia listar e anexar documentos em cliente de outra empresa.
    cur.execute("SELECT id, nome FROM clientes WHERE id=%s AND company_id=%s", (cliente_id, current_user.company_id))
    cliente = cur.fetchone()
    if not cliente:
        cur.close()
        conn.close()
        flash("Cliente não encontrado.", "warning")
        return redirect(url_for("clientes.listar_clientes"))

    if request.method == "POST":
        tipo = request.form.get("tipo", "").strip()
        tipo_outro = request.form.get("tipo_outro", "").strip()
        files = request.files.getlist("arquivos")

        if tipo not in TIPOS_DOCUMENTO_EXTRA:
            cur.close()
            conn.close()
            flash("Selecione um tipo de documento válido.", "warning")
            return redirect(url_for("clientes.cliente_documentos_extras", cliente_id=cliente_id))
        if tipo == "outro" and not tipo_outro:
            cur.close()
            conn.close()
            flash('Descreva o tipo do documento quando escolher "Outro".', "warning")
            return redirect(url_for("clientes.cliente_documentos_extras", cliente_id=cliente_id))
        if not files or files == [None]:
            cur.close()
            conn.close()
            flash("Nenhum arquivo selecionado.", "warning")
            return redirect(url_for("clientes.cliente_documentos_extras", cliente_id=cliente_id))

        count_ok = 0
        try:
            for f in files:
                if not f or f.filename == "":
                    continue
                if not _allowed_doc_extra(f.filename):
                    continue
                filename = _unique_filename(cliente_id, secure_filename(f.filename))
                f.save(os.path.join(_pasta_documentos(), filename))

                cur.execute("""
                    INSERT INTO cliente_documentos (cliente_id, tipo, tipo_outro, arquivo)
                    VALUES (%s, %s, %s, %s)
                """, (cliente_id, tipo, tipo_outro if tipo == "outro" else None, filename))
                count_ok += 1

            conn.commit()
            if count_ok > 0:
                flash(f"{count_ok} documento(s) enviado(s) com sucesso!", "success")
            else:
                flash("Nenhum arquivo válido foi enviado.", "warning")
        except Exception as e:
            conn.rollback()
            print("Erro ao enviar documentos extras do cliente:", e)
            flash("Erro ao enviar documentos.", "danger")
        finally:
            cur.close()
            conn.close()

        return redirect(url_for("clientes.cliente_documentos_extras", cliente_id=cliente_id))

    try:
        cur.execute(
            "SELECT id, tipo, tipo_outro, arquivo, data_upload FROM cliente_documentos "
            "WHERE cliente_id=%s ORDER BY id DESC",
            (cliente_id,),
        )
        documentos = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return render_template(
        "cliente_documentos.html",
        cliente=cliente,
        documentos=documentos,
        tipos=TIPOS_DOCUMENTO_EXTRA,
    )


@clientes_bp.route("/<int:cliente_id>/documentos-extras/<int:doc_id>/excluir", methods=["POST"])
@login_required
@requer_permissao(GERENCIAR_CLIENTES)
def excluir_documento_extra(cliente_id, doc_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        # Valida que o cliente pertence à empresa antes de tocar no documento.
        cur.execute("SELECT id FROM clientes WHERE id=%s AND company_id=%s", (cliente_id, current_user.company_id))
        if not cur.fetchone():
            flash("Cliente não encontrado.", "warning")
            return redirect(url_for("clientes.listar_clientes"))

        cur.execute(
            "SELECT arquivo FROM cliente_documentos WHERE id=%s AND cliente_id=%s",
            (doc_id, cliente_id),
        )
        row = cur.fetchone()
        if row:
            _remover_arquivo(row["arquivo"])
            cur.execute("DELETE FROM cliente_documentos WHERE id=%s", (doc_id,))
            conn.commit()
            flash("Documento removido.", "info")
        else:
            flash("Documento não encontrado.", "warning")
    except Exception as e:
        conn.rollback()
        print("Erro ao remover documento extra do cliente:", e)
        flash("Erro ao remover documento.", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("clientes.cliente_documentos_extras", cliente_id=cliente_id))
