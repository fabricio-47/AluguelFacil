# Asaas por empresa (multi-tenant) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cada empresa (tenant) do AluguelFacil configura a própria chave Asaas (e webhook secret) numa tela de Configurações dentro do sistema, em vez de depender de uma única `ASAAS_API_KEY` global no Render.

**Architecture:** Nova tabela `config_asaas` (uma linha por empresa, mesmo padrão de `config_multas`), módulo `asaas_config.py` centraliza cifra/decifra (Fernet) e leitura das credenciais com fallback pra config global, tela `/configuracoes` pra editar, e os 3 arquivos que hoje chamam a API Asaas com a chave global passam a chamar `obter_config_asaas(cur, current_user.company_id)` primeiro.

**Tech Stack:** Flask, psycopg2 (RealDictCursor via `database.get_db_connection()`), `cryptography` (Fernet, novo), Jinja2/Bootstrap pros templates.

**Spec:** `docs/superpowers/specs/2026-08-17-asaas-por-empresa-design.md`

## Global Constraints

- `get_db_connection()` (em `database.py`) já retorna cursor com `RealDictCursor` — toda leitura é dict-like (`row["coluna"]`), nunca índice numérico. Todo código novo segue isso.
- Este projeto **não tem suíte de testes automatizada** (sem pytest, sem `tests/`). Cada task usa um **script de verificação standalone** (`python -c "..."` ou um arquivo descartável) que roda contra o banco real (Render, já configurado em `.env` via `DATABASE_URL`) em vez de "escrever o teste, rodar pytest". É a mesma forma de verificação já usada nas features anteriores desta sessão. Sempre que o script criar dados de teste, o próprio step de verificação apaga esses dados no final.
- Nunca commitar `.env` (já está no `.gitignore`).
- Toda migration SQL é idempotente (`ADD COLUMN IF NOT EXISTS`, `CREATE TABLE IF NOT EXISTS`) — mesmo padrão das migrations 002-014 já existentes em `migrations/`.
- `current_user.company_id` está sempre disponível dentro de qualquer função chamada durante uma request (Flask-Login `current_user` é um proxy de contexto, funciona em helpers que não são rotas diretamente, ex: `criar_locacao_interna`, `executar_cancelamento_locacao`).

---

## Task 1: Tabela `config_asaas` + config de infraestrutura (encryption key, dependência)

**Files:**
- Create: `migrations/015_config_asaas.sql`
- Modify: `config.py` (adiciona `APP_ENCRYPTION_KEY`)
- Modify: `requirements.txt` (adiciona `cryptography`)

**Interfaces:**
- Produces: tabela `config_asaas(id, company_id, api_key_cifrada, webhook_secret_cifrado, ambiente, ativo, created_at, updated_at)` no banco; `Config.APP_ENCRYPTION_KEY` (string) disponível pro resto do plano.

- [ ] **Step 1: Escrever a migration**

Crie `migrations/015_config_asaas.sql`:

```sql
-- Migration 015: chave Asaas por empresa (multi-tenant), substitui a
-- dependência de uma única ASAAS_API_KEY global no Render.
--
-- Só estrutura (DDL). Idempotente. Aditiva.
-- Mesmo padrão de config_multas (migration 006): uma linha por empresa,
-- upsert via ON CONFLICT (company_id).

CREATE TABLE IF NOT EXISTS config_asaas (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL UNIQUE REFERENCES companies(id),

    api_key_cifrada TEXT,
    webhook_secret_cifrado TEXT,
    ambiente VARCHAR(20) NOT NULL DEFAULT 'sandbox',
    ativo BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_config_asaas_ambiente CHECK (ambiente IN ('sandbox', 'producao'))
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_config_asaas_updated') THEN
        CREATE TRIGGER trg_config_asaas_updated
        BEFORE UPDATE ON config_asaas
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END$$;
```

- [ ] **Step 2: Aplicar a migration no banco real e verificar**

Rode (mesmo padrão usado nas migrations 013/014 desta sessão):

```bash
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
import psycopg2
conn = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require')
cur = conn.cursor()
with open('migrations/015_config_asaas.sql', encoding='utf-8') as f:
    cur.execute(f.read())
conn.commit()
cur.execute(\"SELECT column_name FROM information_schema.columns WHERE table_name='config_asaas' ORDER BY column_name\")
print([r[0] for r in cur.fetchall()])
conn.close()
"
```

Expected: lista com `['ambiente', 'api_key_cifrada', 'ativo', 'company_id', 'created_at', 'id', 'updated_at', 'webhook_secret_cifrado']`.

Se a ação for bloqueada pelo classificador do Claude Code (já aconteceu nesta sessão pra `ALTER TABLE`/DDL em produção), pare e peça confirmação explícita ao usuário antes de rodar — não tente contornar.

- [ ] **Step 3: Gerar a `APP_ENCRYPTION_KEY` e adicionar em `config.py`**

Gere uma chave Fernet válida:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

(Se `cryptography` ainda não estiver instalado localmente, rode `pip install cryptography` antes — vai virar dependência do projeto no Step 5.)

