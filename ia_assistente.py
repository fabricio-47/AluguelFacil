import json

import cohere
from cohere.core.api_error import ApiError

from config import Config
from assistente_tools import executar_tool, tools_schema_para_cohere

SYSTEM_PROMPT = (
    "Você é o assistente interno de uma plataforma de locação de equipamentos. "
    "Responda SOMENTE usando as ferramentas disponíveis (relatórios e dados internos). "
    "Nunca invente números. Se a pergunta não corresponder a nenhuma ferramenta disponível, "
    "diga claramente que não consegue responder isso com os dados que tem — não tente adivinhar "
    "nem responda com conhecimento geral fora do sistema. Responda em português, de forma direta "
    "e curta, citando os números relevantes que vieram da ferramenta."
)

MAX_RODADAS_TOOL_USE = 3


class AssistenteError(Exception):
    pass


def _texto_da_resposta(mensagem):
    partes = [bloco.text for bloco in mensagem.content if bloco.type == "text"]
    return "\n".join(p for p in partes if p).strip()


def perguntar(pergunta, company_id, cur, historico=None):
    """
    Faz uma pergunta ao assistente. historico é uma lista de dicts
    {"role": "user"/"assistant", "texto": str} (texto simples, sem blocos de
    tool-use) usada só como contexto de conversa — cada pergunta ainda
    dispara sua própria rodada de tool-use, executada aqui.

    company_id nunca é passado pro modelo nem é um parâmetro de ferramenta —
    é aplicado no servidor, em cada chamada a executar_tool.

    Retorna o texto final da resposta. Levanta AssistenteError em falhas de
    rede/autenticação/configuração, pro chamador decidir como mostrar isso
    (não deixa a exceção crua estourar pra fora).
    """
    if not Config.COHERE_API_KEY:
        raise AssistenteError("Assistente não configurado (COHERE_API_KEY ausente).")

    client = cohere.ClientV2(Config.COHERE_API_KEY)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for troca in (historico or []):
        messages.append({"role": troca["role"], "content": troca["texto"]})
    messages.append({"role": "user", "content": pergunta})

    try:
        for _ in range(MAX_RODADAS_TOOL_USE):
            resp = client.chat(
                model=Config.COHERE_MODEL,
                messages=messages,
                tools=tools_schema_para_cohere(),
            )

            if resp.finish_reason != "TOOL_CALL":
                return _texto_da_resposta(resp.message) or "Não consegui gerar uma resposta pra isso."

            messages.append(resp.message)

            for tc in resp.message.tool_calls:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                try:
                    resultado = executar_tool(cur, company_id, tc.function.name, args)
                    conteudo = json.dumps(resultado, ensure_ascii=False, default=str)
                except Exception as e:
                    conteudo = json.dumps({"erro": str(e)}, ensure_ascii=False)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": [{"type": "document", "document": {"data": conteudo}}],
                })

        return "Não consegui concluir essa consulta (muitas etapas). Tente reformular a pergunta."

    except ApiError as e:
        raise AssistenteError(f"Erro ao consultar o assistente: {e}") from e
    except Exception as e:
        raise AssistenteError(f"Erro inesperado no assistente: {e}") from e
