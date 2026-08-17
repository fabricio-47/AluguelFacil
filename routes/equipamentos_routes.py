import io
import os
import time
import psycopg2
import qrcode
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_from_directory, current_app, Response
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from database import get_db_connection
from permissions import requer_permissao, tem_permissao, VER_EQUIPAMENTOS, GERENCIAR_EQUIPAMENTOS, ALTERAR_STATUS_EQUIPAMENTO
from estoque import registrar_movimentacao
from planos import verificar_limite
from auditoria import registrar_auditoria

equipamentos_bp = Blueprint("equipamentos", __name__, url_prefix="/equipamentos")

# ======================
# Helpers
# ======================
ALLOWED_DOC_EXT = {"pdf", "png", "jpg", "jpeg"}
ALLOWED_IMG_EXT = {"png", "jpg", "jpeg"}

# "alugado" não entra aqui de propósito: só o fluxo de criar/cancelar locação pode setar esse status.
STATUS_EDITAVEIS = {"disponivel", "reservado", "manutencao", "danificado", "perdido", "inativo"}

def _allowed(filename, allowed):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed

def _unique_filename(prefix_id, filename):
    name, ext = os.path.splitext(filename)
    ts = int(time.time() * 1000)
    return f"{prefix_id}_{ts}{ext.lower()}"

def _campos_formulario(form):
    """Extrai e normaliza os campos genéricos de equipamento vindos do form."""
    status = form.get("status") or "disponivel"
    if status not in STATUS_EDITAVEIS:
        status = "disponivel"
    disponivel = status == "disponivel"
    return {
        "categoria_id": form.get("categoria_id", type=int) or None,
        "codigo_interno": (form.get("codigo_interno") or "").strip().upper() or None,
        "sku": (form.get("sku") or "").strip() or None,
        "codigo_barras": (form.get("codigo_barras") or "").strip() or None,
        "nome": (form.get("nome") or "").strip(),
        "marca": (form.get("marca") or "").strip() or None,
        "modelo": (form.get("modelo") or "").strip() or None,
        "numero_serie": (form.get("numero_serie") or "").strip() or None,
        "ano": form.get("ano") or None,
        "descricao": (form.get("descricao") or "").strip() or None,
        "valor_compra": form.get("valor_compra") or None,
        "valor_diaria": form.get("valor_diaria") or None,
        "valor_semanal": form.get("valor_semanal") or None,
        "valor_quinzenal": form.get("valor_quinzenal") or None,
        "valor_mensal": form.get("valor_mensal") or None,
        "valor_hora": form.get("valor_hora") or None,
        "caucao": form.get("caucao") or None,
        "status": status,
        "quantidade_disponivel": 1 if disponivel else 0,
    }

