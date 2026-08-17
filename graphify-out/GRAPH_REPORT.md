# Graph Report - AluguelFacil  (2026-08-14)

## Corpus Check
- Corpus is ~10,391 words - fits in a single context window. You may not need a graph.

## Summary
- 135 nodes · 271 edges · 16 communities (13 shown, 3 thin omitted)
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 37 edges (avg confidence: 0.76)
- Token cost: 90,230 input · 10,936 output

## Community Hubs (Navigation)
- Core App & Routing
- Motorcycle Routes
- Motorcycle Templates
- Rental Templates
- Database Schema
- Authentication
- Client Templates
- Payment Webhook
- Flask Deps & Layout
- Rental Actions
- Asaas Client Sync
- DB Init Command
- Project README
- Gunicorn Dependency
- Dotenv Dependency

## God Nodes (most connected - your core abstractions)
1. `get_db_connection()` - 29 edges
2. `base.html (Layout Template)` - 21 edges
3. `Config` - 13 edges
4. `locacoes.html (Active Rentals Page)` - 10 edges
5. `locacoes_canceladas.html (Cancelled Rentals Page)` - 9 edges
6. `dashboard.html (Dashboard Page)` - 8 edges
7. `editar_moto.html (Edit Motorcycle Page)` - 7 edges
8. `motos.html (Motorcycles List/Create Page)` - 7 edges
9. `Cliente (Client Entity)` - 7 edges
10. `Moto (Motorcycle Entity)` - 7 edges

## Surprising Connections (you probably didn't know these)
- `_authorized()` --uses--> `Config`  [INFERRED]
  routes/webhook_routes.py → config.py
- `Flask 2.3.3` --conceptually_related_to--> `base.html (Layout Template)`  [INFERRED]
  requirements.txt → templates/base.html
- `psycopg2-binary >=2.9.9` --conceptually_related_to--> `Cliente (Client Entity)`  [INFERRED]
  requirements.txt → templates/clientes.html
- `load_user()` --uses--> `SimpleUser`  [INFERRED]
  app.py → routes/auth_routes.py
- `init_db_command()` --calls--> `get_db_connection()`  [EXTRACTED]
  app.py → database.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **MotoRental Application Pages** — templates_base_template, templates_cliente_habilitacao_template, templates_clientes_template, templates_dashboard_template, templates_editar_cliente_template, templates_editar_locacao_template, templates_editar_moto_template, templates_locacoes_template, templates_locacoes_canceladas_template, templates_login_template, templates_moto_documento_template, templates_moto_imagens_template, templates_motos_template, templates_servicos_locacao_template [INFERRED 0.85]
- **Rental Lifecycle Flow (Locação -> Boleto -> Serviço)** — templates_locacoes_locacao, templates_editar_locacao_boleto, templates_servicos_locacao_servico, templates_locacoes_template, templates_editar_locacao_template, templates_servicos_locacao_template [INFERRED 0.75]
- **Flask Web Application Stack** — requirements_flask, requirements_flask_login, requirements_gunicorn, requirements_psycopg2_binary [INFERRED 0.85]

## Communities (16 total, 3 thin omitted)

### Community 0 - "Core App & Routing"
Cohesion: 0.20
Nodes (21): Config, get_db_connection(), editar_cliente(), listar_clientes(), login_required, route, home(), login_required (+13 more)

### Community 1 - "Motorcycle Routes"
Cohesion: 0.36
Nodes (13): _allowed(), editar_moto(), excluir_documento_moto(), excluir_imagem_moto(), excluir_moto(), listar_motos(), moto_documento(), moto_imagens() (+5 more)

### Community 2 - "Motorcycle Templates"
Cohesion: 0.22
Nodes (14): Route: motos.editar_moto, Route: motos.uploaded_file, editar_moto.html (Edit Motorcycle Page), Route: motos.excluir_documento_moto, Route: motos.moto_documento, Route: motos.uploaded_documento, moto_documento.html (Motorcycle Document Page), Route: motos.excluir_imagem_moto (+6 more)

