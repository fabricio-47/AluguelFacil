import io
import os
import time
import psycopg2
import qrcode
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_from_directory, current_app, Response, abort
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from database import get_db_connection
from permissions import requer_permissao, tem_permissao, VER_EQUIPAMENTOS, GERENCIAR_EQUIPAMENTOS, ALTERAR_STATUS_EQUIPAMENTO
from estoque import registrar_movimentacao
from planos import verificar_limite
from auditoria import registrar_auditoria
from modulos import MODULOS, MODULOS_INVENTARIO, tem_modulo_ativo, gate_algum_modulo

equipamentos_bp = Blueprint("equipamentos", __name__, url_prefix="/equipamentos")
equipamentos_bp.before_request(gate_algum_modulo(MODULOS_INVENTARIO))

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
    tipo_item = (form.get("tipo_item") or "equipamento").strip()
    if tipo_item not in MODULOS_INVENTARIO:
        tipo_item = "equipamento"
    return {
        "tipo_item": tipo_item,
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
        "placa": (form.get("placa") or "").strip().upper() or None,
        "chassi": (form.get("chassi") or "").strip().upper() or None,
        "renavam": (form.get("renavam") or "").strip() or None,
        "quilometragem": form.get("quilometragem") or None,
        "combustivel": (form.get("combustivel") or "").strip() or None,
        "cambio": (form.get("cambio") or "").strip() or None,
        "endereco_completo": (form.get("endereco_completo") or "").strip() or None,
        "bairro": (form.get("bairro") or "").strip() or None,
        "cidade": (form.get("cidade") or "").strip() or None,
        "metro_quadrado": form.get("metro_quadrado") or None,
        "quartos": form.get("quartos") or None,
        "banheiros": form.get("banheiros") or None,
        "tipo_imovel": (form.get("tipo_imovel") or "").strip() or None,
        "iptu": form.get("iptu") or None,
        "condominio": form.get("condominio") or None,
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

        if not tem_modulo_ativo(cur, current_user.company_id, campos["tipo_item"]):
            cur.close()
            conn.close()
            nome_modulo = MODULOS.get(campos["tipo_item"], {}).get("nome", campos["tipo_item"])
            flash(
                f"O módulo \"{nome_modulo}\" não está ativo para sua empresa. "
                f"Fale com o administrador da conta para contratar.",
                "warning",
            )
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
                    valor_quinzenal, valor_mensal, valor_hora, caucao, status, quantidade_disponivel,
                    placa, chassi, renavam, quilometragem, combustivel, cambio,
                    endereco_completo, bairro, cidade, metro_quadrado, quartos, banheiros, tipo_imovel, iptu, condominio,
                    tipo_item
                ) VALUES (%(company_id)s,%(branch_id)s,%(categoria_id)s,%(codigo_interno)s,%(sku)s,%(codigo_barras)s,%(nome)s,%(marca)s,
                    %(modelo)s,%(numero_serie)s,%(ano)s,%(descricao)s,%(valor_compra)s,%(valor_diaria)s,
                    %(valor_semanal)s,%(valor_quinzenal)s,%(valor_mensal)s,%(valor_hora)s,%(caucao)s,
                    %(status)s,%(quantidade_disponivel)s,
                    %(placa)s,%(chassi)s,%(renavam)s,%(quilometragem)s,%(combustivel)s,%(cambio)s,
                    %(endereco_completo)s,%(bairro)s,%(cidade)s,%(metro_quadrado)s,%(quartos)s,%(banheiros)s,%(tipo_imovel)s,%(iptu)s,%(condominio)s,
                    %(tipo_item)s)
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

    tipos_liberados = [s for s in MODULOS_INVENTARIO if tem_modulo_ativo(cur, current_user.company_id, s)]

    cur.execute("""
        SELECT ei.id, ei.codigo_interno, ei.nome, ei.marca, ei.modelo, ei.ano, ei.status,
               ei.foto, ei.documento_arquivo, ec.nome AS categoria_nome, ei.placa, ei.tipo_imovel, ei.tipo_item
        FROM equipment_items ei
        LEFT JOIN equipment_categories ec ON ec.id = ei.categoria_id
        WHERE ei.company_id = %s AND ei.tipo_item = ANY(%s)
        ORDER BY ei.nome
    """, (current_user.company_id, tipos_liberados))
    equipamentos = cur.fetchall()

    cur.execute("SELECT id, nome FROM equipment_categories WHERE company_id = %s ORDER BY nome", (current_user.company_id,))
    categorias = cur.fetchall()

    cur.close()
    conn.close()
    return render_template(
        "equipamentos.html",
        equipamentos=equipamentos,
        categorias=categorias,
        tipos_liberados=tipos_liberados,
        modulos_info=MODULOS,
    )

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
        elif not tem_modulo_ativo(cur, current_user.company_id, campos["tipo_item"]):
            nome_modulo = MODULOS.get(campos["tipo_item"], {}).get("nome", campos["tipo_item"])
            flash(
                f"O módulo \"{nome_modulo}\" não está ativo para sua empresa. "
                f"Fale com o administrador da conta para contratar.",
                "warning",
            )
        else:
            try:
                cur.execute(
                    "SELECT status, tipo_item FROM equipment_items WHERE id=%s AND company_id=%s",
                    (id, current_user.company_id),
                )
                item_atual = cur.fetchone()
                if not item_atual:
                    conn.rollback()
                    cur.close()
                    conn.close()
                    flash("Equipamento não encontrado.", "danger")
                    return redirect(url_for("equipamentos.listar_equipamentos"))
                status_anterior = item_atual["status"]
                if not tem_modulo_ativo(cur, current_user.company_id, item_atual["tipo_item"]):
                    conn.rollback()
                    cur.close()
                    conn.close()
                    nome_modulo = MODULOS.get(item_atual["tipo_item"], {}).get("nome", item_atual["tipo_item"])
                    flash(
                        f"O módulo \"{nome_modulo}\" não está mais ativo para sua empresa -- "
                        f"esse item não pode ser editado. Fale com o administrador da conta.",
                        "warning",
                    )
                    return redirect(url_for("equipamentos.listar_equipamentos"))

                campos["id"] = id
                campos["company_id"] = current_user.company_id
                cur.execute("""
                    UPDATE equipment_items SET
                        categoria_id=%(categoria_id)s, codigo_interno=%(codigo_interno)s, sku=%(sku)s,
                        codigo_barras=%(codigo_barras)s, nome=%(nome)s, marca=%(marca)s, modelo=%(modelo)s,
                        numero_serie=%(numero_serie)s, ano=%(ano)s, descricao=%(descricao)s,
                        valor_compra=%(valor_compra)s, valor_diaria=%(valor_diaria)s,
                        valor_semanal=%(valor_semanal)s, valor_quinzenal=%(valor_quinzenal)s,
                        valor_mensal=%(valor_mensal)s, valor_hora=%(valor_hora)s, caucao=%(caucao)s,
                        status=%(status)s, quantidade_disponivel=%(quantidade_disponivel)s,
                        placa=%(placa)s, chassi=%(chassi)s, renavam=%(renavam)s,
                        quilometragem=%(quilometragem)s, combustivel=%(combustivel)s, cambio=%(cambio)s,
                        endereco_completo=%(endereco_completo)s, bairro=%(bairro)s, cidade=%(cidade)s,
                        metro_quadrado=%(metro_quadrado)s,
                        quartos=%(quartos)s, banheiros=%(banheiros)s, tipo_imovel=%(tipo_imovel)s,
                        iptu=%(iptu)s, condominio=%(condominio)s, tipo_item=%(tipo_item)s
                    WHERE id=%(id)s AND company_id=%(company_id)s
                """, campos)

                if status_anterior != campos["status"]:
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
                    cur.execute(
                        "UPDATE equipment_items SET foto=%s WHERE id=%s AND company_id=%s",
                        (filename, id, current_user.company_id),
                    )

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
               ei.caucao, ei.status, ei.branch_id, b.nome AS filial_nome, ei.tipo_item,
               ei.placa, ei.chassi, ei.renavam, ei.quilometragem, ei.combustivel, ei.cambio,
               ei.endereco_completo, ei.bairro, ei.cidade, ei.metro_quadrado, ei.quartos, ei.banheiros, ei.tipo_imovel, ei.iptu, ei.condominio
        FROM equipment_items ei
        LEFT JOIN branches b ON b.id = ei.branch_id
        WHERE ei.id=%s AND ei.company_id=%s
    """, (id, current_user.company_id))
    equipamento = cur.fetchone()

    if not equipamento:
        cur.close()
        conn.close()
        flash("Equipamento não encontrado.", "warning")
        return redirect(url_for("equipamentos.listar_equipamentos"))

    cur.execute("SELECT id, nome FROM equipment_categories WHERE company_id=%s ORDER BY nome", (current_user.company_id,))
    categorias = cur.fetchall()

    tipos_liberados = [s for s in MODULOS_INVENTARIO if tem_modulo_ativo(cur, current_user.company_id, s)]

    cur.close()
    conn.close()
    return render_template(
        "editar_equipamento.html",
        equipamento=equipamento,
        categorias=categorias,
        status_editaveis=sorted(STATUS_EDITAVEIS),
        tipos_liberados=tipos_liberados,
        modulos_info=MODULOS,
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
        cur.execute("DELETE FROM equipment_items WHERE id=%s AND company_id=%s", (id, current_user.company_id))
        if cur.rowcount == 0:
            conn.rollback()
            flash("Equipamento não encontrado.", "warning")
        else:
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

    # Valida a posse do equipamento pela empresa ANTES de qualquer leitura ou escrita.
    cur.execute(
        "SELECT id FROM equipment_items WHERE id=%s AND company_id=%s",
        (equipamento_id, current_user.company_id),
    )
    if not cur.fetchone():
        cur.close()
        conn.close()
        flash("Equipamento não encontrado.", "warning")
        return redirect(url_for("equipamentos.listar_equipamentos"))

    if request.method == "POST":
        if "documento" not in request.files:
            cur.close()
            conn.close()
            flash("Nenhum arquivo enviado.", "danger")
            return redirect(request.url)

        file = request.files["documento"]
        if file.filename == "":
            cur.close()
            conn.close()
            flash("Nenhum arquivo selecionado.", "danger")
            return redirect(request.url)

        if not _allowed(file.filename, ALLOWED_DOC_EXT):
            cur.close()
            conn.close()
            flash("Formato inválido. Envie PDF, PNG, JPG ou JPEG.", "warning")
            return redirect(request.url)

        try:
            filename = secure_filename(file.filename)
            filename = _unique_filename(equipamento_id, filename)
            pasta = os.path.join(current_app.config["UPLOAD_FOLDER"], "contratos")
            os.makedirs(pasta, exist_ok=True)
            file.save(os.path.join(pasta, filename))

            cur.execute(
                "UPDATE equipment_items SET documento_arquivo=%s WHERE id=%s AND company_id=%s",
                (filename, equipamento_id, current_user.company_id),
            )
            conn.commit()
            flash("Documento enviado com sucesso!", "success")
            return redirect(url_for("equipamentos.equipamento_documento", equipamento_id=equipamento_id))
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao enviar documento: {e}", "danger")
        finally:
            cur.close()
            conn.close()
        return redirect(url_for("equipamentos.equipamento_documento", equipamento_id=equipamento_id))

    cur.execute("""
        SELECT id, codigo_interno, nome, modelo, documento_arquivo
        FROM equipment_items WHERE id=%s AND company_id=%s
    """, (equipamento_id, current_user.company_id))
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
        cur.execute(
            "SELECT documento_arquivo FROM equipment_items WHERE id=%s AND company_id=%s",
            (equipamento_id, current_user.company_id),
        )
        row = cur.fetchone()
        if not row:
            flash("Equipamento não encontrado.", "warning")
            return redirect(url_for("equipamentos.listar_equipamentos"))

        if row["documento_arquivo"]:
            filename = row["documento_arquivo"]
            pasta = os.path.join(current_app.config["UPLOAD_FOLDER"], "contratos")
            filepath = os.path.join(pasta, filename)
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception:
                    pass

        cur.execute(
            "UPDATE equipment_items SET documento_arquivo=NULL WHERE id=%s AND company_id=%s",
            (equipamento_id, current_user.company_id),
        )
        conn.commit()
        flash("Documento do equipamento removido com sucesso!", "info")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao remover documento: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("equipamentos.equipamento_documento", equipamento_id=equipamento_id))

@equipamentos_bp.route("/<int:equipamento_id>/documentos/<filename>")
@login_required
@requer_permissao(VER_EQUIPAMENTOS)
def serve_documento_equipamento(equipamento_id, filename):
    """Exige equipamento_id na URL (não só o filename) para validar a empresa
    antes de servir qualquer arquivo — mesmo raciocínio e mesma correção já
    aplicada em clientes.uploaded_documento."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id FROM equipment_items WHERE id=%s AND company_id=%s",
            (equipamento_id, current_user.company_id),
        )
        if not cur.fetchone():
            abort(404)
    finally:
        cur.close()
        conn.close()
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

    cur.execute("SELECT id, codigo_interno, nome, modelo, ano FROM equipment_items WHERE id=%s AND company_id=%s", (equipamento_id, current_user.company_id))
    equipamento = cur.fetchone()
    if not equipamento:
        cur.close()
        conn.close()
        flash("Equipamento não encontrado.", "warning")
        return redirect(url_for("equipamentos.listar_equipamentos"))

    if request.method == "POST":
        files = request.files.getlist("imagens")
        if not files or files == [None]:
            cur.close()
            conn.close()
            flash("Nenhuma imagem selecionada.", "warning")
            return redirect(request.url)

        cur.execute("SELECT COUNT(*) AS total FROM equipment_item_imagens WHERE equipment_item_id=%s", (equipamento_id,))
        ja_tem = cur.fetchone()["total"]
        LIMITE_FOTOS = 20
        vagas = LIMITE_FOTOS - ja_tem
        if vagas <= 0:
            cur.close()
            conn.close()
            flash(f"Esse item já tem o máximo de {LIMITE_FOTOS} fotos. Exclua alguma antes de enviar mais.", "warning")
            return redirect(request.url)
        if len(files) > vagas:
            files = files[:vagas]
            flash(f"Só cabiam mais {vagas} foto(s) (limite de {LIMITE_FOTOS}) — as primeiras {vagas} foram enviadas.", "warning")

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
        finally:
            cur.close()
            conn.close()
        return redirect(url_for("equipamentos.equipamento_imagens", equipamento_id=equipamento_id))

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
            "SELECT id FROM equipment_items WHERE id=%s AND company_id=%s",
            (equipamento_id, current_user.company_id),
        )
        if not cur.fetchone():
            flash("Equipamento não encontrado.", "warning")
            return redirect(url_for("equipamentos.listar_equipamentos"))

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