# ======================
# Listar e cadastrar equipamentos
# ======================
@equipamentos_bp.route("/", methods=["GET", "POST"])
@login_required
@requer_permissao(VER_EQUIPAMENTOS)
def listar_equipamentos():
    if request.method == "POST" and not tem_permissao(GERENCIAR_EQUIPAMENTOS):
        flash("Você não tem permissão para cadastrar equipamentos.", "danger")
        return redirect(url_for("equipamentos.listar_equipamentos"))

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        campos = _campos_formulario(request.form)
        if not campos["nome"]:
            cur.close()
            conn.close()
            flash("Nome do equipamento é obrigatório.", "warning")
            return redirect(url_for("equipamentos.listar_equipamentos"))

        limite = verificar_limite(cur, current_user.company_id, "limite_equipamentos", "equipment_items")
        if not limite["dentro_do_limite"]:
            cur.close()
            conn.close()
            flash(
                f"Limite de equipamentos do plano atingido ({limite['usado']}/{limite['limite']}). "
                f"Fale com o suporte pra aumentar o limite.",
                "danger",
            )
            return redirect(url_for("equipamentos.listar_equipamentos"))

        # company_id/branch_id não têm form field (equipamento nasce na filial
        # padrão da empresa, depois pode ser transferido em filiais.transferir_equipamento).
        # Setar explícito aqui é necessário — o DEFAULT de coluna do banco é fixo
        # na company/filial originais da Fase 1, e passaria a atribuir equipamentos
        # de QUALQUER empresa nova à company 1 por engano.
        cur.execute("SELECT id FROM branches WHERE company_id=%s ORDER BY id ASC LIMIT 1", (current_user.company_id,))
        branch_row = cur.fetchone()
        if not branch_row:
            cur.close()
            conn.close()
            flash("Cadastre uma filial antes de cadastrar equipamentos.", "warning")
            return redirect(url_for("equipamentos.listar_equipamentos"))
        campos["company_id"] = current_user.company_id
        campos["branch_id"] = branch_row["id"]

        try:
            cur.execute("""
                INSERT INTO equipment_items (
                    company_id, branch_id, categoria_id, codigo_interno, sku, codigo_barras, nome, marca, modelo,
                    numero_serie, ano, descricao, valor_compra, valor_diaria, valor_semanal,
                    valor_quinzenal, valor_mensal, valor_hora, caucao, status, quantidade_disponivel
                ) VALUES (%(company_id)s,%(branch_id)s,%(categoria_id)s,%(codigo_interno)s,%(sku)s,%(codigo_barras)s,%(nome)s,%(marca)s,
                    %(modelo)s,%(numero_serie)s,%(ano)s,%(descricao)s,%(valor_compra)s,%(valor_diaria)s,
                    %(valor_semanal)s,%(valor_quinzenal)s,%(valor_mensal)s,%(valor_hora)s,%(caucao)s,
                    %(status)s,%(quantidade_disponivel)s)
                RETURNING id
            """, campos)
            equipamento_id = cur.fetchone()["id"]

            foto = request.files.get("foto")
            if foto and foto.filename and _allowed(foto.filename, ALLOWED_IMG_EXT):
                pasta = os.path.join(current_app.config["UPLOAD_FOLDER"], "motos")
                os.makedirs(pasta, exist_ok=True)
                filename = _unique_filename(equipamento_id, secure_filename(foto.filename))
                foto.save(os.path.join(pasta, filename))
                cur.execute("UPDATE equipment_items SET foto=%s WHERE id=%s", (filename, equipamento_id))

            registrar_movimentacao(cur, equipamento_id, "entrada", "Cadastro de novo equipamento", int(current_user.id))

            conn.commit()
            flash("Equipamento cadastrado com sucesso!", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao cadastrar equipamento: {e}", "danger")
        finally:
            cur.close()
            conn.close()

        return redirect(url_for("equipamentos.listar_equipamentos"))

    cur.execute("""
        SELECT ei.id, ei.codigo_interno, ei.nome, ei.marca, ei.modelo, ei.ano, ei.status,
               ei.foto, ei.documento_arquivo, ec.nome AS categoria_nome
        FROM equipment_items ei
        LEFT JOIN equipment_categories ec ON ec.id = ei.categoria_id
        ORDER BY ei.nome
    """)
    equipamentos = cur.fetchall()

    cur.execute("SELECT id, nome FROM equipment_categories ORDER BY nome")
    categorias = cur.fetchall()

    cur.close()
    conn.close()
    return render_template("equipamentos.html", equipamentos=equipamentos, categorias=categorias)

# ======================
# Editar equipamento
# ======================
@equipamentos_bp.route("/<int:id>/editar", methods=["GET", "POST"])
@login_required
@requer_permissao(GERENCIAR_EQUIPAMENTOS)
def editar_equipamento(id):
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        campos = _campos_formulario(request.form)
        if not campos["nome"]:
            flash("Nome do equipamento é obrigatório.", "warning")
        else:
            try:
                cur.execute("SELECT status FROM equipment_items WHERE id=%s", (id,))
                status_anterior_row = cur.fetchone()
                status_anterior = status_anterior_row["status"] if status_anterior_row else None

                cur.execute("""
                    UPDATE equipment_items SET
                        categoria_id=%(categoria_id)s, codigo_interno=%(codigo_interno)s, sku=%(sku)s,
                        codigo_barras=%(codigo_barras)s, nome=%(nome)s, marca=%(marca)s, modelo=%(modelo)s,
                        numero_serie=%(numero_serie)s, ano=%(ano)s, descricao=%(descricao)s,
                        valor_compra=%(valor_compra)s, valor_diaria=%(valor_diaria)s,
                        valor_semanal=%(valor_semanal)s, valor_quinzenal=%(valor_quinzenal)s,
                        valor_mensal=%(valor_mensal)s, valor_hora=%(valor_hora)s, caucao=%(caucao)s,
                        status=%(status)s, quantidade_disponivel=%(quantidade_disponivel)s
                    WHERE id=%(id)s
                """, {**campos, "id": id})

                if status_anterior is not None and status_anterior != campos["status"]:
                    registrar_movimentacao(
                        cur, id, "ajuste",
                        f"Status alterado de '{status_anterior}' para '{campos['status']}' via edição",
                        int(current_user.id),
                    )

                foto = request.files.get("foto")
                if foto and foto.filename and _allowed(foto.filename, ALLOWED_IMG_EXT):
                    pasta = os.path.join(current_app.config["UPLOAD_FOLDER"], "motos")
                    os.makedirs(pasta, exist_ok=True)
                    filename = _unique_filename(id, secure_filename(foto.filename))
                    foto.save(os.path.join(pasta, filename))
                    cur.execute("UPDATE equipment_items SET foto=%s WHERE id=%s", (filename, id))

                conn.commit()
                flash("Equipamento atualizado com sucesso!", "success")
                return redirect(url_for("equipamentos.listar_equipamentos"))
            except Exception as e:
                conn.rollback()
                flash(f"Erro ao atualizar equipamento: {e}", "danger")

    cur.execute("""
        SELECT ei.id, ei.categoria_id, ei.codigo_interno, ei.sku, ei.codigo_barras, ei.nome, ei.marca, ei.modelo,
               ei.numero_serie, ei.ano, ei.descricao, ei.foto, ei.documento_arquivo,
               ei.valor_compra, ei.valor_diaria, ei.valor_semanal, ei.valor_quinzenal, ei.valor_mensal, ei.valor_hora,
               ei.caucao, ei.status, ei.branch_id, b.nome AS filial_nome
        FROM equipment_items ei
        LEFT JOIN branches b ON b.id = ei.branch_id
        WHERE ei.id=%s
    """, (id,))
    equipamento = cur.fetchone()

    cur.execute("SELECT id, nome FROM equipment_categories ORDER BY nome")
    categorias = cur.fetchall()

    cur.close()
    conn.close()
    return render_template(
        "editar_equipamento.html",
        equipamento=equipamento,
        categorias=categorias,
        status_editaveis=sorted(STATUS_EDITAVEIS),
    )

# ======================
# Excluir equipamento
# ======================
@equipamentos_bp.route("/<int:id>/excluir", methods=["POST"])
@login_required
@requer_permissao(GERENCIAR_EQUIPAMENTOS)
def excluir_equipamento(id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM equipment_items WHERE id=%s", (id,))
        conn.commit()
        flash("Equipamento excluído com sucesso!", "info")
    except psycopg2.errors.ForeignKeyViolation as e:
        conn.rollback()
        detalhe = getattr(e.diag, "message_detail", "")
        if detalhe:
            flash(f"Erro ao excluir equipamento: {detalhe}", "danger")
        else:
            flash("Não é possível excluir: o equipamento está vinculado a uma locação.", "danger")
    except Exception as e:
        conn.rollback()
        flash(f"Erro inesperado ao excluir equipamento: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("equipamentos.listar_equipamentos"))

# ======================
# Documento do equipamento (upload/visualização)
# ======================
@equipamentos_bp.route("/<int:equipamento_id>/documento", methods=["GET", "POST"])
@login_required
@requer_permissao(VER_EQUIPAMENTOS)
def equipamento_documento(equipamento_id):
    if request.method == "POST" and not tem_permissao(GERENCIAR_EQUIPAMENTOS):
        flash("Você não tem permissão para enviar documentos de equipamentos.", "danger")
        return redirect(url_for("equipamentos.equipamento_documento", equipamento_id=equipamento_id))

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        if "documento" not in request.files:
            flash("Nenhum arquivo enviado.", "danger")
            return redirect(request.url)

        file = request.files["documento"]
        if file.filename == "":
            flash("Nenhum arquivo selecionado.", "danger")
            return redirect(request.url)

        if not _allowed(file.filename, ALLOWED_DOC_EXT):
            flash("Formato inválido. Envie PDF, PNG, JPG ou JPEG.", "warning")
            return redirect(request.url)

        try:
            filename = secure_filename(file.filename)
            filename = _unique_filename(equipamento_id, filename)
            pasta = os.path.join(current_app.config["UPLOAD_FOLDER"], "contratos")
            os.makedirs(pasta, exist_ok=True)
            file.save(os.path.join(pasta, filename))

            cur.execute("UPDATE equipment_items SET documento_arquivo=%s WHERE id=%s", (filename, equipamento_id))
            conn.commit()
            flash("Documento enviado com sucesso!", "success")
            return redirect(url_for("equipamentos.equipamento_documento", equipamento_id=equipamento_id))
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao enviar documento: {e}", "danger")

    cur.execute("""
        SELECT id, codigo_interno, nome, modelo, documento_arquivo
        FROM equipment_items WHERE id=%s
    """, (equipamento_id,))
    equipamento = cur.fetchone()
    cur.close()
    conn.close()
    return render_template("equipamento_documento.html", equipamento=equipamento)

@equipamentos_bp.route("/<int:equipamento_id>/documento/excluir", methods=["POST"])
@login_required
@requer_permissao(GERENCIAR_EQUIPAMENTOS)
def excluir_documento_equipamento(equipamento_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT documento_arquivo FROM equipment_items WHERE id=%s", (equipamento_id,))
        row = cur.fetchone()
        if row and row["documento_arquivo"]:
            filename = row["documento_arquivo"]
            pasta = os.path.join(current_app.config["UPLOAD_FOLDER"], "contratos")
            filepath = os.path.join(pasta, filename)
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception:
                    pass

        cur.execute("UPDATE equipment_items SET documento_arquivo=NULL WHERE id=%s", (equipamento_id,))
        conn.commit()
        flash("Documento do equipamento removido com sucesso!", "info")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao remover documento: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("equipamentos.equipamento_documento", equipamento_id=equipamento_id))

@equipamentos_bp.route("/documentos/<filename>")
@login_required
@requer_permissao(VER_EQUIPAMENTOS)
def serve_documento_equipamento(filename):
    pasta = os.path.join(current_app.config["UPLOAD_FOLDER"], "contratos")
    return send_from_directory(pasta, filename)

# ======================
# Imagens do equipamento (upload múltiplo/lista/excluir)
# ======================
@equipamentos_bp.route("/<int:equipamento_id>/imagens", methods=["GET", "POST"])
@login_required
@requer_permissao(VER_EQUIPAMENTOS)
def equipamento_imagens(equipamento_id):
    if request.method == "POST" and not tem_permissao(GERENCIAR_EQUIPAMENTOS):
        flash("Você não tem permissão para enviar imagens de equipamentos.", "danger")
        return redirect(url_for("equipamentos.equipamento_imagens", equipamento_id=equipamento_id))

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        files = request.files.getlist("imagens")
        if not files or files == [None]:
            flash("Nenhuma imagem selecionada.", "warning")
            return redirect(request.url)

        pasta = os.path.join(current_app.config["UPLOAD_FOLDER"], "motos")
        os.makedirs(pasta, exist_ok=True)

        count_ok = 0
        try:
            for f in files:
                if not f or f.filename == "":
                    continue
                if not _allowed(f.filename, ALLOWED_IMG_EXT):
                    continue
                filename = secure_filename(f.filename)
                filename = _unique_filename(equipamento_id, filename)
                f.save(os.path.join(pasta, filename))

                cur.execute("""
                    INSERT INTO equipment_item_imagens (equipment_item_id, arquivo)
                    VALUES (%s, %s)
                """, (equipamento_id, filename))
                count_ok += 1

            conn.commit()
            if count_ok > 0:
                flash(f"{count_ok} imagem(ns) enviada(s) com sucesso!", "success")
            else:
                flash("Nenhuma imagem válida foi enviada.", "warning")
            return redirect(url_for("equipamentos.equipamento_imagens", equipamento_id=equipamento_id))
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao enviar imagens: {e}", "danger")

    cur.execute("SELECT id, codigo_interno, nome, modelo, ano FROM equipment_items WHERE id=%s", (equipamento_id,))
    equipamento = cur.fetchone()

    cur.execute(
        "SELECT id, arquivo, data_upload FROM equipment_item_imagens WHERE equipment_item_id=%s ORDER BY id DESC",
        (equipamento_id,),
    )
    imagens = cur.fetchall()

    cur.close()
    conn.close()
    return render_template(
        "equipamento_imagens.html", equipamento=equipamento, imagens=imagens, equipamento_id=equipamento_id
    )

@equipamentos_bp.route("/<int:equipamento_id>/imagens/<int:img_id>/excluir", methods=["POST"])
@login_required
@requer_permissao(GERENCIAR_EQUIPAMENTOS)
def excluir_imagem_equipamento(equipamento_id, img_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT arquivo FROM equipment_item_imagens WHERE id=%s AND equipment_item_id=%s",
            (img_id, equipamento_id),
        )
        row = cur.fetchone()
        if row:
            filename = row["arquivo"]
            pasta = os.path.join(current_app.config["UPLOAD_FOLDER"], "motos")
            filepath = os.path.join(pasta, filename)
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception:
                    pass

            cur.execute("DELETE FROM equipment_item_imagens WHERE id=%s", (img_id,))
            conn.commit()
            flash("Imagem removida!", "info")
        else:
            flash("Imagem não encontrada.", "warning")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao remover imagem: {e}", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("equipamentos.equipamento_imagens", equipamento_id=equipamento_id))

@equipamentos_bp.route("/imagens/<filename>")
@login_required
@requer_permissao(VER_EQUIPAMENTOS)
def serve_imagem_equipamento(filename):
    pasta = os.path.join(current_app.config["UPLOAD_FOLDER"], "motos")
    return send_from_directory(pasta, filename)


# ======================
# QR Code do equipamento (gerado na hora, sem salvar arquivo)
# ======================
@equipamentos_bp.route("/<int:id>/qr.png")
@login_required
@requer_permissao(VER_EQUIPAMENTOS)
def qr_png(id):
    url_destino = url_for("equipamentos.qr_page", id=id, _external=True)
    img = qrcode.make(url_destino)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    headers = {}
    if request.args.get("download"):
        headers["Content-Disposition"] = f"attachment; filename=qrcode_equipamento_{id}.png"
    return Response(buffer.getvalue(), mimetype="image/png", headers=headers)


# ======================
# Tela de scan: histórico + mudança rápida de status
# ======================
@equipamentos_bp.route("/<int:id>/qr", methods=["GET", "POST"])
@login_required
@requer_permissao(VER_EQUIPAMENTOS)
def qr_page(id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, company_id, nome, codigo_interno, sku, status
            FROM equipment_items WHERE id=%s
        """, (id,))
        equipamento = cur.fetchone()
        if not equipamento:
            flash("Equipamento não encontrado.", "warning")
            return redirect(url_for("equipamentos.listar_equipamentos"))

        if request.method == "POST":
            if not tem_permissao(ALTERAR_STATUS_EQUIPAMENTO):
                flash("Você não tem permissão para alterar o status deste equipamento.", "danger")
                return redirect(url_for("equipamentos.qr_page", id=id))

            novo_status = request.form.get("status")
            if novo_status not in STATUS_EDITAVEIS:
                flash("Status inválido.", "warning")
                return redirect(url_for("equipamentos.qr_page", id=id))

            status_anterior = equipamento["status"]
            if novo_status != status_anterior:
                cur.execute("UPDATE equipment_items SET status=%s WHERE id=%s", (novo_status, id))
                registrar_movimentacao(
                    cur, id, "ajuste",
                    f"Status alterado de '{status_anterior}' para '{novo_status}' via QR Code",
                    int(current_user.id),
                )
                registrar_auditoria(
                    cur, equipamento["company_id"], int(current_user.id), "alterar_status",
                    "equipment_items", id,
                    valores_antes={"status": status_anterior}, valores_depois={"status": novo_status},
                )
                conn.commit()
                flash(f"Status atualizado para '{novo_status}'.", "success")
            return redirect(url_for("equipamentos.qr_page", id=id))

        cur.execute("""
            SELECT l.id, l.data_inicio, l.data_fim, l.cancelado, c.nome AS cliente_nome
            FROM locacoes l
            JOIN clientes c ON c.id = l.cliente_id
            WHERE l.equipment_item_id = %s
            ORDER BY l.data_inicio DESC LIMIT 10
        """, (id,))
        locacoes = cur.fetchall()

        cur.execute("""
            SELECT data_conclusao_real, tipo, problema FROM manutencoes
            WHERE equipment_item_id=%s AND status='concluida'
            ORDER BY data_conclusao_real DESC LIMIT 1
        """, (id,))
        ultima_manutencao = cur.fetchone()

        cur.execute("""
            SELECT data_conclusao_prevista, tipo, problema FROM manutencoes
            WHERE equipment_item_id=%s AND status != 'concluida' AND data_conclusao_prevista IS NOT NULL
            ORDER BY data_conclusao_prevista ASC LIMIT 1
        """, (id,))
        proxima_manutencao = cur.fetchone()

        return render_template(
            "equipamento_qr.html", equipamento=equipamento, locacoes=locacoes,
            ultima_manutencao=ultima_manutencao, proxima_manutencao=proxima_manutencao,
            status_editaveis=sorted(STATUS_EDITAVEIS),
            pode_alterar_status=tem_permissao(ALTERAR_STATUS_EQUIPAMENTO),
        )
    finally:
        cur.close()
        conn.close()
