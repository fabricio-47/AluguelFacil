# Permissões por cargo, por empresa

## Contexto e objetivo

Hoje as permissões de cada cargo (`financeiro`, `atendente`, `vendedor`, `tecnico`,
`estoquista`, `entregador`) são fixas no código (`permissions.py`,
`PERMISSOES_POR_ROLE`), iguais para todas as empresas que usam a plataforma.
`super_admin`, `admin_locadora` e `gerente` têm acesso total, também fixo
(`ROLES_ACESSO_TOTAL`), e não fazem parte desta mudança.

Objetivo: cada empresa (tenant) pode ajustar, numa tela dentro de Configurações,
quais das permissões existentes cada um dos 6 cargos customizáveis tem — sem
criar cargos novos, sem mexer nos 3 cargos de acesso total. Se a empresa não
customizar um cargo, ele continua usando o conjunto padrão do código (mesmo
padrão de fallback já usado para a Asaas: `docs/superpowers/specs/2026-08-17-asaas-por-empresa-design.md`).

**Fora do escopo** (confirmado com o usuário): criar cargos novos; editar
`super_admin`/`admin_locadora`/`gerente`; qualquer coisa relacionada a excluir
usuários (isso é uma tarefa separada — usuários nunca são excluídos de verdade,
só ativados/desativados, tratado em outro spec/task).

## Comportamento atual (o que este spec NÃO muda)

Além do sistema de permissões, várias telas têm filtros por role "por baixo",
independentes de `tem_permissao` — ex: atendente/vendedor só veem os próprios
orçamentos (filtro por `criado_por`), entregador só vê as próprias entregas
(filtro por role, não por permissão). Esses filtros continuam existindo como
estão — esta mudança só afeta o liga/desliga de cada permissão nomeada em
`permissions.py`, não os filtros de "só vejo o que é meu".

## Arquitetura

### Nova tabela `permissoes_customizadas`

Uma linha por (empresa, cargo) — diferente de `config_multas`/`config_asaas`
(que são uma linha por empresa), aqui é uma linha por empresa **e** cargo,
porque uma empresa pode customizar vários cargos independentemente.

```sql
CREATE TABLE IF NOT EXISTS permissoes_customizadas (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    role VARCHAR(20) NOT NULL,
    permissoes JSONB NOT NULL DEFAULT '[]'::jsonb,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(company_id, role),
    CONSTRAINT chk_permissoes_customizadas_role CHECK (role IN (
        'financeiro', 'atendente', 'vendedor', 'tecnico', 'estoquista', 'entregador'
    ))
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_permissoes_customizadas_updated') THEN
        CREATE TRIGGER trg_permissoes_customizadas_updated
        BEFORE UPDATE ON permissoes_customizadas
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END$$;
```

`permissoes` é um array JSON de strings (os valores já existentes de
`permissions.py`, ex: `["ver_locacoes", "criar_locacao"]`). **A presença de uma
linha — mesmo com array vazio — significa "este cargo foi customizado por essa
empresa"; a ausência de linha significa "usa o padrão do código."** Isso evita
a ambiguidade de "empresa customizou pra zero permissões" vs "empresa nunca
mexeu nisso."

`JSONB` já é um padrão usado no projeto (`auditoria.valores_antes/depois`,
migration 012).

### `permissions.py` — `_permissoes_do_role` fica ciente de empresa

Hoje `_permissoes_do_role(role)` é uma função pura, só olha o dict fixo. Passa
a receber `company_id` e consultar o banco, com cache por request (`flask.g`)
pra não bater no banco em toda chamada de `tem_permissao` (que é usada em
`@requer_permissao` de ~13 arquivos de rotas, tipicamente uma vez por request
protegida).

