from functools import wraps

from flask import flash, redirect, url_for
from flask_login import current_user

# ======================
# Permissões conhecidas
# ======================
VER_DASHBOARD_FINANCEIRO = "ver_dashboard_financeiro"
VER_LOCACOES = "ver_locacoes"
CRIAR_LOCACAO = "criar_locacao"
GERENCIAR_LOCACOES = "gerenciar_locacoes"  # editar, cancelar, sincronizar boletos (dados financeiros da locação)
VER_CLIENTES = "ver_clientes"
GERENCIAR_CLIENTES = "gerenciar_clientes"
VER_EQUIPAMENTOS = "ver_equipamentos"
GERENCIAR_EQUIPAMENTOS = "gerenciar_equipamentos"  # criar/editar/excluir equipamentos, documentos e imagens
VER_DESPESAS = "ver_despesas"  # também dá acesso a fluxo de caixa e dashboard financeiro (só leitura)
GERENCIAR_DESPESAS = "gerenciar_despesas"  # criar/editar/excluir despesas, marcar como paga
VER_MANUTENCOES = "ver_manutencoes"
GERENCIAR_MANUTENCOES = "gerenciar_manutencoes"  # abrir/editar/concluir manutenção
VER_FILIAIS = "ver_filiais"  # gestão de filiais — não concedida a nenhum role específico, só acesso total
GERENCIAR_FILIAIS = "gerenciar_filiais"
VER_ENTREGAS = "ver_entregas"  # entregador só vê as próprias, mesmo com essa permissão (filtro é por role, não por permissão)
GERENCIAR_ENTREGAS = "gerenciar_entregas"  # criar/atribuir entregas
VER_MAPA_OPERACIONAL = "ver_mapa_operacional"
VER_RELATORIOS = "ver_relatorios"  # relatórios operacionais (mais alugados, parados) — não concedida a nenhum role, só acesso total
VER_RELATORIOS_FINANCEIROS = "ver_relatorios_financeiros"  # relatórios de receita/inadimplência/atraso
VER_ORCAMENTOS = "ver_orcamentos"  # atendente/vendedor só veem os próprios (filtro por criado_por, não é uma permissão separada)
GERENCIAR_ORCAMENTOS = "gerenciar_orcamentos"  # criar orçamento, mudar status, aprovar/converter em locação
VER_PIPELINE = "ver_pipeline"  # pipeline de vendas + tarefas de CRM; atendente/vendedor só veem os próprios (filtro por usuario_responsavel)
GERENCIAR_PIPELINE = "gerenciar_pipeline"  # mover cliente de etapa, criar/concluir tarefas
VER_USUARIOS = "ver_usuarios"  # gestão de funcionários da própria empresa — não concedida a nenhum role específico, só acesso total
GERENCIAR_USUARIOS = "gerenciar_usuarios"
ALTERAR_STATUS_EQUIPAMENTO = "alterar_status_equipamento"  # mudar status pela tela de QR Code — mais estreita que GERENCIAR_EQUIPAMENTOS
VER_ASSISTENTE = "ver_assistente"  # assistente de IA interno — não concedida a nenhum role específico, só acesso total (gerente/admin_locadora/super_admin)

# super_admin e admin_locadora têm acesso total.
# gerente também, exceto configurações da conta/assinatura — que ainda não existem
# como rota no sistema, então por ora o efeito prático é o mesmo.
ROLES_ACESSO_TOTAL = {"super_admin", "admin_locadora", "gerente"}

