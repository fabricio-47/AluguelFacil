import datetime as dt
import os
import time

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_from_directory, current_app, abort
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from database import get_db_connection
from permissions import tem_permissao, requer_permissao, CRIAR_LOCACAO, GERENCIAR_LOCACOES, VER_LOCACOES, landing_url
from routes.locacoes_routes import executar_cancelamento_locacao
from multas import calcular_multa
from assinaturas_core import buscar_assinatura_recente, salvar_assinatura

checklists_bp = Blueprint("checklists", __name__, url_prefix="/checklists")

ALLOWED_IMG_EXT = {"png", "jpg", "jpeg"}
ESTADOS = ("novo", "bom", "regular", "danificado")
ESTADO_ORDEM = {estado: i for i, estado in enumerate(ESTADOS)}


def _allowed(filename, allowed):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed


def _unique_filename(prefix_id, filename):
    name, ext = os.path.splitext(filename)
    ts = int(time.time() * 1000)
    return f"{prefix_id}_{ts}{ext.lower()}"


def _permissao_para_tipo(tipo):
    return CRIAR_LOCACAO if tipo == "entrega" else GERENCIAR_LOCACOES


# ======================
# Criar checklist de entrega ou devolução
# ======================
@checklists_bp.route("/locacao/<int:locacao_id>/<tipo>/novo", methods=["GET", "POST"])
@login_required
def novo(locacao_id, tipo):
    if tipo not in ("entrega", "devolucao"):
        abort(404)

    if not tem_permissao(_permissao_para_tipo(tipo)):
        flash("Você não tem permissão para preencher este checklist.", "danger")
        return redirect(landing_url())

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        estado_geral = request.form.get("estado_geral")
        if estado_geral not in ESTADOS:
            cur.close()
            conn.close()
            flash("Selecione o estado geral do equipamento.", "warning")
            return redirect(url_for("checklists.novo", locacao_id=locacao_id, tipo=tipo))

        acessorios_enviados = (request.form.get("acessorios_enviados") or "").strip() or None
        observacoes = (request.form.get("observacoes") or "").strip() or None
        confirmado_pelo_cliente = bool(request.form.get("confirmado_pelo_cliente"))

        tipo_documento = f"checklist_{tipo}"
        assinatura_imagem = request.form.get(f"assinatura_imagem_{tipo}")
        nome_assinante = (request.form.get(f"nome_assinante_{tipo}") or "").strip()
        motivo_substituicao = (request.form.get(f"motivo_substituicao_{tipo}") or "").strip() or None
        substitui_assinatura_id = request.form.get(f"substitui_assinatura_id_{tipo}", type=int)

        if not assinatura_imagem or not nome_assinante:
            cur.close()
            conn.close()
            flash("A assinatura do checklist é obrigatória.", "warning")
            return redirect(url_for("checklists.novo", locacao_id=locacao_id, tipo=tipo))

        # Reconfere no servidor (não confia só no campo escondido do form) se já
        # existe assinatura pra esse documento — se existir, motivo é obrigatório.
        assinatura_existente = buscar_assinatura_recente(cur, tipo_documento, locacao_id, checklist_tipo=tipo)
        if assinatura_existente and not motivo_substituicao:
            cur.close()
            conn.close()
            flash("Já existe uma assinatura pra este checklist — informe o motivo pra registrar uma nova.", "warning")
            return redirect(url_for("checklists.novo", locacao_id=locacao_id, tipo=tipo))
        if assinatura_existente:
            substitui_assinatura_id = assinatura_existente["id"]

        try:
            cur.execute("SELECT cliente_id, company_id FROM locacoes WHERE id=%s", (locacao_id,))
            locacao_ctx = cur.fetchone()
            if not locacao_ctx:
                conn.rollback()
                flash("Locação não encontrada.", "danger")
                return redirect(url_for("locacoes.listar_locacoes"))

            # checklists tem UNIQUE(locacao_id, tipo) — re-assinatura (motivo
            # preenchido) atualiza o checklist já existente em vez de tentar
            # inserir um segundo, o que violaria essa constraint.
            if assinatura_existente:
                cur.execute("""
                    UPDATE checklists SET estado_geral=%s, acessorios_enviados=%s,
                    observacoes=%s, criado_por=%s, confirmado_pelo_cliente=%s
                    WHERE locacao_id=%s AND tipo=%s
                    RETURNING id
                """, (
                    estado_geral, acessorios_enviados, observacoes,
                    int(current_user.id), confirmado_pelo_cliente, locacao_id, tipo,
                ))
            else:
                cur.execute("""
                    INSERT INTO checklists (
                        locacao_id, tipo, estado_geral, acessorios_enviados,
                        observacoes, criado_por, confirmado_pelo_cliente
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id
                """, (
                    locacao_id, tipo, estado_geral, acessorios_enviados,
                    observacoes, int(current_user.id), confirmado_pelo_cliente,
                ))
            checklist_id = cur.fetchone()["id"]

            salvar_assinatura(
                cur,
                upload_folder=current_app.config["UPLOAD_FOLDER"],
                company_id=locacao_ctx["company_id"],
                tipo_documento=tipo_documento,
                documento_id=checklist_id,
                imagem_base64=assinatura_imagem,
                nome_assinante=nome_assinante,
                request=request,
                usuario_id=int(current_user.id),
                cliente_id=locacao_ctx["cliente_id"],
                motivo_substituicao=motivo_substituicao,
                substitui_assinatura_id=substitui_assinatura_id,
            )

            if tipo == "devolucao":
                cur.execute(
                    "SELECT asaas_subscription_id, equipment_item_id, company_id, data_fim, valor FROM locacoes WHERE id=%s",
                    (locacao_id,),
                )
                locacao = cur.fetchone()
                if not locacao:
                    conn.rollback()
                    flash("Locação não encontrada.", "danger")
                    return redirect(url_for("locacoes.listar_locacoes"))

                # Calcula o atraso/multa com a data_fim planejada ANTES dela ser
                # sobrescrita por executar_cancelamento_locacao — retrato definitivo do fechamento.
                cur.execute("SELECT valor_diaria FROM equipment_items WHERE id=%s", (locacao["equipment_item_id"],))
                equipamento = cur.fetchone()
                cur.execute("SELECT * FROM config_multas WHERE company_id=%s", (locacao["company_id"],))
                config = cur.fetchone()
                calculo = calcular_multa(
                    locacao["data_fim"], dt.date.today(), locacao["valor"],
                    equipamento["valor_diaria"] if equipamento else None, config,
                )
                cur.execute(
                    "UPDATE checklists SET dias_atraso_final=%s, valor_multa_final=%s WHERE id=%s",
                    (calculo["dias_atraso"], calculo["valor_multa_total"], checklist_id),
                )

                # Re-assinatura de uma devolução já registrada não deve repetir o
                # cancelamento (locação já finalizada, equipamento já liberado,
                # assinatura Asaas já cancelada) — só atualiza checklist/multa/assinatura.
                if not assinatura_existente:
                    executar_cancelamento_locacao(
                        cur, locacao_id, locacao["equipment_item_id"], locacao["asaas_subscription_id"],
                    )
                conn.commit()
                flash("Checklist de devolução registrado e locação finalizada!", "success")
                return redirect(url_for("locacoes.listar_locacoes"))

            conn.commit()
            flash("Checklist de entrega registrado! Você já pode anexar fotos, se quiser.", "success")
            return redirect(url_for("checklists.comparacao", locacao_id=locacao_id))
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao registrar checklist: {e}", "danger")
        finally:
            cur.close()
            conn.close()

        return redirect(url_for("checklists.novo", locacao_id=locacao_id, tipo=tipo))

    cur.execute("""
        SELECT l.id, c.nome AS cliente_nome, ei.nome AS equipamento_nome, ei.codigo_interno
        FROM locacoes l
        JOIN clientes c ON c.id = l.cliente_id
        JOIN equipment_items ei ON ei.id = l.equipment_item_id
        WHERE l.id = %s
    """, (locacao_id,))
    locacao = cur.fetchone()
    if not locacao:
        cur.close()
        conn.close()
        flash("Locação não encontrada.", "warning")
        return redirect(url_for("locacoes.listar_locacoes"))

    assinatura_existente = buscar_assinatura_recente(cur, f"checklist_{tipo}", locacao_id, checklist_tipo=tipo)
    cur.close()
    conn.close()

    return render_template(
        "checklist_form.html", locacao=locacao, tipo=tipo, estados=ESTADOS,
        assinatura_existente=assinatura_existente,
    )