```python
from flask import g
from database import get_db_connection

def _permissoes_do_role(role, company_id):
    if role in ROLES_ACESSO_TOTAL:
        return None  # coringa, libera qualquer permissão — sem consulta ao banco

    cache_attr = f"_permissoes_cache_{role}_{company_id}"
    if hasattr(g, cache_attr):
        return getattr(g, cache_attr)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT permissoes FROM permissoes_customizadas WHERE company_id=%s AND role=%s",
        (company_id, role),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    if row is not None:
        resultado = set(row["permissoes"])
    else:
        resultado = PERMISSOES_POR_ROLE.get(role, set())

    setattr(g, cache_attr, resultado)
    return resultado


def tem_permissao(permissao):
    if not current_user.is_authenticated:
        return False
    permissoes = _permissoes_do_role(
        getattr(current_user, "role", None), getattr(current_user, "company_id", None)
    )
    return permissoes is None or permissao in permissoes
```

`_permissoes_do_role` é a única função que muda de assinatura. `tem_permissao`
e `tem_role` continuam com a mesma assinatura pública — nenhuma das ~13 rotas
que já chamam `tem_permissao`/`requer_permissao` precisa mudar.

### Agrupamento de permissões pra exibição (novo, só UI)

Adiciona em `permissions.py` uma lista de grupos, usada só pra renderizar a
tela — não muda nenhum comportamento de autorização:

```python
GRUPOS_PERMISSOES = [
    ("Financeiro", [VER_DASHBOARD_FINANCEIRO, VER_DESPESAS, GERENCIAR_DESPESAS, VER_RELATORIOS_FINANCEIROS]),
    ("Locações", [VER_LOCACOES, CRIAR_LOCACAO, GERENCIAR_LOCACOES]),
    ("Clientes", [VER_CLIENTES, GERENCIAR_CLIENTES]),
    ("Equipamentos", [VER_EQUIPAMENTOS, GERENCIAR_EQUIPAMENTOS, ALTERAR_STATUS_EQUIPAMENTO]),
    ("Manutenções", [VER_MANUTENCOES, GERENCIAR_MANUTENCOES]),
    ("Filiais", [VER_FILIAIS, GERENCIAR_FILIAIS]),
    ("Entregas", [VER_ENTREGAS, GERENCIAR_ENTREGAS, VER_MAPA_OPERACIONAL]),
    ("Relatórios", [VER_RELATORIOS]),
    ("Orçamentos", [VER_ORCAMENTOS, GERENCIAR_ORCAMENTOS]),
    ("CRM / Pipeline", [VER_PIPELINE, GERENCIAR_PIPELINE]),
    ("Usuários", [VER_USUARIOS, GERENCIAR_USUARIOS]),
    ("Assistente de IA", [VER_ASSISTENTE]),
]

CARGOS_CUSTOMIZAVEIS = ("financeiro", "atendente", "vendedor", "tecnico", "estoquista", "entregador")

LABEL_PERMISSAO = {
    VER_DASHBOARD_FINANCEIRO: "Ver dashboard financeiro",
    VER_LOCACOES: "Ver locações",
    CRIAR_LOCACAO: "Criar locação",
    GERENCIAR_LOCACOES: "Editar/cancelar locações",
    VER_CLIENTES: "Ver clientes",
    GERENCIAR_CLIENTES: "Cadastrar/editar clientes",
    VER_EQUIPAMENTOS: "Ver equipamentos",
    GERENCIAR_EQUIPAMENTOS: "Cadastrar/editar equipamentos",
    VER_DESPESAS: "Ver despesas",
    GERENCIAR_DESPESAS: "Lançar/editar despesas",
    VER_MANUTENCOES: "Ver manutenções",
    GERENCIAR_MANUTENCOES: "Abrir/concluir manutenções",
    VER_FILIAIS: "Ver filiais",
    GERENCIAR_FILIAIS: "Cadastrar/editar filiais",
    VER_ENTREGAS: "Ver entregas",
    GERENCIAR_ENTREGAS: "Criar/atribuir entregas",
    VER_MAPA_OPERACIONAL: "Ver mapa operacional",
    VER_RELATORIOS: "Ver relatórios operacionais",
    VER_RELATORIOS_FINANCEIROS: "Ver relatórios financeiros",
    VER_ORCAMENTOS: "Ver orçamentos",
    GERENCIAR_ORCAMENTOS: "Criar/aprovar orçamentos",
    VER_PIPELINE: "Ver pipeline de vendas",
    GERENCIAR_PIPELINE: "Mover etapa/criar tarefas do CRM",
    VER_USUARIOS: "Ver usuários",
    GERENCIAR_USUARIOS: "Cadastrar/editar usuários",
    ALTERAR_STATUS_EQUIPAMENTO: "Mudar status de equipamento (QR Code)",
    VER_ASSISTENTE: "Usar o assistente de IA",
}
```

