# Asaas por empresa (multi-tenant)

## Contexto e objetivo

Hoje a integração com a Asaas (criação de clientes, assinaturas/cobranças recorrentes,
webhooks de pagamento) usa uma única chave global (`Config.ASAAS_API_KEY`), lida de
uma variável de ambiente no Render. Isso funciona enquanto só existe uma empresa
(locadora) usando o sistema, mas o AluguelFacil é uma plataforma SaaS multi-empresa
(tabela `companies`, `company_id` em quase todas as tabelas) — cada empresa que
"alugar" o SaaS tem sua própria conta Asaas e precisa receber pagamentos na própria
conta bancária, não na do dono da plataforma.

Objetivo: cada empresa configura a própria chave Asaas (e webhook secret) numa tela
de Configurações dentro do sistema, sem precisar de acesso ao Render. A chave global
continua existindo como fallback para empresas que ainda não configuraram a própria.

## Arquitetura

### Nova tabela `config_asaas`

Mesmo padrão de `config_multas` (migration 006): uma linha por empresa, `company_id`
único, upsert via `ON CONFLICT`.

```sql
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

`api_key_cifrada` e `webhook_secret_cifrado` guardam o valor cifrado (Fernet), nunca
texto puro. `ambiente` decide a `base_url` usada nas chamadas (sandbox ou produção).

### Criptografia — módulo `asaas_config.py`

Novo módulo, novo ponto central de acesso às credenciais Asaas (substitui o acesso
direto a `Config.ASAAS_API_KEY` nos 8 arquivos que usam isso hoje).

```python
from cryptography.fernet import Fernet
from config import Config

BASE_URL_POR_AMBIENTE = {
    "sandbox": "https://sandbox.asaas.com/api/v3",
    "producao": "https://api.asaas.com/v3",
}

def _fernet():
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
    """Retorna dict {api_key, base_url, webhook_secret} pra empresa, com fallback
    pra config global (Config.ASAAS_API_KEY/ASAAS_BASE_URL/ASAAS_WEBHOOK_SECRET)
    se a empresa não tiver configurado a própria chave (ou estiver inativa)."""
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
    """Pra validação do webhook: lista de todos os secrets válidos (todas as
    empresas configuradas + o global), já decifrados."""
    secrets = set()
    if Config.ASAAS_WEBHOOK_SECRET:
        secrets.add(Config.ASAAS_WEBHOOK_SECRET.strip())
    cur.execute("SELECT webhook_secret_cifrado FROM config_asaas WHERE ativo=TRUE AND webhook_secret_cifrado IS NOT NULL")
    for row in cur.fetchall():
        valor = decifrar(row["webhook_secret_cifrado"])
        if valor:
            secrets.add(valor.strip())
    return secrets
