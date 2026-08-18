# Atualização Cadastral Obrigatória (Comprovante de Residência) — Design

## Contexto

Hoje o sistema não verifica há quanto tempo um cliente está sem alugar, nem
se o comprovante de residência dele está desatualizado. Um cliente pode
alugar novamente depois de anos sem que ninguém peça documentação nova.

**Pedido original do usuário:** se um cliente não aluga nada há mais de 3
meses (sem locação ativa/nova nos últimos 90 dias) e volta a alugar, o
sistema deve pedir atualização cadastral obrigatória — novo comprovante de
residência — antes de confirmar a nova locação. Bloquear a criação da
locação até essa atualização ser feita.

**Decisões já validadas com o usuário** (perguntas anteriores):
- Só locações **não canceladas** contam para determinar a última locação do cliente.
- O escopo da exigência é **só o comprovante de residência** (não os outros 3 slots fixos: doc_frente, doc_verso, foto_cliente).
- A atualização **reaproveita o campo já existente** (`comprovante_residencia_arquivo`, via `editar_cliente`) — não é criado um upload dedicado a este fluxo.
- O aviso aparece **na tela de Nova Locação, ao escolher o cliente**.
- A regra **também se aplica a clientes de primeira locação** (não há isenção para quem nunca alugou).
- O comprovante conta como "atualizado" se foi reenviado **a qualquer momento depois** da última locação relevante — não precisa ser reenviado especificamente "no ato" da nova locação.

## Regra de negócio

Nova coluna `clientes.comprovante_residencia_atualizado_em TIMESTAMP`,
gravada automaticamente (não editável pelo usuário) toda vez que
`comprovante_residencia_arquivo` é substituído — tanto no cadastro
(`listar_clientes` POST) quanto na edição (`editar_cliente` POST).

Ao tentar criar uma nova locação para um cliente, calcula-se:

1. **Busca a locação não cancelada mais recente do cliente** (`MAX(data_inicio)` entre `locacoes WHERE cliente_id=X AND cancelado=FALSE`).

2. **Se não existe locação anterior** (cliente de primeira locação):
   - Bloqueia se `comprovante_residencia_atualizado_em` for `NULL` ou tiver mais de 90 dias.

3. **Se existe locação anterior:**
   - `dias_parado = hoje - data_inicio da última locação`
   - Se `dias_parado <= 90`: **não bloqueia** (cliente esteve ativo recentemente, comprovante não é reavaliado).
   - Se `dias_parado > 90`: bloqueia, **a menos que** `comprovante_residencia_atualizado_em` seja posterior à `data_inicio` dessa última locação (ou seja: o cliente atualizou o comprovante em algum momento depois da última vez que alugou — mesmo que não tenha sido "agora").

Este cálculo fica centralizado em uma função só
(`cliente_precisa_atualizar_comprovante(cur, cliente_id) -> bool`), usada
tanto pelo aviso no front-end quanto pelo bloqueio no back-end — uma única
fonte de verdade para a regra.

## Onde o bloqueio é aplicado

`criar_locacao_interna()` (`routes/locacoes_routes.py`) é o ponto de
criação de locação reaproveitado tanto pelo formulário manual
(`listar_locacoes` POST) quanto pela conversão de orçamento em locação
(`orcamentos_routes.py`). Colocar o bloqueio **dentro** dessa função —
não em cada chamador — garante que nenhum caminho de criação de locação,
presente ou futuro, escape da regra.

`criar_locacao_interna()` levanta uma nova exceção dedicada,
`ComprovanteDesatualizadoError` (mesmo padrão já usado por `AsaasError`,
definida no mesmo módulo), com mensagem pronta para exibir ao usuário.

- Em `locacoes_routes.py`, o `try/except AsaasError` já existente ao redor
  da chamada de `criar_locacao_interna` ganha mais um `except
  ComprovanteDesatualizadoError` irmão, com o mesmo tratamento (flash +
  redirect).
- Em `orcamentos_routes.py`, `ComprovanteDesatualizadoError` entra na
  tupla `except (ValueError, AsaasError)` já existente ali (com import
  atualizado).

## Aviso no front-end (Nova Locação)

Novo endpoint JSON: `GET /clientes/<id>/status-cadastral`, retornando
`{"precisa_atualizar_comprovante": bool}`.

Em `templates/locacoes.html`, o `<select id="cliente_id">` ganha um
listener de `change` que chama esse endpoint e mostra/esconde um alerta
Bootstrap (`alert-warning`) logo abaixo do select, com um link para
`editar_cliente` (abrindo em nova aba) para o usuário resolver antes de
tentar submeter. O aviso é só uma ajuda de UX — o bloqueio real está no
back-end (seção anterior), então mesmo se o JS falhar ou for burlado, a
regra continua valendo.

## Migration e backfill

`migrations/018_comprovante_residencia_validade.sql`:

```sql
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS comprovante_residencia_atualizado_em TIMESTAMP;

-- Backfill: clientes que já têm um comprovante de residência arquivado
-- recebem uma data aproximada (não sabemos a data exata do upload
-- original, já que a coluna não existia). Usamos updated_at como melhor
-- proxy disponível, caindo para created_at se updated_at for nulo.
-- Clientes sem comprovante arquivado ficam com a coluna NULL — e isso é
-- correto: eles não têm comprovante nenhum, então já deveriam ser
-- bloqueados na próxima locação até enviarem um.
UPDATE clientes
SET comprovante_residencia_atualizado_em = COALESCE(updated_at, created_at)
WHERE comprovante_residencia_arquivo IS NOT NULL
  AND comprovante_residencia_atualizado_em IS NULL;
```

Aplicada manualmente contra o banco de produção via script `python -c`
(mesmo padrão das migrations anteriores), não pelo deploy automático.

**Nota sobre o rollout:** como o backfill usa `updated_at`/`created_at`
como aproximação, alguns clientes que na verdade têm um comprovante
recente podem aparecer como "desatualizados" logo após o deploy (se o
registro do cliente não foi tocado desde o cadastro original, por
exemplo). Isso é uma aproximação aceita — o efeito prático é, na pior das
hipóteses, pedir uma atualização a mais do que o estritamente necessário
no primeiro mês; nunca o contrário (nunca deixa passar um comprovante
realmente antigo).

## Fora de escopo

- Backup automático — **não mexer**, fica pendente até decisão sobre custo (constraint do usuário, vale para todo o trabalho atual).
- Os outros 3 documentos fixos do cliente (doc_frente, doc_verso, foto_cliente) — regra não se aplica a eles.
- Notificação proativa (e-mail/SMS) avisando o cliente antes de ele tentar alugar — fora de escopo, o aviso é reativo (só aparece quando alguém tenta criar a locação).