### Tela — nova seção dentro de `/configuracoes`

Reaproveita a página já existente (`routes/configuracoes_routes.py`,
`templates/configuracoes.html`) em vez de criar página nova — adiciona uma
segunda `<div class="card">` "Permissões por Cargo" abaixo do card do Asaas,
no mesmo template. **Implementado com uma rota de POST dedicada**
(`POST /configuracoes/permissoes`, form próprio) em vez de compartilhar o
form/POST do Asaas — mantém as duas seções desacopladas (salvar permissões
não depende de reenviar/validar os campos da Asaas, e vice-versa).

- **GET**: busca todas as linhas de `permissoes_customizadas` da empresa
  (`WHERE company_id=%s`, sem filtro de role — traz o que tiver customizado).
  Pra cada um dos 6 `CARGOS_CUSTOMIZAVEIS`, monta o conjunto efetivo (linha
  customizada se existir, senão `PERMISSOES_POR_ROLE[cargo]`) pra pré-marcar
  os checkboxes.
- **Render**: uma grade — 6 colunas (cargos) × permissões agrupadas por área
  (linhas), checkbox em cada célula. **Implementado como
  `name="perm__<cargo>"` com `value="<permissao>"`** (um campo multi-valor
  por cargo, lido via `request.form.getlist(f"perm__{cargo}")`) em vez de um
  nome por checkbox — é a forma idiomática de grupo de checkboxes em HTML e
  o que faz `getlist` funcionar direto, sem precisar decompor nomes de campo.
- **POST**: pra cada um dos 6 cargos, calcula o conjunto de permissões
  marcadas (via `request.form` — checkboxes ausentes = desmarcado) e faz
  `INSERT ... ON CONFLICT (company_id, role) DO UPDATE SET permissoes=...`
  — sempre grava uma linha por cargo (mesmo que vazia), porque o formulário
  sempre envia o estado completo dos 6 cargos de uma vez. Isso significa que,
  a partir do primeiro save, a empresa **sempre** tem uma linha por cargo (não
  volta a usar o fallback do código a menos que a linha seja apagada
  manualmente do banco) — é o comportamento esperado: uma vez que o admin
  mexeu na tela, o que está salvo manda.
- Acesso: mesmo guard da seção Asaas, `@requer_role("super_admin", "admin_locadora")`.

## Fluxo de dados

1. Admin da empresa abre `/configuracoes`, rola até "Permissões por Cargo",
   vê os 6 cargos com os checkboxes já marcados conforme o padrão atual
   (ou customização prévia).
2. Desmarca/marca o que quiser, salva.
3. `permissoes_customizadas` recebe upsert pros 6 cargos (uma linha cada).
4. Da próxima requisição em diante, qualquer `tem_permissao(...)` chamado por
   um usuário daquela empresa com um desses cargos usa o novo conjunto —
   sem precisar reiniciar nada, sem precisar o usuário deslogar (a consulta
   acontece a cada request, com cache só dentro do próprio request via `g`).

## Tratamento de erros

- Se a query em `_permissoes_do_role` falhar (erro de conexão, etc.), a
  exceção sobe — mesmo comportamento de qualquer outra falha de banco nas
  rotas já existentes (não tem tratamento especial hoje pra falha de banco
  dentro de decorators, então não inventamos um aqui).
- POST com um valor de cargo fora de `CARGOS_CUSTOMIZAVEIS` ou permissão fora
  da lista conhecida: ignorado silenciosamente (não grava lixo).

## Testes

Sem suíte automatizada no projeto — mesmo padrão das features anteriores:
scripts `python -c "..."` contra o banco real, mais teste manual no navegador
pra confirmar que desmarcar uma permissão de fato bloqueia a rota
correspondente pra um usuário daquele cargo.