# ======================
# Upload de fotos do checklist
# ======================
@checklists_bp.route("/<int:checklist_id>/fotos", methods=["POST"])
@login_required
def upload_fotos(checklist_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT locacao_id, tipo FROM checklists WHERE id=%s", (checklist_id,))
    checklist = cur.fetchone()
    if not checklist:
        cur.close()
        conn.close()
        flash("Checklist não encontrado.", "warning")
        return redirect(url_for("locacoes.listar_locacoes"))

    if not tem_permissao(_permissao_para_tipo(checklist["tipo"])):
        cur.close()
        conn.close()
        flash("Você não tem permissão para anexar fotos a este checklist.", "danger")
        return redirect(landing_url())

    files = request.files.getlist("fotos")
    pasta = os.path.join(current_app.config["UPLOAD_FOLDER"], "checklists")
    os.makedirs(pasta, exist_ok=True)

    count_ok = 0
    try:
        for f in files:
            if not f or f.filename == "" or not _allowed(f.filename, ALLOWED_IMG_EXT):
                continue
            filename = _unique_filename(checklist_id, secure_filename(f.filename))
            f.save(os.path.join(pasta, filename))
            cur.execute(
                "INSERT INTO checklist_fotos (checklist_id, arquivo) VALUES (%s, %s)",
                (checklist_id, filename),
            )
            count_ok += 1
        conn.commit()
        if count_ok:
            flash(f"{count_ok} foto(s) anexada(s)!", "success")
        else:
            flash("Nenhuma foto válida foi enviada.", "warning")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao enviar fotos: {e}", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("checklists.comparacao", locacao_id=checklist["locacao_id"]))


@checklists_bp.route("/fotos/<filename>")
@login_required
@requer_permissao(VER_LOCACOES)
def serve_foto(filename):
    pasta = os.path.join(current_app.config["UPLOAD_FOLDER"], "checklists")
    return send_from_directory(pasta, filename)


# ======================
# Comparação entrega x devolução
# ======================
@checklists_bp.route("/locacao/<int:locacao_id>")
@login_required
@requer_permissao(VER_LOCACOES)
def comparacao(locacao_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT l.id, c.nome AS cliente_nome, ei.nome AS equipamento_nome, ei.codigo_interno
        FROM locacoes l
        JOIN clientes c ON c.id = l.cliente_id
        JOIN equipment_items ei ON ei.id = l.equipment_item_id
        WHERE l.id = %s
    """, (locacao_id,))
    locacao = cur.fetchone()
    if not locacao:
        cur.close()
        conn.close()
        flash("Locação não encontrada.", "warning")
        return redirect(url_for("locacoes.listar_locacoes"))

    checklists_por_tipo = {}
    for tipo in ("entrega", "devolucao"):
        cur.execute("""
            SELECT id, estado_geral, acessorios_enviados, observacoes, criado_em, confirmado_pelo_cliente
            FROM checklists WHERE locacao_id=%s AND tipo=%s
        """, (locacao_id, tipo))
        checklist = cur.fetchone()
        if checklist:
            cur.execute(
                "SELECT id, arquivo FROM checklist_fotos WHERE checklist_id=%s ORDER BY id",
                (checklist["id"],),
            )
            checklist = dict(checklist)
            checklist["fotos"] = cur.fetchall()
            checklist["assinatura"] = buscar_assinatura_recente(cur, f"checklist_{tipo}", locacao_id, checklist_tipo=tipo)
        checklists_por_tipo[tipo] = checklist

    cur.close()
    conn.close()

    piorou = False
    entrega, devolucao = checklists_por_tipo["entrega"], checklists_por_tipo["devolucao"]
    if entrega and devolucao:
        piorou = ESTADO_ORDEM[devolucao["estado_geral"]] > ESTADO_ORDEM[entrega["estado_geral"]]

    return render_template(
        "checklist_comparacao.html",
        locacao=locacao,
        entrega=entrega,
        devolucao=devolucao,
        piorou=piorou,
    )