@equipamentos_bp.route("/<int:equipamento_id>/imagens/<filename>")
@login_required
@requer_permissao(VER_EQUIPAMENTOS)
def serve_imagem_equipamento(equipamento_id, filename):
    """Mesma correção de serve_documento_equipamento: exige equipamento_id na
    URL pra validar a empresa antes de servir a imagem."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id FROM equipment_items WHERE id=%s AND company_id=%s",
            (equipamento_id, current_user.company_id),
        )
        if not cur.fetchone():
            abort(404)
    finally:
        cur.close()
        conn.close()
    pasta = os.path.join(current_app.config["UPLOAD_FOLDER"], "motos")
    return send_from_directory(pasta, filename)


# ======================
# QR Code do equipamento (gerado na hora, sem salvar arquivo)
# ======================
@equipamentos_bp.route("/<int:id>/qr.png")
@login_required
@requer_permissao(VER_EQUIPAMENTOS)
def qr_png(id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM equipment_items WHERE id=%s AND company_id=%s", (id, current_user.company_id))
        if not cur.fetchone():
            abort(404)
    finally:
        cur.close()
        conn.close()

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
        if not equipamento or equipamento["company_id"] != current_user.company_id:
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
                cur.execute(
                    "UPDATE equipment_items SET status=%s WHERE id=%s AND company_id=%s",
                    (novo_status, id, current_user.company_id),
                )
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


# ======================
# Categorias de equipamento (nome + categoria pai opcional, pra separar
# Equipamentos genericos / Veiculos / Imoveis visualmente)
# ======================
@equipamentos_bp.route("/categorias", methods=["GET", "POST"])
@login_required
@requer_permissao(VER_EQUIPAMENTOS)
def listar_categorias():
    if request.method == "POST" and not tem_permissao(GERENCIAR_EQUIPAMENTOS):
        flash("Você não tem permissão para cadastrar categorias.", "danger")
        return redirect(url_for("equipamentos.listar_categorias"))

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        categoria_pai_id = request.form.get("categoria_pai_id", type=int) or None
        if not nome:
            flash("Nome da categoria é obrigatório.", "warning")
        else:
            try:
                cur.execute(
                    "INSERT INTO equipment_categories (company_id, nome, categoria_pai_id) VALUES (%s, %s, %s)",
                    (current_user.company_id, nome, categoria_pai_id),
                )
                conn.commit()
                flash("Categoria cadastrada com sucesso!", "success")
            except Exception as e:
                conn.rollback()
                flash(f"Erro ao cadastrar categoria: {e}", "danger")
        cur.close()
        conn.close()
        return redirect(url_for("equipamentos.listar_categorias"))

    cur.execute("""
        SELECT c.id, c.nome, c.categoria_pai_id, pai.nome AS categoria_pai_nome,
               (SELECT COUNT(*) FROM equipment_items ei WHERE ei.categoria_id = c.id) AS itens_usando
        FROM equipment_categories c
        LEFT JOIN equipment_categories pai ON pai.id = c.categoria_pai_id
        WHERE c.company_id = %s
        ORDER BY c.nome
    """, (current_user.company_id,))
    categorias = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("equipamento_categorias.html", categorias=categorias)


@equipamentos_bp.route("/categorias/<int:id>/editar", methods=["POST"])
@login_required
@requer_permissao(GERENCIAR_EQUIPAMENTOS)
def editar_categoria(id):
    nome = (request.form.get("nome") or "").strip()
    categoria_pai_id = request.form.get("categoria_pai_id", type=int) or None
    if categoria_pai_id == id:
        flash("Uma categoria não pode ser pai dela mesma.", "warning")
        return redirect(url_for("equipamentos.listar_categorias"))
    if not nome:
        flash("Nome da categoria é obrigatório.", "warning")
        return redirect(url_for("equipamentos.listar_categorias"))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE equipment_categories SET nome=%s, categoria_pai_id=%s WHERE id=%s AND company_id=%s",
            (nome, categoria_pai_id, id, current_user.company_id),
        )
        conn.commit()
        flash("Categoria atualizada!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao atualizar categoria: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("equipamentos.listar_categorias"))


@equipamentos_bp.route("/categorias/<int:id>/excluir", methods=["POST"])
@login_required
@requer_permissao(GERENCIAR_EQUIPAMENTOS)
def excluir_categoria(id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM equipment_categories WHERE id=%s AND company_id=%s", (id, current_user.company_id))
        if cur.rowcount == 0:
            conn.rollback()
            flash("Categoria não encontrada.", "warning")
        else:
            conn.commit()
            flash("Categoria excluída.", "info")
    except psycopg2.errors.ForeignKeyViolation:
        conn.rollback()
        flash("Não é possível excluir: existem equipamentos ou subcategorias usando essa categoria.", "danger")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao excluir categoria: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("equipamentos.listar_categorias"))