Guarde o valor gerado — vai ser usado no Step 6 (adicionar no `.env` local) e depois configurado no Render (fora do escopo deste plano automatizável; avise o usuário no fim da task).

Em `config.py`, depois do bloco de `# Cohere (assistente de IA interno)`, adicione:

```python
    # Criptografia de credenciais por empresa (Asaas, e futuramente outras)
    APP_ENCRYPTION_KEY = os.getenv("APP_ENCRYPTION_KEY")
```

- [ ] **Step 4: Adicionar `cryptography` em `requirements.txt`**

Adicione uma linha no final de `requirements.txt`:

```
cryptography>=42.0.0
```

- [ ] **Step 5: Instalar a dependência localmente**

```bash
pip install "cryptography>=42.0.0"
```

Expected: instala sem erro (ou confirma que já está instalado, do Step 3).

- [ ] **Step 6: Adicionar a chave gerada no `.env` local**

Edite `.env` (nunca commitar) adicionando a linha (com o valor real gerado no Step 3):

```
APP_ENCRYPTION_KEY=<valor gerado no Step 3>
```

- [ ] **Step 7: Commit**

```bash
git add migrations/015_config_asaas.sql config.py requirements.txt
git commit -m "Adiciona tabela config_asaas + APP_ENCRYPTION_KEY (infra pra chave Asaas por empresa)"
```

---

## Task 2: Módulo `asaas_config.py` (cifra/decifra + leitura de credenciais)

**Files:**
- Create: `asaas_config.py`

**Interfaces:**
- Consumes: `Config.APP_ENCRYPTION_KEY`, `Config.ASAAS_API_KEY`, `Config.ASAAS_BASE_URL`, `Config.ASAAS_WEBHOOK_SECRET` (de `config.py`, Task 1); tabela `config_asaas` (Task 1).
- Produces (usado pelas Tasks 3-6):
  - `cifrar(texto: str | None) -> str | None`
  - `decifrar(texto_cifrado: str | None) -> str | None`
  - `obter_config_asaas(cur, company_id: int) -> dict` com chaves `api_key`, `base_url`, `webhook_secret`
  - `todos_webhook_secrets_validos(cur) -> set[str]`

- [ ] **Step 1: Escrever `asaas_config.py`**

```python
from cryptography.fernet import Fernet

from config import Config

BASE_URL_POR_AMBIENTE = {
    "sandbox": "https://sandbox.asaas.com/api/v3",
    "producao": "https://api.asaas.com/v3",
}


def _fernet():
    if not Config.APP_ENCRYPTION_KEY:
        raise RuntimeError("APP_ENCRYPTION_KEY ausente — infraestrutura de criptografia não configurada.")
    return Fernet(Config.APP_ENCRYPTION_KEY.encode())


def cifrar(texto):
    if not texto:
        return None
    return _fernet().encrypt(texto.encode()).decode()


def decifrar(texto_cifrado):
    if not texto_cifrado:
        return None
    return _fernet().decrypt(texto_cifrado.encode()).decode()


def obter_config_asaas(cur, company_id):
    """
    Retorna as credenciais Asaas da empresa: {api_key, base_url, webhook_secret}.
    Se a empresa não tiver config própria (ou estiver inativa), cai pra
    config global (Config.ASAAS_API_KEY/ASAAS_BASE_URL/ASAAS_WEBHOOK_SECRET).
    """
    cur.execute("SELECT * FROM config_asaas WHERE company_id=%s AND ativo=TRUE", (company_id,))
    row = cur.fetchone()
    if row and row["api_key_cifrada"]:
        return {
            "api_key": decifrar(row["api_key_cifrada"]),
            "base_url": BASE_URL_POR_AMBIENTE.get(row["ambiente"], BASE_URL_POR_AMBIENTE["sandbox"]),
            "webhook_secret": decifrar(row["webhook_secret_cifrado"]) if row["webhook_secret_cifrado"] else None,
        }
    return {
        "api_key": Config.ASAAS_API_KEY,
        "base_url": Config.ASAAS_BASE_URL,
        "webhook_secret": Config.ASAAS_WEBHOOK_SECRET,
    }


def todos_webhook_secrets_validos(cur):
    """Conjunto de todos os webhook secrets válidos (todas as empresas
    configuradas + o global), já decifrados, pra validar requests recebidos."""
    secrets = set()
    if Config.ASAAS_WEBHOOK_SECRET:
        secrets.add(Config.ASAAS_WEBHOOK_SECRET.strip())
    cur.execute(
        "SELECT webhook_secret_cifrado FROM config_asaas WHERE ativo=TRUE AND webhook_secret_cifrado IS NOT NULL"
    )
    for row in cur.fetchall():
        valor = decifrar(row["webhook_secret_cifrado"])
        if valor:
            secrets.add(valor.strip())
    return secrets
```

- [ ] **Step 2: Verificar cifra/decifra com um script standalone**

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
from asaas_config import cifrar, decifrar