PERMISSOES_POR_ROLE = {
    "financeiro": {
        VER_DASHBOARD_FINANCEIRO, VER_LOCACOES, GERENCIAR_LOCACOES, VER_CLIENTES, VER_EQUIPAMENTOS,
        VER_DESPESAS, GERENCIAR_DESPESAS, VER_RELATORIOS_FINANCEIROS,
    },
    "atendente": {
        VER_LOCACOES, CRIAR_LOCACAO, VER_CLIENTES, GERENCIAR_CLIENTES, VER_EQUIPAMENTOS,
        VER_ENTREGAS, GERENCIAR_ENTREGAS, VER_MAPA_OPERACIONAL,
        VER_ORCAMENTOS, GERENCIAR_ORCAMENTOS, VER_PIPELINE, GERENCIAR_PIPELINE,
    },
    "vendedor": {
        VER_LOCACOES, CRIAR_LOCACAO, VER_CLIENTES, GERENCIAR_CLIENTES, VER_EQUIPAMENTOS,
        VER_ENTREGAS, GERENCIAR_ENTREGAS, VER_MAPA_OPERACIONAL,
        VER_ORCAMENTOS, GERENCIAR_ORCAMENTOS, VER_PIPELINE, GERENCIAR_PIPELINE,
    },
    "tecnico": {
        VER_EQUIPAMENTOS, VER_MANUTENCOES, GERENCIAR_MANUTENCOES, ALTERAR_STATUS_EQUIPAMENTO,
    },
    "estoquista": {
        VER_EQUIPAMENTOS, GERENCIAR_EQUIPAMENTOS, VER_MANUTENCOES, GERENCIAR_MANUTENCOES,
        VER_ENTREGAS, VER_MAPA_OPERACIONAL, ALTERAR_STATUS_EQUIPAMENTO,
    },
    "entregador": {
        VER_ENTREGAS, VER_MAPA_OPERACIONAL,
    },
}

# Ordem de preferência para decidir uma página segura pra onde mandar o usuário
# (pós-login ou quando uma permissão é negada em outro lugar).
_ROTA_POR_PERMISSAO = [
    (VER_DASHBOARD_FINANCEIRO, "dashboard.home"),
    (VER_MAPA_OPERACIONAL, "operacional.mapa"),
    (VER_LOCACOES, "locacoes.listar_locacoes"),
    (VER_EQUIPAMENTOS, "equipamentos.listar_equipamentos"),
    (VER_CLIENTES, "clientes.listar_clientes"),
]


def _permissoes_do_role(role):
    if role in ROLES_ACESSO_TOTAL:
        return None  # None = coringa, libera qualquer permissão
    return PERMISSOES_POR_ROLE.get(role, set())


def tem_permissao(permissao):
    if not current_user.is_authenticated:
        return False
    permissoes = _permissoes_do_role(getattr(current_user, "role", None))
    return permissoes is None or permissao in permissoes


def tem_role(*roles):
    return current_user.is_authenticated and getattr(current_user, "role", None) in roles


def landing_url():
    """Primeira página que o usuário logado tem permissão de acessar (fallback seguro, sem loop)."""
    if current_user.is_authenticated and getattr(current_user, "eh_admin_plataforma", False):
        return url_for("admin_plataforma.dashboard")
    for permissao, endpoint in _ROTA_POR_PERMISSAO:
        if tem_permissao(permissao):
            return url_for(endpoint)
    return url_for("auth.login")


def _negar_acesso():
    flash("Você não tem permissão para acessar esta página.", "danger")
    return redirect(landing_url())


def requer_permissao(permissao):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not tem_permissao(permissao):
                return _negar_acesso()
            return f(*args, **kwargs)
        return wrapped
    return decorator


def requer_role(*roles):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not tem_role(*roles):
                return _negar_acesso()
            return f(*args, **kwargs)
        return wrapped
    return decorator


# ======================
# Admin de plataforma — TOTALMENTE separado do sistema de permissões acima.
# eh_admin_plataforma nunca entra em ROLES_ACESSO_TOTAL/PERMISSOES_POR_ROLE:
# ser admin de plataforma não muda em nada o que o usuário vê dentro da sua
# própria company nas telas normais, só libera a área /admin-plataforma.
# ======================
def eh_admin_plataforma():
    return current_user.is_authenticated and getattr(current_user, "eh_admin_plataforma", False)


def requer_admin_plataforma(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not eh_admin_plataforma():
            flash("Acesso restrito ao administrador da plataforma.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return wrapped