```

`Config.APP_ENCRYPTION_KEY` é uma variável de ambiente nova, só no Render (nunca no
banco), gerada uma vez com `Fernet.generate_key()`. Sem ela, `cifrar`/`decifrar`
levantam erro — a tela de Configurações fica inacessível até a chave existir (é
aceitável, é infraestrutura obrigatória do deploy, mesmo nível de `DATABASE_URL`).

### Tela de Configurações

Novo blueprint `routes/configuracoes_routes.py`, prefixo `/configuracoes`, rota
`/` (GET+POST), acesso via `@requer_role("super_admin", "admin_locadora")` (mesmo
guard de `config_multas`).

- GET: busca `config_asaas` da empresa do usuário logado (`current_user.company_id`).
  Campo de API key **nunca mostra o valor salvo** — se já tem chave configurada,
  mostra um campo vazio com placeholder "•••• chave configurada (deixe em branco
  pra manter)"; se o usuário digitar algo, substitui; se deixar vazio, mantém a
  chave atual (não apaga sem querer).
- POST: valida `ambiente` (sandbox/producao), cifra API key e webhook secret (só
  se preenchidos — campo vazio = mantém o que já estava), upsert em `config_asaas`.
- Template `templates/configuracoes.html`, novo, mesmo estilo visual das outras
  telas do sistema (`config_multas.html` como referência).
- `ativo` não tem toggle na UI nesta primeira versão — todo upsert grava
  `ativo=TRUE`. A coluna existe pra permitir desativar via banco (ou uma tela
  futura) sem apagar a configuração, mesmo padrão de `config_multas.ativo`.
- Link "Configurações" no menu (`base.html`), sempre visível — mesmo padrão dos
  outros itens do menu (ex: "Usuários"), que não escondem por role no template;
  quem não tem o role é barrado pelo `@requer_role` na própria rota.

### Refatoração dos arquivos que usam `Config.ASAAS_API_KEY`/`ASAAS_BASE_URL` hoje

Levantamento preciso (grep por `Config.ASAAS_`, não só menções a "Asaas"): só três
arquivos chamam a API da Asaas de fato com a config global —
`routes/clientes_routes.py` (2 chamadas), `routes/locacoes_routes.py` (4 chamadas),
`routes/webhook_routes.py` (`_authorized()`). `config.py` mantém as vars globais
como fallback, não muda.

`checklists_routes.py`, `catalogo_routes.py` e `orcamentos_routes.py` só mencionam
"Asaas" em comentário ou leem a coluna `asaas_id`/`asaas_subscription_id` do banco
— não chamam a API, não precisam mudar.

`sync_clientes_asaas.py` é um script standalone (roda manual via linha de comando,
nunca é importado por nenhuma rota, lê `os.environ` direto em vez de `Config`) —
fica fora do escopo desta mudança. Se um dia precisar rodar por empresa, isso é
uma tarefa separada (ex: aceitar `--company-id` como argumento).

Cada chamada que hoje faz:

```python
headers = {"access_token": Config.ASAAS_API_KEY}
resp = requests.get(f"{Config.ASAAS_BASE_URL}/customers", headers=headers, ...)
```

passa a ser:

```python
asaas = obter_config_asaas(cur, current_user.company_id)
headers = {"access_token": asaas["api_key"]}
resp = requests.get(f"{asaas['base_url']}/customers", headers=headers, ...)
```

`webhook_routes.py` é o caso especial: não tem `current_user` (é uma rota pública,
chamada pela Asaas). `_authorized()` passa a comparar o token recebido contra
`todos_webhook_secrets_validos(cur)` em vez de um único secret global. A URL do
webhook continua sendo uma só (`/webhook/asaas`) pra todas as empresas — o payload
já identifica a locação certa via `asaas_subscription_id` (que é único por
assinatura na Asaas, independente de qual conta criou), então não precisa de
`company_id` na URL.

## Fluxo de dados

1. Empresa acessa `/configuracoes`, cola a API key da própria conta Asaas, escolhe
   ambiente, salva → cifrada e gravada em `config_asaas`.
2. Qualquer rota que precise falar com a Asaas (criar cliente, criar assinatura,
   sincronizar boletos) chama `obter_config_asaas(cur, current_user.company_id)`
   primeiro, e usa o `api_key`/`base_url` retornados.
3. Webhook da Asaas chega em `/webhook/asaas` (uma URL só, pra todas as empresas) →
   valida contra a lista de secrets válidos → processa o payload normalmente (já
   funciona sem mudança, porque a associação com a locação é por
   `asaas_subscription_id`, não por empresa).

## Tratamento de erros

- `APP_ENCRYPTION_KEY` ausente: a tela de Configurações mostra erro claro
  ("Infraestrutura de criptografia não configurada, contate o suporte") em vez de
  estourar exceção crua — mesmo padrão do `AssistenteError` no assistente de IA.
- Empresa sem chave própria e sem fallback global: comportamento atual é mantido
  (erro 401 da Asaas, capturado e exibido via `flash`, como já acontece hoje).
- Campo de API key deixado em branco no POST: mantém o valor cifrado já salvo
  (não apaga a configuração existente).

## Testes

- Cadastro de cliente com chave própria configurada (sandbox) — confirma que usa a
  chave da empresa, não a global.
- Empresa sem chave própria configurada — confirma fallback pra chave global.
- Webhook aceita token de uma empresa configurada e rejeita token inválido.
- Campo de API key em branco no POST não apaga a chave já salva.