original = 'minha-chave-secreta-123'
cifrado = cifrar(original)
assert cifrado != original, 'deveria estar cifrado, nao em texto puro'
assert decifrar(cifrado) == original, 'roundtrip falhou'
assert cifrar(None) is None
assert decifrar(None) is None
print('OK: cifra/decifra funcionando')
"
```

Expected: imprime `OK: cifra/decifra funcionando`, sem exceção.

- [ ] **Step 3: Verificar `obter_config_asaas` (fallback global) com um script standalone**

Usa a empresa `id=1` (já existente, "Minha Locadora Original" — confirmada no início desta sessão), que ainda não tem linha em `config_asaas`:

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from asaas_config import obter_config_asaas
from config import Config

conn = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require', cursor_factory=RealDictCursor)
cur = conn.cursor()
resultado = obter_config_asaas(cur, 1)
assert resultado['api_key'] == Config.ASAAS_API_KEY, 'deveria cair no fallback global'
assert resultado['base_url'] == Config.ASAAS_BASE_URL
print('OK: fallback global funcionando ->', resultado)
conn.close()
"
```

Expected: imprime `OK: fallback global funcionando -> {...}` (com `api_key` igual ao valor de `Config.ASAAS_API_KEY`, que pode ser `None` se ainda não configurado — tudo bem, é o comportamento atual).

- [ ] **Step 4: Verificar `obter_config_asaas` com config própria da empresa (insere linha de teste, confirma, apaga)**

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from asaas_config import obter_config_asaas, cifrar

conn = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require', cursor_factory=RealDictCursor)
cur = conn.cursor()

cur.execute('''
    INSERT INTO config_asaas (company_id, api_key_cifrada, webhook_secret_cifrado, ambiente, ativo)
    VALUES (1, %s, %s, 'sandbox', TRUE)
''', (cifrar('chave-de-teste-empresa-1'), cifrar('webhook-secret-teste')))
conn.commit()

resultado = obter_config_asaas(cur, 1)
assert resultado['api_key'] == 'chave-de-teste-empresa-1', resultado
assert resultado['base_url'] == 'https://sandbox.asaas.com/api/v3', resultado
assert resultado['webhook_secret'] == 'webhook-secret-teste', resultado
print('OK: config propria da empresa funcionando ->', resultado)

cur.execute('DELETE FROM config_asaas WHERE company_id=1')
conn.commit()
conn.close()
"
```

Expected: imprime `OK: config propria da empresa funcionando -> {...}`, sem exceção. A linha de teste é apagada no final do próprio script (não deixa lixo no banco).

- [ ] **Step 5: Commit**

```bash
git add asaas_config.py
git commit -m "Adiciona asaas_config.py: cifra/decifra e leitura de credenciais Asaas por empresa"
```

---

## Task 3: Tela `/configuracoes` (blueprint, template, nav, registro no app)

**Files:**
- Create: `routes/configuracoes_routes.py`
- Create: `templates/configuracoes.html`
- Modify: `app.py` (importar e registrar o blueprint)
- Modify: `templates/base.html` (link "Configurações" no menu)

**Interfaces:**
- Consumes: `obter_config_asaas` não é usado aqui (essa tela só grava, não decide credencial pra chamar API); usa `cifrar`/`decifrar` de `asaas_config.py` (Task 2), `requer_role` de `permissions.py` (já existe), `get_db_connection` de `database.py` (já existe).
- Produces: rota `configuracoes.pagina_configuracoes` (endpoint Flask), acessível em `/configuracoes/`.

- [ ] **Step 1: Escrever `routes/configuracoes_routes.py`**

```python
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from database import get_db_connection
from permissions import requer_role
from asaas_config import cifrar

configuracoes_bp = Blueprint("configuracoes", __name__, url_prefix="/configuracoes")

AMBIENTES_ASAAS = ("sandbox", "producao")


