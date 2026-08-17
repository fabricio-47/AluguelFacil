# Permissões por Cargo, por Empresa Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cada empresa (tenant) do AluguelFacil pode customizar, numa tela dentro de Configurações, quais permissões cada um dos 6 cargos ajustáveis (financeiro, atendente, vendedor, tecnico, estoquista, entregador) tem — com fallback pro padrão fixo do código quando a empresa não customizou.

**Architecture:** Nova tabela `permissoes_customizadas` (uma linha por empresa+cargo, coluna `permissoes` JSONB — presença de linha = customizado, ausência = usa o padrão fixo). `permissions.py`'s `_permissoes_do_role` passa a consultar essa tabela (com fallback e cache por request via `flask.g`). Nova seção na página `/configuracoes` já existente, com uma rota de POST dedicada.

**Tech Stack:** Flask, psycopg2 (RealDictCursor via `database.get_db_connection()`), Jinja2/Bootstrap, `flask.g` pra cache por request.

**Spec:** `docs/superpowers/specs/2026-08-17-permissoes-por-cargo-design.md`

## Global Constraints

- `get_db_connection()` sempre retorna `RealDictCursor` — leitura é sempre `row["coluna"]`, nunca índice numérico. `RealDictRow` **não** suporta indexação inteira (`row[0]` levanta `KeyError`) — lição já aprendida na feature anterior desta sessão (Asaas por empresa).
- Projeto **não tem suíte de testes automatizada** (sem pytest, sem `tests/`). Verificação é scripts `python -c "..."` standalone contra o banco real (`.env` já configurado localmente com `DATABASE_URL`).
- Nenhuma tarefa deste plano precisa de login interativo no navegador — toda verificação de comportamento de rota usa `app.test_client()` do Flask com `login_user()` chamado diretamente (sem passar por formulário de login), que é uma técnica de teste padrão, não uma ação de "digitar senha em formulário de login" restrita a agentes.
- Migration idempotente (`CREATE TABLE IF NOT EXISTS`), mesmo padrão das migrations já existentes.
- Esta mudança **não** cria cargos novos, **não** mexe em `super_admin`/`admin_locadora`/`gerente` (que continuam com acesso total fixo via `ROLES_ACESSO_TOTAL`), e **não** mexe nos filtros de "só vejo o que é meu" que já existem em algumas telas (esses são independentes do sistema de permissões nomeadas).

---

## Task 1: Tabela `permissoes_customizadas`

**Files:**
- Create: `migrations/016_permissoes_customizadas.sql`

**Interfaces:**
- Produces: tabela `permissoes_customizadas(id, company_id, role, permissoes JSONB, created_at, updated_at)` no banco, `UNIQUE(company_id, role)`.

- [ ] **Step 1: Escrever a migration**

Crie `migrations/016_permissoes_customizadas.sql`:

```sql
-- Migration 016: permissões customizadas por cargo, por empresa.
--
-- Só estrutura (DDL). Idempotente. Aditiva.
-- Uma linha por (empresa, cargo) — diferente de config_multas/config_asaas
-- (uma linha por empresa), aqui é por empresa E cargo, já que uma empresa
-- pode customizar vários cargos independentemente.
--
-- A coluna `permissoes` é um array JSON de strings (os valores de
-- permissions.py, ex: ["ver_locacoes", "criar_locacao"]). A PRESENÇA da
-- linha (mesmo com array vazio) significa "este cargo foi customizado";
-- a AUSÊNCIA de linha significa "usa o padrão fixo do código".

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

- [ ] **Step 2: Aplicar a migration no banco real e verificar**

```bash
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
import psycopg2
conn = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require')
cur = conn.cursor()
with open('migrations/016_permissoes_customizadas.sql', encoding='utf-8') as f:
    cur.execute(f.read())
