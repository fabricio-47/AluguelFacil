import base64
import os
import time


def obter_ip_cliente(request):
    """IP real do visitante — request.remote_addr sozinho reflete o proxy do
    Render, não quem realmente assinou. X-Forwarded-For (primeiro IP da
    cadeia) é o que carrega o IP original; sem ele, cai no remote_addr."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr


def buscar_assinatura_recente(cur, tipo_documento, locacao_id, checklist_tipo=None):
    """
    Assinatura mais recente pra um documento. Pra 'contrato', documento_id já
    é o locacao_id. Pra checklist, o checklist ainda não existe no momento em
    que o form é exibido (nasce na mesma submissão da assinatura) — então a
    busca é feita via locacao_id + tipo do checklist, olhando todas as
    assinaturas de qualquer checklist daquele tipo pra essa locação.
    """
    if tipo_documento == "contrato":
        cur.execute("""
            SELECT * FROM assinaturas
            WHERE tipo_documento = 'contrato' AND documento_id = %s
            ORDER BY data_hora DESC LIMIT 1
        """, (locacao_id,))
    else:
        cur.execute("""
            SELECT a.* FROM assinaturas a
            JOIN checklists c ON c.id = a.documento_id
            WHERE a.tipo_documento = %s AND c.locacao_id = %s AND c.tipo = %s
            ORDER BY a.data_hora DESC LIMIT 1
        """, (tipo_documento, locacao_id, checklist_tipo))
    return cur.fetchone()


def salvar_assinatura(cur, *, upload_folder, company_id, tipo_documento, documento_id,
                       imagem_base64, nome_assinante, request, usuario_id=None, cliente_id=None,
                       motivo_substituicao=None, substitui_assinatura_id=None):
    """
    Decodifica o PNG (data-URL base64 vindo do canvas), salva em
    uploads/assinaturas/ e grava a linha em assinaturas. Não faz commit —
    quem chama controla a transação. Retorna o id da assinatura criada.
    """
    if "," in imagem_base64:
        imagem_base64 = imagem_base64.split(",", 1)[1]

    pasta = os.path.join(upload_folder, "assinaturas")
    os.makedirs(pasta, exist_ok=True)
    filename = f"{tipo_documento}_{documento_id}_{int(time.time() * 1000)}.png"
    with open(os.path.join(pasta, filename), "wb") as f:
        f.write(base64.b64decode(imagem_base64))

    ip_address = obter_ip_cliente(request)
    user_agent = request.headers.get("User-Agent")

    cur.execute("""
        INSERT INTO assinaturas (
            company_id, tipo_documento, documento_id, assinatura_imagem, nome_assinante,
            ip_address, user_agent, usuario_id, cliente_id, motivo_substituicao, substitui_assinatura_id
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
    """, (
        company_id, tipo_documento, documento_id, filename, nome_assinante,
        ip_address, user_agent, usuario_id, cliente_id, motivo_substituicao, substitui_assinatura_id,
    ))
    return cur.fetchone()["id"]