@configuracoes_bp.route("/", methods=["GET", "POST"])
@login_required
@requer_role("super_admin", "admin_locadora")
def pagina_configuracoes():
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        ambiente = request.form.get("ambiente")
        if ambiente not in AMBIENTES_ASAAS:
            cur.close()
            conn.close()
            flash("Ambiente inválido.", "warning")
            return redirect(url_for("configuracoes.pagina_configuracoes"))

        api_key_nova = (request.form.get("api_key") or "").strip()
        webhook_secret_novo = (request.form.get("webhook_secret") or "").strip()

        try:
            cur.execute("SELECT api_key_cifrada, webhook_secret_cifrado FROM config_asaas WHERE company_id=%s", (current_user.company_id,))
            atual = cur.fetchone()

            # Campo em branco = mantém o valor já salvo (nunca apaga sem querer).
            api_key_cifrada = cifrar(api_key_nova) if api_key_nova else (atual["api_key_cifrada"] if atual else None)
            webhook_secret_cifrado = cifrar(webhook_secret_novo) if webhook_secret_novo else (atual["webhook_secret_cifrado"] if atual else None)

            cur.execute("""
                INSERT INTO config_asaas (company_id, api_key_cifrada, webhook_secret_cifrado, ambiente, ativo)
                VALUES (%s, %s, %s, %s, TRUE)
                ON CONFLICT (company_id) DO UPDATE SET
                    api_key_cifrada = EXCLUDED.api_key_cifrada,
                    webhook_secret_cifrado = EXCLUDED.webhook_secret_cifrado,
                    ambiente = EXCLUDED.ambiente,
                    ativo = TRUE
            """, (current_user.company_id, api_key_cifrada, webhook_secret_cifrado, ambiente))
            conn.commit()
            flash("Configuração do Asaas salva com sucesso!", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Erro ao salvar configuração: {e}", "danger")
        finally:
            cur.close()
            conn.close()

        return redirect(url_for("configuracoes.pagina_configuracoes"))

    cur.execute("SELECT * FROM config_asaas WHERE company_id=%s", (current_user.company_id,))
    config = cur.fetchone()
    cur.close()
    conn.close()
    return render_template("configuracoes.html", config=config, ambientes=AMBIENTES_ASAAS)
```

- [ ] **Step 2: Escrever `templates/configuracoes.html`**

```html
{% extends "base.html" %}
{% block title %}Configurações{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
  <h2>Configurações</h2>
</div>

<div class="card shadow-sm">
  <div class="card-header bg-primary text-white">
    <i class="fa-solid fa-money-check-dollar me-1"></i> Integração com Asaas
  </div>
  <div class="card-body">
    <form method="post">
      <div class="row g-3">
        <div class="col-md-6">
          <label class="form-label">Chave da API (Access Token)</label>
          <input type="password" name="api_key" class="form-control"
                 placeholder="{% if config and config.api_key_cifrada %}•••• chave configurada (deixe em branco pra manter){% else %}Cole aqui a API key da sua conta Asaas{% endif %}">
          <small class="text-muted">Nunca exibida depois de salva — só é possível substituir.</small>
        </div>
        <div class="col-md-6">
          <label class="form-label">Webhook Secret</label>
          <input type="password" name="webhook_secret" class="form-control"
                 placeholder="{% if config and config.webhook_secret_cifrado %}•••• configurado (deixe em branco pra manter){% else %}Opcional — token que você define no painel do Asaas{% endif %}">
        </div>
        <div class="col-md-6">
          <label class="form-label">Ambiente</label>
          <select name="ambiente" class="form-select">
            {% for a in ambientes %}
            <option value="{{ a }}" {% if config and config.ambiente == a %}selected{% endif %}>
              {{ "Sandbox (testes)" if a == "sandbox" else "Produção" }}
            </option>
            {% endfor %}
          </select>
        </div>
      </div>

      <div class="mt-4">
        <button class="btn btn-success">
          <i class="fa-solid fa-save me-1"></i> Salvar Configuração
        </button>
      </div>
    </form>

    <small class="text-muted d-block mt-3">
      Se nenhuma chave própria for configurada, o sistema usa a chave padrão da plataforma (se houver).
    </small>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Registrar o blueprint em `app.py`**

Adicione o import junto dos outros (`from routes.assistente_routes import assistente_bp` é o último, em `app.py`):

```python
from routes.configuracoes_routes import configuracoes_bp
```

E o registro, junto dos outros `app.register_blueprint(...)` (depois de `app.register_blueprint(assistente_bp)`):

```python
app.register_blueprint(configuracoes_bp)
```

- [ ] **Step 4: Adicionar o link "Configurações" no menu (`templates/base.html`)**

Encontre o bloco do link "Usuários" em `base.html` (por volta da linha 183-189) e adicione logo depois, seguindo o mesmo estilo:

```html
    <!-- Configurações -->
    <li class="nav-item">
    <a class="nav-link {% if request.endpoint and request.endpoint.startswith('configuracoes.') %}active{% endif %}"
    href="{{ url_for('configuracoes.pagina_configuracoes') }}">
    <i class="fa-solid fa-gear me-1"></i>Configurações
    </a>
    </li>
```

- [ ] **Step 5: Verificar que o app importa e a rota está registrada**

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import app as flaskapp
print('IMPORT OK')
for r in flaskapp.app.url_map.iter_rules():
    if 'configuracoes' in str(r):
        print(' ', r, r.methods)
"
```

Expected: `IMPORT OK` e uma linha `/configuracoes/ {'GET', 'HEAD', 'POST', 'OPTIONS'}`.

- [ ] **Step 6: Testar no navegador (servidor local, dados reais do Render)**

Suba o servidor local (mesmo padrão usado nas features anteriores desta sessão — criar `_run_local.py` temporário com `load_dotenv()` + `app.run(host="127.0.0.1", port=5050)`, rodar em background, checar `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5050/` até responder).

No navegador (logado como `admin@admin.com`/`admin`, que é `super_admin` — passa no `@requer_role`):
1. Abrir `http://127.0.0.1:5050/configuracoes/` — confirmar que a página carrega com os campos vazios (nenhuma config ainda) e placeholder "Cole aqui a API key...".
2. Preencher API key `teste-sandbox-123`, Webhook Secret `webhook-teste-456`, Ambiente `Sandbox`, salvar.
3. Confirmar flash "Configuração do Asaas salva com sucesso!" e que o campo de API key volta vazio com placeholder "•••• chave configurada (deixe em branco pra manter)".
4. Salvar de novo deixando os dois campos de chave em branco, só trocando o ambiente pra "Produção" — confirmar (via script Python, abaixo) que `api_key_cifrada`/`webhook_secret_cifrado` continuam os mesmos, só `ambiente` mudou.

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from asaas_config import decifrar

conn = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require', cursor_factory=RealDictCursor)
cur = conn.cursor()
cur.execute('SELECT * FROM config_asaas WHERE company_id=1')
row = cur.fetchone()
print('ambiente:', row['ambiente'])
print('api_key decifrada:', decifrar(row['api_key_cifrada']))
print('webhook_secret decifrado:', decifrar(row['webhook_secret_cifrado']))
conn.close()
"
```

Expected: `api_key decifrada: teste-sandbox-123`, `webhook_secret decifrado: webhook-teste-456`, `ambiente: producao` (mudou só o ambiente).

5. **Limpar os dados de teste** (apagar a linha, já que era só teste manual):

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import psycopg2, os
conn = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require')
cur = conn.cursor()
cur.execute('DELETE FROM config_asaas WHERE company_id=1')
conn.commit()
conn.close()
print('limpo')
"
```

6. Parar o servidor local e apagar `_run_local.py`.

- [ ] **Step 7: Commit**

```bash
git add routes/configuracoes_routes.py templates/configuracoes.html app.py templates/base.html
git commit -m "Adiciona tela /configuracoes pra chave Asaas por empresa"
```

---

## Task 4: Refatorar `routes/clientes_routes.py` pra usar `obter_config_asaas`

**Files:**
- Modify: `routes/clientes_routes.py:93,100,123` (dentro de `listar_clientes()`, bloco de integração com Asaas no cadastro de cliente)

**Interfaces:**
- Consumes: `obter_config_asaas(cur, company_id)` de `asaas_config.py` (Task 2) — retorna dict `{api_key, base_url, webhook_secret}`.

- [ ] **Step 1: Adicionar o import**

No topo de `routes/clientes_routes.py`, junto dos outros imports locais:

```python
from asaas_config import obter_config_asaas
```

- [ ] **Step 2: Substituir o uso de `Config.ASAAS_API_KEY`/`Config.ASAAS_BASE_URL`**

Local atual (dentro do `try` do POST de `listar_clientes`, por volta da linha 93):

```python
            # Busca cliente no Asaas pelo CPF (document) ou email
            headers = {"access_token": Config.ASAAS_API_KEY}
            params = {}
            if cpf:
                params["cpfCnpj"] = cpf
            else:
                params["email"] = email

            resp = requests.get(f"{Config.ASAAS_BASE_URL}/customers", headers=headers, params=params, timeout=30)
```

Troque por:

```python
            # Busca cliente no Asaas pelo CPF (document) ou email
            asaas = obter_config_asaas(cur, current_user.company_id)
            headers = {"access_token": asaas["api_key"]}
            params = {}
            if cpf:
                params["cpfCnpj"] = cpf
            else:
                params["email"] = email

            resp = requests.get(f"{asaas['base_url']}/customers", headers=headers, params=params, timeout=30)
```

E logo abaixo (por volta da linha 123, dentro do `if not asaas_id:`):

```python
                resp_create = requests.post(f"{Config.ASAAS_BASE_URL}/customers", headers=headers, json=cliente_payload, timeout=30)
```

Troque por:

```python
                resp_create = requests.post(f"{asaas['base_url']}/customers", headers=headers, json=cliente_payload, timeout=30)
```

(`headers` já foi reatribuído acima com a chave certa, não precisa mudar de novo aqui.)

- [ ] **Step 3: Verificar que o arquivo ainda importa sem erro**

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import app as flaskapp
print('IMPORT OK')
"
```

Expected: `IMPORT OK`, sem `ImportError`/`NameError`.

- [ ] **Step 4: Verificar o fallback end-to-end (sem chave própria configurada = mesmo comportamento de antes)**

Suba o servidor local de novo (mesmo processo do Task 3 Step 6), logue, tente cadastrar um cliente novo em `/clientes/`. Como nenhuma empresa tem `config_asaas` própria neste ponto (Task 3 limpou os dados de teste), o comportamento esperado é idêntico ao observado no início desta sessão: erro "Erro ao consultar Asaas: 401" (ou sucesso, se a `ASAAS_API_KEY` global já estiver configurada no `.env` nesse momento) — o importante é confirmar que **não mudou o comportamento**, só a origem da credencial. Pare o servidor local depois.

- [ ] **Step 5: Commit**

```bash
git add routes/clientes_routes.py
git commit -m "clientes_routes.py: usa obter_config_asaas em vez da chave Asaas global"
```

---

## Task 5: Refatorar `routes/locacoes_routes.py` pra usar `obter_config_asaas`

**Files:**
- Modify: `routes/locacoes_routes.py:262-264` (dentro de `criar_locacao_interna`, criação de assinatura)
- Modify: `routes/locacoes_routes.py:374-386` (dentro de `editar_locacao`, atualização de assinatura)
- Modify: `routes/locacoes_routes.py:481-485` (dentro de `executar_cancelamento_locacao`, cancelamento)
- Modify: `routes/locacoes_routes.py:562-563` (dentro de `sincronizar_boletos_manual`, consulta de boletos)

**Interfaces:**
- Consumes: `obter_config_asaas(cur, company_id)` de `asaas_config.py` (Task 2).

- [ ] **Step 1: Adicionar o import**

No topo de `routes/locacoes_routes.py`, junto dos outros imports locais (`from assinaturas_core import ...`):

```python
from asaas_config import obter_config_asaas
```

- [ ] **Step 2: `criar_locacao_interna` — criação de assinatura**

Local atual (por volta da linha 261-267):

```python
    try:
        resp = requests.post(
            f"{Config.ASAAS_BASE_URL}/subscriptions",
            headers={"access_token": Config.ASAAS_API_KEY},
            json=subscription_data,
            timeout=30,
        )
    except requests.RequestException as rexc:
        raise AsaasError(f"Falha de conexão com Asaas: {str(rexc)}") from rexc
```

Troque por:

```python
    asaas = obter_config_asaas(cur, current_user.company_id)
    try:
        resp = requests.post(
            f"{asaas['base_url']}/subscriptions",
            headers={"access_token": asaas["api_key"]},
            json=subscription_data,
            timeout=30,
        )
    except requests.RequestException as rexc:
        raise AsaasError(f"Falha de conexão com Asaas: {str(rexc)}") from rexc
```

(`cur` já é parâmetro da função `criar_locacao_interna`, não precisa adicionar.)

- [ ] **Step 3: `editar_locacao` — atualização de assinatura**

Local atual (por volta da linha 374-386):

```python
                resp = requests.post(
                    f"{Config.ASAAS_BASE_URL}/subscriptions/{asaas_subscription_id}",
                    headers={"access_token": Config.ASAAS_API_KEY},
                    json=patch_data,
                    timeout=30
                )
                if resp.status_code not in (200, 201):
                    resp = requests.put(
                        f"{Config.ASAAS_BASE_URL}/subscriptions/{asaas_subscription_id}",
                        headers={"access_token": Config.ASAAS_API_KEY},
                        json=patch_data,
                        timeout=30
                    )
```

Troque por:

```python
                asaas = obter_config_asaas(cur, current_user.company_id)
                resp = requests.post(
                    f"{asaas['base_url']}/subscriptions/{asaas_subscription_id}",
                    headers={"access_token": asaas["api_key"]},
                    json=patch_data,
                    timeout=30
                )
                if resp.status_code not in (200, 201):
                    resp = requests.put(
                        f"{asaas['base_url']}/subscriptions/{asaas_subscription_id}",
                        headers={"access_token": asaas["api_key"]},
                        json=patch_data,
                        timeout=30
                    )
```

- [ ] **Step 4: `executar_cancelamento_locacao` — cancelamento**

Local atual (por volta da linha 478-485):

```python
def executar_cancelamento_locacao(cur, locacao_id, equipamento_id, asaas_subscription_id):
    """Cancela a assinatura no Asaas (se existir) e libera o equipamento. Não faz commit — quem chama controla a transação."""
    if asaas_subscription_id:
        resp = requests.post(
            f"{Config.ASAAS_BASE_URL}/subscriptions/{asaas_subscription_id}/cancel",
            headers={"access_token": Config.ASAAS_API_KEY},
            timeout=30
        )
```

Troque por:

```python
def executar_cancelamento_locacao(cur, locacao_id, equipamento_id, asaas_subscription_id):
    """Cancela a assinatura no Asaas (se existir) e libera o equipamento. Não faz commit — quem chama controla a transação."""
    if asaas_subscription_id:
        asaas = obter_config_asaas(cur, current_user.company_id)
        resp = requests.post(
            f"{asaas['base_url']}/subscriptions/{asaas_subscription_id}/cancel",
            headers={"access_token": asaas["api_key"]},
            timeout=30
        )
```

- [ ] **Step 5: `sincronizar_boletos_manual` — consulta de boletos**

Local atual (por volta da linha 561-563):

```python
        sub_id = row[0]
        url = f"{Config.ASAAS_BASE_URL}/payments?subscription={sub_id}&limit=100"
        resp = requests.get(url, headers={"access_token": Config.ASAAS_API_KEY}, timeout=30)
```

Troque por:

```python
        sub_id = row[0]
        asaas = obter_config_asaas(cur, current_user.company_id)
        url = f"{asaas['base_url']}/payments?subscription={sub_id}&limit=100"
        resp = requests.get(url, headers={"access_token": asaas["api_key"]}, timeout=30)
```

- [ ] **Step 6: Verificar que o arquivo ainda importa sem erro**

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import app as flaskapp
print('IMPORT OK')
"
```

Expected: `IMPORT OK`.

- [ ] **Step 7: Verificar que as 4 substituições foram feitas (nenhuma sobrou usando a Config direto)**

```bash
python -c "
import re
codigo = open('routes/locacoes_routes.py', encoding='utf-8').read()
sobrou = re.findall(r'Config\.ASAAS_(API_KEY|BASE_URL)', codigo)
assert not sobrou, f'ainda hà usos diretos: {sobrou}'
print('OK: nenhum uso direto de Config.ASAAS_API_KEY/BASE_URL restante')
"
```

Expected: `OK: nenhum uso direto de Config.ASAAS_API_KEY/BASE_URL restante`.

- [ ] **Step 8: Commit**

```bash
git add routes/locacoes_routes.py
git commit -m "locacoes_routes.py: usa obter_config_asaas em vez da chave Asaas global"
```

---

## Task 6: Refatorar `routes/webhook_routes.py` pra aceitar secret de qualquer empresa

**Files:**
- Modify: `routes/webhook_routes.py` (`_authorized`, `asaas_webhook`)

**Interfaces:**
- Consumes: `todos_webhook_secrets_validos(cur)` de `asaas_config.py` (Task 2).

- [ ] **Step 1: Reescrever `routes/webhook_routes.py`**

Arquivo completo (a mudança principal: abrir a conexão com o banco **antes** de checar autorização, porque `_authorized` agora precisa de `cur` pra consultar os secrets de todas as empresas; e `_authorized` passa a comparar contra um conjunto de secrets válidos, não um único):

```python
import json
from flask import Blueprint, request, abort, Request
from database import get_db_connection
from asaas_config import todos_webhook_secrets_validos

webhook_bp = Blueprint("webhook", __name__, url_prefix="/webhook")

def _authorized(req: Request, cur) -> bool:
    # Validação por token de cabeçalho, contra o conjunto de secrets válidos
    # (todas as empresas configuradas + o global). Sem nenhum secret
    # configurado em lugar nenhum, aceita (útil em dev).
    secrets_validos = todos_webhook_secrets_validos(cur)
    if not secrets_validos:
        return True
    hdrs = {k.lower(): v for k, v in req.headers.items()}
    token = hdrs.get("x-webhook-token") or hdrs.get("asaas-webhook-token") or hdrs.get("authorization")
    return token in secrets_validos

@webhook_bp.route("/asaas", methods=["POST"])
def asaas_webhook():
    conn = get_db_connection()
    cur = conn.cursor()

    if not _authorized(request, cur):
        cur.close()
        conn.close()
        abort(401)

    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        cur.close()
        conn.close()
        abort(400)

    event = data.get("event")
    payment = data.get("payment") or {}

    try:
        if event in ("PAYMENT_CREATED", "PAYMENT_UPDATED"):
            _upsert_boleto(cur, payment)

        elif event in ("PAYMENT_CONFIRMED", "PAYMENT_RECEIVED", "PAYMENT_RECEIVED_IN_CASH"):
            _upsert_boleto(cur, payment)
            _atualizar_agregado_locacao(cur, payment)

        elif event in ("PAYMENT_OVERDUE", "PAYMENT_DELETED", "PAYMENT_CANCELED"):
            _upsert_boleto(cur, payment)
            _atualizar_agregado_locacao(cur, payment)

        conn.commit()
    except Exception as e:
        conn.rollback()
        # Retornar 200 para Asaas não reenfileirar eternamente, mas logue em produção:
        return {"ok": False, "error": str(e)}, 200
    finally:
        cur.close()
        conn.close()

    return {"ok": True}, 200

def _upsert_boleto(cur, p):
    asaas_payment_id = p.get("id")
    status = p.get("status")
    valor = p.get("value")
    net_value = p.get("netValue")
    boleto_url = p.get("bankSlipUrl")
    descricao = p.get("description")
    due_date = p.get("dueDate")
    payment_date = p.get("paymentDate")
    subscription_id = p.get("subscription")

    # Relacionar com locação pela assinatura
    cur.execute("SELECT id FROM locacoes WHERE asaas_subscription_id=%s", (subscription_id,))
    row = cur.fetchone()
    locacao_id = row[0] if row else None

    # Upsert
    cur.execute("SELECT id FROM boletos WHERE asaas_payment_id=%s", (asaas_payment_id,))
    exists = cur.fetchone()
    if exists:
        cur.execute("""
            UPDATE boletos
               SET status=%s, valor=%s, valor_pago=%s, boleto_url=%s, descricao=%s,
                   data_vencimento=%s, data_pagamento=%s
             WHERE asaas_payment_id=%s
        """, (status, valor, net_value, boleto_url, descricao, due_date, payment_date, asaas_payment_id))
    else:
        cur.execute("""
            INSERT INTO boletos (locacao_id, asaas_payment_id, status, valor, valor_pago,
                                 boleto_url, descricao, data_vencimento, data_pagamento)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (locacao_id, asaas_payment_id, status, valor, net_value, boleto_url, descricao, due_date, payment_date))

def _atualizar_agregado_locacao(cur, p):
    # Recalcula status agregado da locação com base nos boletos
    subscription_id = p.get("subscription")
    if not subscription_id:
        return
    cur.execute("SELECT id FROM locacoes WHERE asaas_subscription_id=%s", (subscription_id,))
    row = cur.fetchone()
    if not row:
        return
    locacao_id = row[0]

    # Somatório valor pago e status mais recente
    cur.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN status IN ('RECEIVED','CONFIRMED','RECEIVED_IN_CASH') THEN COALESCE(valor_pago,0) ELSE 0 END),0) AS total_pago,
            MAX(data_pagamento) AS ultima_data_pagto
        FROM boletos
        WHERE locacao_id=%s
    """, (locacao_id,))
    agg = cur.fetchone()
    total_pago = agg[0] if agg else 0

    # Atualiza campos agregados (se você tiver colunas pagamento_status/valor_pago na locações)
    try:
        cur.execute("""
            UPDATE locacoes
               SET valor_pago=%s
             WHERE id=%s
        """, (total_pago, locacao_id))
    except Exception:
        # Se a coluna não existir, ignore silenciosamente
        pass
```

- [ ] **Step 2: Verificar que o arquivo ainda importa sem erro**

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import app as flaskapp
print('IMPORT OK')
"
```

Expected: `IMPORT OK`.

- [ ] **Step 3: Verificar a autorização com um script standalone (sem subir o servidor)**

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import psycopg2, os
from psycopg2.extras import RealDictCursor
from routes.webhook_routes import _authorized

conn = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require', cursor_factory=RealDictCursor)
cur = conn.cursor()

class FakeRequest:
    def __init__(self, headers):
        self.headers = headers

# Sem nenhum secret configurado em lugar nenhum -> aceita (dev)
req_sem_token = FakeRequest({})
assert _authorized(req_sem_token, cur) == True, 'sem secret configurado deveria aceitar'
print('OK: sem secret configurado, aceita')

conn.close()
"
```

Expected: `OK: sem secret configurado, aceita` (proporção esperada nesse ponto, já que nenhuma empresa tem `config_asaas` com `webhook_secret_cifrado` preenchido e `ASAAS_WEBHOOK_SECRET` global provavelmente também não está setado localmente).

- [ ] **Step 4: Verificar rejeição de token inválido quando existe secret configurado (insere linha de teste, confirma, apaga)**

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import psycopg2, os
from psycopg2.extras import RealDictCursor
from asaas_config import cifrar
from routes.webhook_routes import _authorized

conn = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require', cursor_factory=RealDictCursor)
cur = conn.cursor()

cur.execute('''
    INSERT INTO config_asaas (company_id, webhook_secret_cifrado, ambiente, ativo)
    VALUES (1, %s, 'sandbox', TRUE)
''', (cifrar('meu-webhook-secret'),))
conn.commit()

class FakeRequest:
    def __init__(self, headers):
        self.headers = headers

req_valido = FakeRequest({'X-Webhook-Token': 'meu-webhook-secret'})
req_invalido = FakeRequest({'X-Webhook-Token': 'token-errado'})

assert _authorized(req_valido, cur) == True, 'token valido deveria ser aceito'
assert _authorized(req_invalido, cur) == False, 'token invalido deveria ser rejeitado'
print('OK: token valido aceito, invalido rejeitado')

cur.execute('DELETE FROM config_asaas WHERE company_id=1')
conn.commit()
conn.close()
"
```

Expected: `OK: token valido aceito, invalido rejeitado`. A linha de teste é apagada no final.

- [ ] **Step 5: Commit**

```bash
git add routes/webhook_routes.py
git commit -m "webhook_routes.py: aceita webhook secret de qualquer empresa configurada, não só o global"
```

---

## Task 7: Push final e limpeza

**Files:** nenhum arquivo novo — só verificação final e push.

- [ ] **Step 1: Rodar uma verificação completa de import + rotas**

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import app as flaskapp
print('IMPORT OK')
rotas_esperadas = ['/configuracoes/']
existentes = [str(r) for r in flaskapp.app.url_map.iter_rules()]
for r in rotas_esperadas:
    assert r in existentes, f'rota faltando: {r}'
print('OK: todas as rotas esperadas presentes')
"
```

Expected: `IMPORT OK` e `OK: todas as rotas esperadas presentes`.

- [ ] **Step 2: Confirmar que não sobrou nenhum arquivo de teste/scratch**

```bash
git status --short
```

Expected: só os arquivos das Tasks 1-6 (já commitados) — nenhum `_run_local.py` ou arquivo de teste solto.

- [ ] **Step 3: Push**

```bash
git push origin main
```

- [ ] **Step 4: Avisar o usuário sobre a `APP_ENCRYPTION_KEY` no Render**

Depois do push (que vai disparar o auto-deploy no Render), a tela `/configuracoes` só funciona em produção depois que `APP_ENCRYPTION_KEY` (gerada no Task 1, Step 3) for adicionada nas variáveis de ambiente do Render — igual foi feito com `COHERE_API_KEY`. Sem isso, `cifrar`/`decifrar` levantam `RuntimeError` e a tela de Configurações fica inacessível (erro 500). Avise o usuário explicitamente sobre esse passo manual.