### Community 3 - "Rental Templates"
Cohesion: 0.21
Nodes (12): requests 2.31.0, Boleto (Payment Slip Entity), Route: locacoes.sincronizar_boletos_manual, editar_locacao.html (Edit Rental Page), Route: locacoes.boletos_locacao, Route: locacoes.uploaded_contract, locacoes_canceladas.html (Cancelled Rentals Page), Locação (Rental Entity) (+4 more)

### Community 4 - "Database Schema"
Cohesion: 0.31
Nodes (10): boletos, clientes, locacoes, moto_imagens, motos, servicos_locacao, set_updated_at(), trg_boletos_updated (+2 more)

### Community 5 - "Authentication"
Cohesion: 0.24
Nodes (8): load_user(), login(), logout(), login_required, route, SimpleUser, user_loader, UserMixin

### Community 6 - "Client Templates"
Cohesion: 0.31
Nodes (10): psycopg2-binary >=2.9.9, Route: clientes.excluir_habilitacao, Route: clientes.uploaded_habilitacao, cliente_habilitacao.html (Driver's License Upload Page), Cliente (Client Entity), Route: clientes.listar_clientes, clientes.html (Clients List/Create Page), dashboard.html (Dashboard Page) (+2 more)

### Community 7 - "Payment Webhook"
Cohesion: 0.43
Nodes (6): Request, asaas_webhook(), _atualizar_agregado_locacao(), _authorized(), route, _upsert_boleto()

### Community 8 - "Flask Deps & Layout"
Cohesion: 0.38
Nodes (7): Flask 2.3.3, Flask-Login 0.6.3, Route: auth.logout, base.html (Layout Template), Route: dashboard.home, Route: auth.login, login.html (Login Page)

### Community 9 - "Rental Actions"
Cohesion: 0.29
Nodes (7): Route: locacoes.editar_locacao, Route: locacoes.canceladas, Route: servicos.servicos_locacao, Route: locacoes.cancelar_locacao, Route: locacoes.contrato_pdf, Route: servicos.listar_servicos, locacoes.html (Active Rentals Page)

### Community 10 - "Asaas Client Sync"
Cohesion: 0.67
Nodes (5): buscar_cliente_asaas_por_cpf(), buscar_cliente_asaas_por_email(), criar_cliente_asaas(), normalize_response_list(), sync_clientes()

### Community 11 - "DB Init Command"
Cohesion: 0.50
Nodes (4): init_db_command(), Inicializa o banco de dados aplicando o schema.sql, command, with_appcontext

## Ambiguous Edges - Review These
- `Route: servicos.listar_servicos` → `Route: servicos.servicos_locacao`  [AMBIGUOUS]
  templates/locacoes.html · relation: conceptually_related_to

## Knowledge Gaps
- **22 isolated node(s):** `usuarios`, `MotoRental (Project)`, `Flask 2.3.3`, `psycopg2-binary >=2.9.9`, `gunicorn 21.2.0` (+17 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Route: servicos.listar_servicos` and `Route: servicos.servicos_locacao`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `get_db_connection()` connect `Core App & Routing` to `Motorcycle Routes`, `DB Init Command`, `Payment Webhook`?**
  _High betweenness centrality (0.118) - this node is a cross-community bridge._
- **Why does `base.html (Layout Template)` connect `Flask Deps & Layout` to `Rental Actions`, `Motorcycle Templates`, `Rental Templates`, `Client Templates`?**
  _High betweenness centrality (0.079) - this node is a cross-community bridge._
- **Why does `locacoes.html (Active Rentals Page)` connect `Rental Actions` to `Flask Deps & Layout`, `Motorcycle Templates`, `Rental Templates`, `Client Templates`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `Config` (e.g. with `get_db_connection()` and `listar_clientes()`) actually correct?**
  _`Config` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `locacoes.html (Active Rentals Page)` (e.g. with `Cliente (Client Entity)` and `Boleto (Payment Slip Entity)`) actually correct?**
  _`locacoes.html (Active Rentals Page)` has 4 INFERRED edges - model-reasoned connections that need verification._
- **What connects `usuarios`, `MotoRental (Project)`, `Flask 2.3.3` to the rest of the system?**
  _22 weakly-connected nodes found - possible documentation gaps or missing edges._