conn.commit()
cur.execute(\"SELECT column_name, data_type FROM information_schema.columns WHERE table_name='permissoes_customizadas' ORDER BY column_name\")
print(cur.fetchall())
conn.close()
"
```

Expected: lista de colunas incluindo `('permissoes', 'jsonb')`, `('company_id', 'integer')`, `('role', 'character varying')`.

Se a ação for bloqueada pelo classificador do Claude Code (já aconteceu nesta sessão pra DDL em produção), pare e peça confirmação explícita ao usuário — não tente contornar.

- [ ] **Step 3: Commit**

```bash
git add migrations/016_permissoes_customizadas.sql
git commit -m "Adiciona tabela permissoes_customizadas (permissões por cargo, por empresa)"
```

---

## Task 2: `permissions.py` — company-aware + metadados de exibição

**Files:**
- Modify: `permissions.py`

**Interfaces:**
- Consumes: tabela `permissoes_customizadas` (Task 1).
- Produces (usado pela Task 3):
  - `CARGOS_CUSTOMIZAVEIS: tuple[str, ...]` — os 6 nomes de cargo customizáveis.
  - `GRUPOS_PERMISSOES: list[tuple[str, list[str]]]` — `[(nome_do_grupo, [permissao1, permissao2, ...]), ...]`.
  - `LABEL_PERMISSAO: dict[str, str]` — permissão (a string, ex. `"ver_locacoes"`) → rótulo em português pra exibir na tela.
  - `_permissoes_do_role(role, company_id)` muda de assinatura (era `_permissoes_do_role(role)`) — só é usada dentro do próprio módulo, então nenhum código externo quebra.
  - `tem_permissao(permissao)` e `tem_role(*roles)` mantêm a MESMA assinatura pública — nenhuma das ~13 rotas que já usam `tem_permissao`/`requer_permissao` precisa mudar.

- [ ] **Step 1: Adicionar os imports novos no topo do arquivo**

Depois de `from flask_login import current_user`, adicione:

```python
from flask import g
from database import get_db_connection
```

- [ ] **Step 2: Substituir `_permissoes_do_role` e `tem_permissao`**

Local atual (por volta da linha 80-90):

```python
def _permissoes_do_role(role):
    if role in ROLES_ACESSO_TOTAL:
        return None  # None = coringa, libera qualquer permissão
    return PERMISSOES_POR_ROLE.get(role, set())


def tem_permissao(permissao):
    if not current_user.is_authenticated:
        return False
    permissoes = _permissoes_do_role(getattr(current_user, "role", None))
    return permissoes is None or permissao in permissoes
```

Troque por:

```python
def _permissoes_do_role(role, company_id):
    if role in ROLES_ACESSO_TOTAL:
        return None  # None = coringa, libera qualquer permissão — sem consulta ao banco

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

`tem_role` não muda — deixe como está.

- [ ] **Step 3: Adicionar `CARGOS_CUSTOMIZAVEIS`, `GRUPOS_PERMISSOES` e `LABEL_PERMISSAO`**

Logo depois do dict `PERMISSOES_POR_ROLE` (antes de `_ROTA_POR_PERMISSAO`), adicione:

```python
CARGOS_CUSTOMIZAVEIS = ("financeiro", "atendente", "vendedor", "tecnico", "estoquista", "entregador")

# Só pra exibição na tela de Configurações — não muda nenhum comportamento
# de autorização.
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

- [ ] **Step 4: Verificar que o arquivo importa sem erro**

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import app as flaskapp
print('IMPORT OK')
"
```

Expected: `IMPORT OK`.

- [ ] **Step 5: Verificar `GRUPOS_PERMISSOES`/`LABEL_PERMISSAO` cobrem exatamente as mesmas 27 permissões que já existem**

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import permissions as p

todas_constantes = {
    v for k, v in vars(p).items()
    if k.isupper() and isinstance(v, str) and k not in ('CARGOS_CUSTOMIZAVEIS',)
}
# Remove strings que não são nomes de permissão (não há outras strings maiúsculas no módulo,
# mas a checagem abaixo é o que importa de verdade):
do_grupo = {perm for _, perms in p.GRUPOS_PERMISSOES for perm in perms}
do_label = set(p.LABEL_PERMISSAO.keys())

assert do_grupo == do_label, f'GRUPOS_PERMISSOES e LABEL_PERMISSAO cobrem conjuntos diferentes: {do_grupo ^ do_label}'
print('OK: GRUPOS_PERMISSOES e LABEL_PERMISSAO cobrem exatamente as mesmas', len(do_grupo), 'permissoes')

# Todo cargo customizavel deve ter um conjunto padrao definido em PERMISSOES_POR_ROLE
for cargo in p.CARGOS_CUSTOMIZAVEIS:
    assert cargo in p.PERMISSOES_POR_ROLE, f'{cargo} nao tem padrao em PERMISSOES_POR_ROLE'
print('OK: todos os', len(p.CARGOS_CUSTOMIZAVEIS), 'cargos customizaveis tem padrao definido')
"
```

Expected: `OK: GRUPOS_PERMISSOES e LABEL_PERMISSAO cobrem exatamente as mesmas 27 permissoes` e `OK: todos os 6 cargos customizaveis tem padrao definido`.

- [ ] **Step 6: Verificar `_permissoes_do_role` contra o banco real (fallback, override, cache)**

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import psycopg2, os, json
from psycopg2.extras import RealDictCursor
from flask import Flask, g
import permissions as p

app = Flask(__name__)

with app.app_context():
    conn = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require', cursor_factory=RealDictCursor)
    cur = conn.cursor()

    # 1. Sem override -> usa o padrao fixo do codigo
    resultado = p._permissoes_do_role('atendente', 1)
    assert resultado == p.PERMISSOES_POR_ROLE['atendente'], resultado
    print('OK: sem override, usa o padrao fixo')

    # 2. Cache por request (g): muda o banco por baixo, mas dentro do mesmo
    # app_context/request o resultado cacheado nao muda
    cur.execute(\"INSERT INTO permissoes_customizadas (company_id, role, permissoes) VALUES (1, 'atendente', %s)\", (json.dumps(['ver_locacoes']),))
    conn.commit()
    resultado_cacheado = p._permissoes_do_role('atendente', 1)
    assert resultado_cacheado == p.PERMISSOES_POR_ROLE['atendente'], 'deveria ter vindo do cache, nao da nova linha'
    print('OK: cache por request funcionando (nao rebateu no banco)')

    cur.execute('DELETE FROM permissoes_customizadas WHERE company_id=1')
    conn.commit()
    conn.close()

# 3. Novo app_context (novo 'request') -> sem cache, le a config nova do banco
with app.app_context():
    conn = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require', cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute(\"INSERT INTO permissoes_customizadas (company_id, role, permissoes) VALUES (1, 'atendente', %s)\", (json.dumps(['ver_locacoes']),))
    conn.commit()

    resultado = p._permissoes_do_role('atendente', 1)
    assert resultado == {'ver_locacoes'}, resultado
    print('OK: override customizado (so ver_locacoes) lido corretamente')

    # 4. Override vazio -> nega tudo (nao cai no fallback)
    cur.execute(\"UPDATE permissoes_customizadas SET permissoes=%s WHERE company_id=1 AND role='atendente'\", (json.dumps([]),))
    conn.commit()

with app.app_context():
    conn2 = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require', cursor_factory=RealDictCursor)
    resultado_vazio = p._permissoes_do_role('atendente', 1)
    assert resultado_vazio == set(), f'override vazio deveria negar tudo, veio {resultado_vazio}'
    print('OK: override vazio nega tudo (nao cai no fallback)')
    conn2.close()

    # limpeza
    conn3 = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require')
    cur3 = conn3.cursor()
    cur3.execute('DELETE FROM permissoes_customizadas WHERE company_id=1')
    conn3.commit()
    conn3.close()

# 5. Cargo de acesso total nunca bate no banco
with app.app_context():
    assert p._permissoes_do_role('super_admin', 1) is None
    print('OK: super_admin retorna None (coringa) sem consultar banco')
"
```

Expected: as 5 linhas `OK: ...` impressas, sem exceção. O script já limpa os dados de teste que insere.

- [ ] **Step 7: Commit**

```bash
git add permissions.py
git commit -m "permissions.py: torna permissões por cargo cientes de empresa, com fallback e cache por request"
```

---

## Task 3: Seção "Permissões por Cargo" em `/configuracoes`

**Files:**
- Modify: `routes/configuracoes_routes.py`
- Modify: `templates/configuracoes.html`

**Interfaces:**
- Consumes: `CARGOS_CUSTOMIZAVEIS`, `GRUPOS_PERMISSOES`, `LABEL_PERMISSAO` de `permissions.py` (Task 2); tabela `permissoes_customizadas` (Task 1).
- Produces: nova rota `configuracoes.salvar_permissoes` (POST), endpoint usado só por este template.

- [ ] **Step 1: Adicionar os imports novos em `routes/configuracoes_routes.py`**

No topo do arquivo, junto dos outros imports:

```python
import json

from permissions import requer_role, CARGOS_CUSTOMIZAVEIS, GRUPOS_PERMISSOES, LABEL_PERMISSAO, PERMISSOES_POR_ROLE
```

(troque a linha `from permissions import requer_role` já existente por essa, que importa tudo de uma vez.)

- [ ] **Step 2: Buscar a matriz de permissões efetivas no GET de `pagina_configuracoes`**

Local atual, final da função (por volta da linha 59-63):

```python
    cur.execute("SELECT * FROM config_asaas WHERE company_id=%s", (current_user.company_id,))
    config = cur.fetchone()
    cur.close()
    conn.close()
    return render_template("configuracoes.html", config=config, ambientes=AMBIENTES_ASAAS)
```

Troque por (busca as customizações da empresa e monta o conjunto efetivo por cargo, pra pré-marcar os checkboxes):

```python
    cur.execute("SELECT * FROM config_asaas WHERE company_id=%s", (current_user.company_id,))
    config = cur.fetchone()

    cur.execute(
        "SELECT role, permissoes FROM permissoes_customizadas WHERE company_id=%s",
        (current_user.company_id,),
    )
    customizadas_por_cargo = {row["role"]: set(row["permissoes"]) for row in cur.fetchall()}

    permissoes_efetivas = {
        cargo: customizadas_por_cargo.get(cargo, PERMISSOES_POR_ROLE.get(cargo, set()))
        for cargo in CARGOS_CUSTOMIZAVEIS
    }

    cur.close()
    conn.close()
    return render_template(
        "configuracoes.html",
        config=config,
        ambientes=AMBIENTES_ASAAS,
        cargos=CARGOS_CUSTOMIZAVEIS,
        grupos_permissoes=GRUPOS_PERMISSOES,
        label_permissao=LABEL_PERMISSAO,
        permissoes_efetivas=permissoes_efetivas,
    )
```

- [ ] **Step 3: Adicionar a rota `salvar_permissoes`**

No final do arquivo, depois da função `pagina_configuracoes`:

```python
@configuracoes_bp.route("/permissoes", methods=["POST"])
@login_required
@requer_role("super_admin", "admin_locadora")
def salvar_permissoes():
    todas_permissoes = {perm for _, perms in GRUPOS_PERMISSOES for perm in perms}

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        for cargo in CARGOS_CUSTOMIZAVEIS:
            marcadas = request.form.getlist(f"perm__{cargo}")
            marcadas_validas = [p for p in marcadas if p in todas_permissoes]
            cur.execute("""
                INSERT INTO permissoes_customizadas (company_id, role, permissoes)
                VALUES (%s, %s, %s)
                ON CONFLICT (company_id, role) DO UPDATE SET
                    permissoes = EXCLUDED.permissoes
            """, (current_user.company_id, cargo, json.dumps(marcadas_validas)))
        conn.commit()
        flash("Permissões salvas com sucesso!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao salvar permissões: {e}", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("configuracoes.pagina_configuracoes"))
```

Nota: `request.form.getlist(f"perm__{cargo}")` funciona porque no template (Step 4) cada checkbox de um cargo usa `name="perm__<cargo>"` e `value="<permissao>"` — checkboxes desmarcados simplesmente não aparecem na lista, que é exatamente o comportamento HTML padrão de formulário (não precisa de campo escondido pra "desmarcado").

- [ ] **Step 4: Adicionar o card "Permissões por Cargo" em `templates/configuracoes.html`**

Local atual — final do arquivo, logo antes de `{% endblock %}`:

```html
    <small class="text-muted d-block mt-3">
      Se nenhuma chave própria for configurada, o sistema usa a chave padrão da plataforma (se houver).
    </small>
  </div>
</div>
{% endblock %}
```

Troque por (adiciona o segundo card, com form e rota próprios):

```html
    <small class="text-muted d-block mt-3">
      Se nenhuma chave própria for configurada, o sistema usa a chave padrão da plataforma (se houver).
    </small>
  </div>
</div>

<div class="card shadow-sm mt-4">
  <div class="card-header bg-primary text-white">
    <i class="fa-solid fa-user-shield me-1"></i> Permissões por Cargo
  </div>
  <div class="card-body">
    <form method="post" action="{{ url_for('configuracoes.salvar_permissoes') }}">
      <div class="table-responsive">
        <table class="table table-sm table-bordered align-middle">
          <thead>
            <tr>
              <th>Permissão</th>
              {% for cargo in cargos %}
              <th class="text-center text-capitalize">{{ cargo }}</th>
              {% endfor %}
            </tr>
          </thead>
          <tbody>
            {% for nome_grupo, permissoes_do_grupo in grupos_permissoes %}
            <tr class="table-light">
              <td colspan="{{ cargos|length + 1 }}"><strong>{{ nome_grupo }}</strong></td>
            </tr>
            {% for permissao in permissoes_do_grupo %}
            <tr>
              <td>{{ label_permissao[permissao] }}</td>
              {% for cargo in cargos %}
              <td class="text-center">
                <input type="checkbox" class="form-check-input" name="perm__{{ cargo }}" value="{{ permissao }}"
                       {% if permissao in permissoes_efetivas[cargo] %}checked{% endif %}>
              </td>
              {% endfor %}
            </tr>
            {% endfor %}
            {% endfor %}
          </tbody>
        </table>
      </div>

      <div class="mt-3">
        <button class="btn btn-success">
          <i class="fa-solid fa-save me-1"></i> Salvar Permissões
        </button>
      </div>
    </form>

    <small class="text-muted d-block mt-3">
      Cargos não customizados aqui usam o padrão do sistema. Assim que você salvar, o cargo passa a usar
      exatamente o que estiver marcado (mesmo que isso signifique remover acessos que ele tinha antes).
    </small>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Verificar que o app importa e a rota está registrada**

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import app as flaskapp
print('IMPORT OK')
for r in flaskapp.app.url_map.iter_rules():
    if 'permissoes' in str(r):
        print(' ', r, r.methods)
"
```

Expected: `IMPORT OK` e uma linha `/configuracoes/permissoes {'POST', 'OPTIONS'}`.

- [ ] **Step 6: Commit**

```bash
git add routes/configuracoes_routes.py templates/configuracoes.html
git commit -m "Adiciona seção Permissões por Cargo em /configuracoes"
```

---

## Task 4: Verificação end-to-end (rota real bloqueada/liberada conforme a permissão)

**Files:** nenhum arquivo novo — só verificação.

**Interfaces:**
- Consumes: tudo das Tasks 1-3.

- [ ] **Step 1: Criar um usuário de teste com role 'atendente' pra empresa 1, salvar uma customização, e confirmar via `app.test_client()` que uma rota protegida por `VER_LOCACOES` reflete a mudança**

Este script usa `flask_login.login_user()` diretamente dentro do contexto de teste do Flask — não é um formulário de login, é a forma padrão de simular uma sessão autenticada em testes. Não digita nenhuma senha em lugar nenhum.

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import psycopg2, os, json
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash
import app as flaskapp
from models.user import User

conn = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require', cursor_factory=RealDictCursor)
cur = conn.cursor()

# Cria um usuario de teste 'atendente' pra empresa 1 (senha so pra existir a coluna, nunca usada)
cur.execute(\"DELETE FROM usuarios WHERE username='teste_perm_atendente'\")
cur.execute('''
    INSERT INTO usuarios (username, email, senha, role, company_id)
    VALUES ('teste_perm_atendente', 'teste_perm_atendente@example.com', %s, 'atendente', 1)
    RETURNING id
''', (generate_password_hash('senha-descartavel-de-teste'),))
user_id = cur.fetchone()['id']
conn.commit()

client = flaskapp.app.test_client()

def logar_como(uid):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)
        sess['_fresh'] = True

# 1. Sem customizacao: atendente tem VER_LOCACOES por padrao (confirmado em PERMISSOES_POR_ROLE) -> acessa
logar_como(user_id)
resp = client.get('/locacoes/')
assert resp.status_code == 200, f'esperava 200 (acesso liberado por padrao), veio {resp.status_code}'
print('OK: atendente sem customizacao acessa /locacoes/ (permissao padrao)')

# 2. Customiza o cargo 'atendente' pra empresa 1 SEM ver_locacoes -> passa a bloquear
cur.execute(\"DELETE FROM permissoes_customizadas WHERE company_id=1 AND role='atendente'\")
cur.execute('''
    INSERT INTO permissoes_customizadas (company_id, role, permissoes)
    VALUES (1, 'atendente', %s)
''', (json.dumps(['ver_clientes']),))  # sem ver_locacoes de proposito
conn.commit()

client2 = flaskapp.app.test_client()  # cliente novo -> contexto de app novo -> sem cache de g
def logar_como2(uid):
    with client2.session_transaction() as sess:
        sess['_user_id'] = str(uid)
        sess['_fresh'] = True
logar_como2(user_id)
resp2 = client2.get('/locacoes/')
assert resp2.status_code in (302, 303), f'esperava redirect (acesso negado), veio {resp2.status_code}'
print('OK: atendente customizado sem ver_locacoes eh bloqueado em /locacoes/')

resp3 = client2.get('/clientes/')
assert resp3.status_code == 200, f'ver_clientes deveria continuar liberado, veio {resp3.status_code}'
print('OK: ver_clientes (que ficou marcado) continua liberado pro mesmo usuario')

# Limpeza
cur.execute('DELETE FROM permissoes_customizadas WHERE company_id=1 AND role=%s', ('atendente',))
cur.execute('DELETE FROM usuarios WHERE id=%s', (user_id,))
conn.commit()
conn.close()
print('Limpeza concluida.')
"
```

Expected: as 3 linhas `OK: ...` e `Limpeza concluida.`, sem exceção. Se o teste de usuário/senha der erro por alguma constraint diferente da esperada (ex: `company_id` obrigatório, coluna a mais), ajuste o INSERT conforme o schema real de `usuarios` — não pule a verificação.

- [ ] **Step 2: Testar salvar_permissoes via `app.test_client()` (POST simulando o formulário, sem navegador)**

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import psycopg2, os
from psycopg2.extras import RealDictCursor
import app as flaskapp

conn = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require', cursor_factory=RealDictCursor)
cur = conn.cursor()
cur.execute(\"SELECT id FROM usuarios WHERE username='admin'\")
admin_id = cur.fetchone()['id']

client = flaskapp.app.test_client()
with client.session_transaction() as sess:
    sess['_user_id'] = str(admin_id)
    sess['_fresh'] = True

resp = client.post('/configuracoes/permissoes', data={
    'perm__atendente': ['ver_locacoes', 'ver_clientes'],
    # os outros 5 cargos ficam sem nenhum campo -> tratados como 'nada marcado' (lista vazia)
}, follow_redirects=False)
assert resp.status_code in (302, 303), resp.status_code

cur.execute(\"SELECT permissoes FROM permissoes_customizadas WHERE company_id=1 AND role='atendente'\")
row = cur.fetchone()
assert set(row['permissoes']) == {'ver_locacoes', 'ver_clientes'}, row

cur.execute(\"SELECT permissoes FROM permissoes_customizadas WHERE company_id=1 AND role='vendedor'\")
row_vendedor = cur.fetchone()
assert row_vendedor is not None and row_vendedor['permissoes'] == [], 'cargo sem checkbox marcado deveria salvar lista vazia, nao ficar sem linha'
print('OK: POST em /configuracoes/permissoes grava os 6 cargos, marcado e vazio corretamente')

cur.execute('DELETE FROM permissoes_customizadas WHERE company_id=1')
conn.commit()
conn.close()
print('Limpeza concluida.')
"
```

Expected: `OK: ...` e `Limpeza concluida.`, sem exceção.

- [ ] **Step 3: Nenhum commit nesta task (só verificação) — se tudo passou, task concluída**
